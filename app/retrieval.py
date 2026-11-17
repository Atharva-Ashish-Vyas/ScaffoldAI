import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from app.storage import connect, dump, one, rows, unpack


def tokens(text):
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def embed(text):
    terms = tokens(text)
    counts = Counter(terms + [terms[i] + "_" + terms[i + 1] for i in range(len(terms) - 1)])
    vector = {}
    for word, n in counts.items():
        key = str(int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 2048)
        vector[key] = vector.get(key, 0) + n
    size = math.sqrt(sum(v * v for v in vector.values())) or 1
    return {k: v / size for k, v in vector.items()}


def similarity(a, b):
    return sum(value * b.get(key, 0) for key, value in a.items())


def split_text(text, size=900, overlap=120):
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    pieces = []
    pos = 0
    while pos < len(clean):
        end = min(len(clean), pos + size)
        if end < len(clean):
            boundary = clean.rfind(" ", pos + size // 2, end)
            if boundary > pos:
                end = boundary
        pieces.append(clean[pos:end])
        if end == len(clean):
            break
        pos = max(pos + 1, end - overlap)
    return pieces


def extract(path):
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [(1, path.read_text(encoding="utf-8", errors="replace"))]
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    if suffix == ".pptx":
        from pptx import Presentation
        deck = Presentation(str(path))
        return [(i + 1, "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame)) for i, slide in enumerate(deck.slides)]
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return [(1, "\n".join(p.text for p in doc.paragraphs))]
    raise ValueError("Supported files: PDF, PPTX, DOCX, TXT")


def ingest(path, course, topic, approved=False):
    path = Path(path)
    pages = extract(path)
    if not any(text.strip() for _, text in pages):
        raise ValueError("No extractable text found; scanned images require OCR")
    with connect() as db:
        cursor = db.execute("INSERT INTO notes(filename,course,topic,approved) VALUES(?,?,?,?)", (path.name, course, topic, int(approved)))
        note_id = cursor.lastrowid
        count = 0
        for number, raw in pages:
            lines = [x.strip() for x in raw.splitlines() if x.strip()]
            heading = lines[0][:120] if lines else ""
            for offset, chunk in enumerate(split_text(raw)):
                chunk_id = f"note{note_id}-p{number}-c{offset}"
                db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (chunk_id, note_id, number, heading, chunk, dump(embed(chunk))))
                count += 1
    return {"note_id": note_id, "pages": len(pages), "chunks": count, "approved": approved}


def retrieve(question, course, topic, limit=4, min_score=0.065):
    candidates = rows("""SELECT c.id,c.page,c.heading,c.content,c.embedding,n.filename,n.course,n.topic FROM chunks c JOIN notes n ON n.id=c.note_id WHERE n.approved=1 AND n.course=? AND n.topic=?""", (course, topic))
    stopwords = {"about", "after", "against", "and", "are", "between", "can", "could", "difference", "do", "does", "explain", "for", "from", "have", "how", "in", "into", "is", "it", "machine", "learning", "model", "models", "of", "on", "performance", "student", "the", "their", "these", "those", "to", "what", "when", "where", "which", "while", "with", "would", "why"}
    terms = set(tokens(question)) - stopwords
    if not terms:
        return []
    if len(terms) <= 2:
        limit = min(limit, 1)
    required = min(2, len(terms))
    ranked = []
    for chunk in candidates:
        content_terms = set(tokens(chunk["content"]))
        matched = terms & content_terms
        if len(matched) < required:
            continue
        score = len(matched) / len(terms)
        chunk.pop("embedding", None)
        chunk["score"] = round(score, 4)
        ranked.append(chunk)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    selected = []
    seen_pages = set()
    for chunk in ranked:
        page_key = (chunk["filename"], chunk["page"])
        if page_key not in seen_pages:
            selected.append(chunk)
            seen_pages.add(page_key)
        if len(selected) == limit:
            break
    return selected


def approve_note(note_id, approved=True):
    if not one("SELECT id FROM notes WHERE id=?", (note_id,)):
        raise ValueError("Note not found")
    with connect() as db:
        db.execute("UPDATE notes SET approved=? WHERE id=?", (int(approved), note_id))
