import csv
import json
import re
from pathlib import Path
from app.storage import connect, rows

ALLOWED = {"focus", "probing", "generic", "hint", "question", "reflect", "scaffolding"}
BLOCKED = re.compile(r"\b(the answer is|correct answer|equals?\s*\d|therefore|final answer|solution is)\b|[=+*/]\s*\d", re.I)


def extract_teacher_moves(record, dataset):
    conversation = record.get("conversation", "")
    if isinstance(conversation, list):
        turns = conversation
    else:
        turns = conversation.split("|EOM|")
    result = []
    for i, turn in enumerate(turns):
        move = "generic"
        if isinstance(turn, dict):
            role = str(turn.get("role", turn.get("speaker", ""))).lower()
            text = str(turn.get("text", turn.get("content", "")))
            move = str(turn.get("dialog_act", "generic"))
        else:
            match = re.match(r"\s*(Teacher|Tutor):\s*(?:\(([^)]+)\))?\s*(.*)", str(turn), re.I | re.S)
            if not match:
                continue
            role, move, text = "teacher", (match.group(2) or "generic"), match.group(3)
        if role not in {"teacher", "tutor"}:
            continue
        move_match = re.match(r"\s*\(([^)]+)\)\s*(.*)", text, re.S)
        if move_match:
            move, text = move_match.groups()
        move = str(move).lower().strip()
        text = re.sub(r"\s+", " ", text).strip()
        if move not in ALLOWED or not 8 <= len(text) <= 190 or not text.endswith("?") or BLOCKED.search(text):
            continue
        if re.search(r"\d|\$|\b(pens|chicken|dozen|dollars|meters|kilometers)\b", text, re.I):
            continue
        result.append({"dataset": dataset, "example_id": f"{dataset}-{record.get('qid', record.get('id', 'record'))}-{i}", "student_state": "unknown", "pedagogical_move": move, "tutor_example": text, "is_safe_style_example": True, "contains_domain_facts": False})
    return result


def import_dataset(path, dataset):
    if dataset not in {"mathdial", "kele", "socrateach"}:
        raise ValueError("Unsupported dataset")
    source = Path(path)
    if source.suffix == ".csv":
        with source.open(newline="", encoding="utf-8") as stream:
            records = list(csv.DictReader(stream))
    elif source.suffix == ".jsonl":
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif source.suffix == ".json":
        records = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = records.get("data", records.get("dialogues", [records]))
    else:
        raise ValueError("Expected CSV, JSON or JSONL")
    examples = []
    for record in records:
        if isinstance(record, dict):
            examples.extend(extract_teacher_moves(record, dataset))
    with connect() as db:
        for item in examples:
            db.execute("INSERT OR REPLACE INTO pedagogy VALUES(?,?,?,?,?,?)", (dataset, item["example_id"], item["student_state"], item["pedagogical_move"], item["tutor_example"], 1))
        db.execute("INSERT OR REPLACE INTO dataset_imports(dataset,records,last_source) VALUES(?,?,?)", (dataset, len(records), source.name))
    return {"records": len(records), "safe_examples": len(examples)}


def examples_for(action, limit=2):
    examples = rows("SELECT tutor_example FROM pedagogy WHERE safe=1 ORDER BY example_id LIMIT 100")
    return [row["tutor_example"] for row in examples[:limit]]


def dataset_status():
    stats = rows("SELECT dataset,pedagogical_move,COUNT(*) as total FROM pedagogy GROUP BY dataset,pedagogical_move")
    imports = {x["dataset"]: x for x in rows("SELECT dataset,records,last_source FROM dataset_imports")}
    return [{"dataset": name, "imported_records": imports.get(name, {}).get("records", 0), "safe_probing_examples": sum(x["total"] for x in stats if x["dataset"] == name and x["pedagogical_move"] in {"focus", "probing", "generic", "question"}), "safe_hint_examples": sum(x["total"] for x in stats if x["dataset"] == name and x["pedagogical_move"] in {"hint", "scaffolding"}), "purpose": "pedagogical examples/evaluation only", "license_reminder": "Verify upstream license and attribution before distribution"} for name in ("kele", "mathdial", "socrateach")]
