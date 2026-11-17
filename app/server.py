import csv
import io
import os
import re
import secrets
import uuid
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from app.storage import ROOT, connect, dump, init, one, rows, unpack
from app.retrieval import ingest, approve_note, retrieve
from app.pedagogy import dataset_status, import_dataset
from app.assessment import score
from app.agents import TutorAgents, ProviderUnavailable

load_dotenv(ROOT / ".env")
init()
app = FastAPI(title="ScaffoldAI - Educational Research Prototype", version="0.3.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
agents = TutorAgents()


def admin(password):
    configured = os.getenv("SCAFFOLD_ADMIN_PASSWORD", "")
    if not configured:
        raise HTTPException(503, "Set SCAFFOLD_ADMIN_PASSWORD in .env to enable faculty dashboard")
    if not password or not secrets.compare_digest(password, configured):
        raise HTTPException(403, "Faculty access denied")


class Question(BaseModel):
    id: str
    course: str = "ML"
    topic: str
    question: str
    ideal_answer: str
    rubric_points: list[dict]
    allowed_exam_hints: dict = Field(default_factory=dict)
    approved: bool = False


class Start(BaseModel):
    student_id: str = Field(min_length=3, max_length=60)
    mode: str
    course: str = "ML"
    topic: str
    question_id: str | None = None
    question: str = ""


class Turn(BaseModel):
    session_id: str
    attempt: str = Field(default="", max_length=3000)
    hint_level: int = Field(default=0, ge=0, le=3)
    request_hint: bool = False


class Submit(BaseModel):
    session_id: str
    answer: str = Field(min_length=1, max_length=5000)


class Grade(BaseModel):
    score: float = Field(ge=0, le=100)
    feedback: str = ""


class Course(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=100)


@app.get("/")
def student_ui():
    return FileResponse(ROOT / "static/student.html")


@app.get("/faculty")
def faculty_ui():
    return FileResponse(ROOT / "static/faculty.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "prototype": True, "course": "ML", "model_mode": "live" if agents.provider.live else "mock", "runtime_agent_count": 3}


@app.get("/api/questions")
def approved_questions(course: str = "ML", topic: str = ""):
    query = "SELECT id,course,topic,question FROM questions WHERE approved=1 AND course=?"
    params = [course]
    if topic:
        query += " AND topic=?"
        params.append(topic)
    return rows(query, tuple(params))


@app.get("/api/courses")
def courses():
    result = rows("SELECT code,name FROM courses ORDER BY code")
    for course in result:
        notes = rows("SELECT topic,filename FROM notes WHERE course=? AND approved=1 ORDER BY topic,filename", (course["code"],))
        topics = sorted({item["topic"] for item in notes} | {item["topic"] for item in rows("SELECT DISTINCT topic FROM questions WHERE course=? AND approved=1", (course["code"],))})
        course["topics"] = topics or ["General"]
        course["approved_notes"] = len(notes)
        course["files"] = sorted({item["filename"] for item in notes})
    return result


@app.get("/api/coverage")
def course_coverage(course: str, topic: str = "General", question: str = ""):
    approved = rows("SELECT filename FROM notes WHERE course=? AND topic=? AND approved=1", (course, topic))
    evidence = retrieve(question, course, topic) if question.strip() else []
    return {"course": course, "topic": topic, "approved_notes": len(approved), "files": sorted({item["filename"] for item in approved}), "matched": bool(evidence), "sources": [{"file": item["filename"], "page": item["page"]} for item in evidence]}


@app.post("/api/sessions")
def start_session(body: Start):
    if body.mode not in {"normal", "exam", "independent"}:
        raise HTTPException(400, "Mode must be normal, exam, or independent")
    if not body.student_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "Use an anonymous alphanumeric student ID")
    question = None
    if body.question_id:
        question = one("SELECT * FROM questions WHERE id=? AND approved=1", (body.question_id,))
    if body.mode != "normal" and not question:
        raise HTTPException(400, "Exam and independent modes require an approved question")
    if body.question_id and not question:
        raise HTTPException(400, "Question not approved")
    if question and (question["course"] != body.course or question["topic"] != body.topic):
        raise HTTPException(400, "Question course/topic mismatch")
    title = question["question"] if question else body.question.strip()
    if not title:
        raise HTTPException(400, "Enter a question or select an approved one")
    if body.mode == "normal" and not retrieve(title, body.course, body.topic):
        raise HTTPException(409, f"No approved {body.course}/{body.topic} note passage matches this question. Upload and approve relevant lecture notes, or choose a question covered by this course.")
    sid = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO sessions(id,student_id,mode,course,topic,question_id,question) VALUES(?,?,?,?,?,?,?)", (sid, body.student_id, body.mode, body.course, body.topic, body.question_id, title))
    max_hints = 3 if body.mode == "normal" else 0
    if body.mode == "exam":
        allowed = unpack(question["hints"], {})
        max_hints = 0
        for level in range(1, 4):
            if not allowed.get(f"level_{level}"):
                break
            max_hints = level
    return {"session_id": sid, "mode": body.mode, "question": title, "max_hints": max_hints, "notice": "Educational research prototype; grades are provisional."}


def session(sid):
    record = one("SELECT * FROM sessions WHERE id=?", (sid,))
    if not record:
        raise HTTPException(404, "Session not found")
    return record


def related_question(record):
    return one("SELECT * FROM questions WHERE id=?", (record["question_id"],)) if record["question_id"] else None


def session_hint_limit(record):
    if record["mode"] == "normal":
        return 3
    if record["mode"] != "exam":
        return 0
    question = related_question(record)
    allowed = unpack(question["hints"], {}) if question else {}
    maximum = 0
    for level in range(1, 4):
        if not allowed.get(f"level_{level}"):
            break
        maximum = level
    return maximum


@app.get("/api/student/sessions")
def student_sessions(student_id: str):
    if not student_id or len(student_id) > 60:
        raise HTTPException(400, "Enter a valid student ID")
    return rows("SELECT id,student_id,mode,course,topic,question,question_id,hint_count,finished,created_at FROM sessions WHERE student_id=? ORDER BY created_at DESC", (student_id,))


@app.get("/api/sessions/{sid}")
def student_session(sid: str):
    record = session(sid)
    attempts = rows("SELECT student_text,tutor_text,sources FROM attempts WHERE session_id=? ORDER BY id", (sid,))
    submission = one("SELECT answer,provisional_score,faculty_score,feedback,coverage FROM submissions WHERE session_id=? ORDER BY id DESC", (sid,))
    if submission:
        if record["mode"] == "normal":
            approved_question = related_question(record)
            submission["ideal_answer"] = approved_question["ideal_answer"] if approved_question else None
            submission["coverage"] = unpack(submission["coverage"], {}).get("coverage", [])
        else:
            submission.pop("coverage", None)
            submission.pop("provisional_score", None)
    return {"session_id": record["id"], "student_id": record["student_id"], "mode": record["mode"], "course": record["course"], "topic": record["topic"], "question_id": record["question_id"], "question": record["question"], "hint_count": record["hint_count"], "max_hints": session_hint_limit(record), "finished": bool(record["finished"]), "attempts": [{"student_text": item["student_text"], "tutor_text": item["tutor_text"], "sources": unpack(item["sources"], [])} for item in attempts], "submission": submission}


@app.post("/api/turns")
def turn(body: Turn):
    s = session(body.session_id)
    if s["finished"]:
        raise HTTPException(400, "Session already submitted")
    if s["mode"] == "independent":
        raise HTTPException(403, "AI assistance is disabled in Independent QnA")
    if body.request_hint:
        if body.hint_level != s["hint_count"] + 1 or body.hint_level > 3:
            raise HTTPException(400, "Each hint level can be requested only once, in order")
    elif body.hint_level != 0:
        raise HTTPException(400, "Use the Ask for hint button to request a hint level")
    elif not body.attempt.strip():
        raise HTTPException(400, "Enter your reasoning before sending")
    history = rows("SELECT student_text,tutor_text FROM attempts WHERE session_id=? ORDER BY id", (s["id"],))
    messages = []
    for item in history:
        messages.extend([{"role": "student", "content": item["student_text"]}, {"role": "tutor", "content": item["tutor_text"]}])
    question = related_question(s)
    if s["mode"] == "exam":
        if not body.request_hint:
            raise HTTPException(403, "Exam permits explicitly requested approved hints only")
        allowed = unpack(question["hints"], {})
        hint = allowed.get(f"level_{body.hint_level}")
        if not hint:
            raise HTTPException(403, "This hint level is not approved by faculty")
        try:
            internal = agents.run(s["question"], body.attempt or "Hint requested", s["course"], s["topic"], messages, body.hint_level, question["ideal_answer"], exam=True)
        except ProviderUnavailable as error:
            raise HTTPException(503, "Model unavailable: " + str(error)) from error
        if not internal["sources"]:
            raise HTTPException(409, "Approved notes for this topic are required")
        with connect() as db:
            updated = db.execute("UPDATE sessions SET hint_count=? WHERE id=? AND hint_count=? AND finished=0", (body.hint_level, s["id"], body.hint_level - 1))
            if updated.rowcount != 1:
                raise HTTPException(409, "This hint level has already been used")
            db.execute("INSERT INTO attempts(session_id,student_text,tutor_text,diagnosis,traces,sources,leak_check) VALUES(?,?,?,?,?,?,?)", (s["id"], body.attempt or "Hint requested", hint, dump(internal["diagnosis"]), dump(internal["traces"]), dump(internal["sources"]), "faculty_preapproved_hint_only"))
        return {"reply": hint, "hint_level": body.hint_level, "notice": "Faculty-approved hint only. No evaluation is available during the exam."}
    ideal = question["ideal_answer"] if question else ""
    try:
        result = agents.run(s["question"], body.attempt or "Hint requested", s["course"], s["topic"], messages, body.hint_level, ideal)
    except ProviderUnavailable as error:
        raise HTTPException(503, "Model unavailable: " + str(error)) from error
    if not result["sources"]:
        raise HTTPException(409, f"No matching approved note passage in {s['course']}/{s['topic']} for this question. Ask about a covered concept or upload relevant slides.")
    with connect() as db:
        if body.request_hint:
            updated = db.execute("UPDATE sessions SET hint_count=? WHERE id=? AND hint_count=? AND finished=0", (body.hint_level, s["id"], body.hint_level - 1))
            if updated.rowcount != 1:
                raise HTTPException(409, "This hint level has already been used")
        db.execute("INSERT INTO attempts(session_id,student_text,tutor_text,diagnosis,traces,sources,leak_check) VALUES(?,?,?,?,?,?,?)", (s["id"], body.attempt or "Hint requested", result["reply"], dump(result["diagnosis"]), dump(result["traces"]), dump(result["sources"]), result["leak_check"]))
    return {"reply": result["reply"], "sources": result["sources"], "hint_level": body.hint_level, "leak_check": result["leak_check"]}


@app.post("/api/submissions")
def submit(body: Submit):
    s = session(body.session_id)
    if s["finished"]:
        raise HTTPException(400, "Already submitted")
    question = related_question(s)
    grade = score(body.answer, unpack(question["rubric"], []), question["ideal_answer"]) if question else {"score": None, "coverage": [], "uncertain": True}
    attempts = [item["student_text"] for item in rows("SELECT student_text FROM attempts WHERE session_id=? ORDER BY id", (s["id"],))]
    try:
        understanding = agents.assess_understanding(s["question"], body.answer, s["course"], s["topic"], attempts, unpack(question["rubric"], []) if question else [])
    except ProviderUnavailable as error:
        understanding = {"understanding_score": None, "reasoning_score": None, "answer_score": None, "confidence": "unavailable", "rationale": "Model assessment unavailable: " + str(error)[:200], "method": "unavailable"}
    provisional_score = grade["score"] if question else understanding["answer_score"]
    with connect() as db:
        db.execute("INSERT INTO submissions(session_id,answer,provisional_score,coverage) VALUES(?,?,?,?)", (s["id"], body.answer, provisional_score, dump(grade)))
        db.execute("INSERT INTO session_assessments(session_id,understanding_score,reasoning_score,answer_score,confidence,rationale,method) VALUES(?,?,?,?,?,?,?)", (s["id"], understanding["understanding_score"], understanding["reasoning_score"], understanding["answer_score"], understanding["confidence"], understanding["rationale"], understanding["method"]))
        db.execute("UPDATE sessions SET finished=1 WHERE id=?", (s["id"],))
    if s["mode"] in {"exam", "independent"}:
        return {"message": "Your answer has been submitted for evaluation."}
    return {"message": "Study answer submitted", "provisional_score": provisional_score, "accepted": provisional_score is not None and provisional_score >= 85 and not grade.get("uncertain", False) if question else False, "coverage": grade["coverage"], "correct_points": [x["criterion"] for x in grade["coverage"] if x["met"]], "missing_points": [x["criterion"] for x in grade["coverage"] if not x["met"]], "ideal_answer": question["ideal_answer"] if question else None, "notice": "Automated provisional score; requires faculty review"}


@app.get("/api/progress/{student_id}")
def progress(student_id: str):
    items = rows("SELECT s.mode,s.topic,s.created_at,s.hint_count,s.finished FROM sessions s WHERE s.student_id=?", (student_id,))
    study_scores = rows("SELECT u.provisional_score FROM submissions u JOIN sessions s ON s.id=u.session_id WHERE s.student_id=? AND s.mode='normal'", (student_id,))
    return {"sessions": items, "study_scores": [x["provisional_score"] for x in study_scores], "notice": "Scores are provisional, not official grades"}


@app.get("/api/admin/notes")
def notes(x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    return rows("SELECT n.*,COUNT(c.id) AS chunks FROM notes n LEFT JOIN chunks c ON c.note_id=n.id GROUP BY n.id")


@app.post("/api/admin/courses")
def save_course(body: Course, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    code = body.code.strip().upper()
    name = body.name.strip()
    if not re.fullmatch(r"[A-Z0-9_-]{2,20}", code):
        raise HTTPException(400, "Course code must use 2–20 letters, numbers, hyphens, or underscores")
    if len(name) < 2:
        raise HTTPException(400, "Enter a course name")
    with connect() as db:
        db.execute("INSERT INTO courses(code,name) VALUES(?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name", (code, name))
    return {"code": code, "name": name}


@app.post("/api/admin/notes/upload")
async def upload_note(file: UploadFile = File(...), course: str = Form("ML"), topic: str = Form("General"), x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    if not one("SELECT code FROM courses WHERE code=?", (course,)):
        raise HTTPException(400, "Create this course before uploading notes")
    topic = topic.strip() or "General"
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt", ".pptx", ".docx"}:
        raise HTTPException(400, "Only PDF/PPTX/DOCX/TXT")
    target_dir = ROOT / "data/course_notes/raw"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (uuid.uuid4().hex + suffix)
    data = await file.read(50_000_001)
    if len(data) > 50_000_000:
        raise HTTPException(413, "50 MB limit")
    target.write_bytes(data)
    try:
        result = ingest(target, course, topic, approved=False)
    except Exception as error:
        target.unlink(missing_ok=True)
        raise HTTPException(400, str(error)) from error
    with connect() as db:
        db.execute("UPDATE notes SET filename=? WHERE id=?", (Path(file.filename).name, result["note_id"]))
    return result


@app.post("/api/admin/notes/{note_id}/approval")
def note_approval(note_id: int, approved: bool = True, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    try:
        approve_note(note_id, approved)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return {"note_id": note_id, "approved": approved}


@app.get("/api/admin/questions")
def all_questions(x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    return [{**item, "rubric_points": unpack(item.pop("rubric"), []), "allowed_exam_hints": unpack(item.pop("hints"), {})} for item in rows("SELECT * FROM questions")]


@app.post("/api/admin/questions")
def save_question(body: Question, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    if not one("SELECT code FROM courses WHERE code=?", (body.course,)):
        raise HTTPException(400, "Create this course before adding its questions")
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO questions VALUES(?,?,?,?,?,?,?,?)", (body.id, body.course, body.topic, body.question, body.ideal_answer, dump(body.rubric_points), dump(body.allowed_exam_hints), int(body.approved)))
    return {"id": body.id, "approved": body.approved}


@app.post("/api/admin/questions/{qid}/approval")
def question_approval(qid: str, approved: bool = True, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    if not one("SELECT id FROM questions WHERE id=?", (qid,)):
        raise HTTPException(404, "Question not found")
    with connect() as db:
        db.execute("UPDATE questions SET approved=? WHERE id=?", (int(approved), qid))
    return {"id": qid, "approved": approved}


@app.get("/api/admin/sessions")
def all_sessions(x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    return rows("SELECT s.*,a.understanding_score,a.confidence AS understanding_confidence FROM sessions s LEFT JOIN session_assessments a ON a.session_id=s.id ORDER BY s.created_at DESC")


@app.get("/api/admin/sessions/{sid}")
def session_details(sid: str, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    s = session(sid)
    return {"session": s, "question": related_question(s), "attempts": rows("SELECT * FROM attempts WHERE session_id=?", (sid,)), "submissions": rows("SELECT * FROM submissions WHERE session_id=?", (sid,)), "understanding": one("SELECT * FROM session_assessments WHERE session_id=?", (sid,))}


@app.post("/api/admin/sessions/{sid}/reassess")
def reassess_session(sid: str, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    record = session(sid)
    submission = one("SELECT answer FROM submissions WHERE session_id=? ORDER BY id DESC", (sid,))
    if not submission:
        raise HTTPException(400, "The student must submit a final answer before reassessment")
    attempts = [item["student_text"] for item in rows("SELECT student_text FROM attempts WHERE session_id=? ORDER BY id", (sid,))]
    question = related_question(record)
    try:
        understanding = agents.assess_understanding(record["question"], submission["answer"], record["course"], record["topic"], attempts, unpack(question["rubric"], []) if question else [])
    except ProviderUnavailable as error:
        raise HTTPException(503, "Model assessment unavailable: " + str(error)) from error
    if understanding["understanding_score"] is None:
        raise HTTPException(503, understanding["rationale"])
    with connect() as db:
        db.execute("""INSERT INTO session_assessments(session_id,understanding_score,reasoning_score,answer_score,confidence,rationale,method)
                      VALUES(?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
                      understanding_score=excluded.understanding_score, reasoning_score=excluded.reasoning_score,
                      answer_score=excluded.answer_score, confidence=excluded.confidence,
                      rationale=excluded.rationale, method=excluded.method, created_at=CURRENT_TIMESTAMP""",
                   (sid, understanding["understanding_score"], understanding["reasoning_score"], understanding["answer_score"], understanding["confidence"], understanding["rationale"], understanding["method"]))
    return understanding


@app.delete("/api/admin/sessions/{sid}")
def delete_session(sid: str, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    session(sid)
    with connect() as db:
        db.execute("DELETE FROM attempts WHERE session_id=?", (sid,))
        db.execute("DELETE FROM submissions WHERE session_id=?", (sid,))
        db.execute("DELETE FROM session_assessments WHERE session_id=?", (sid,))
        db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    return {"deleted": sid}


@app.post("/api/admin/submissions/{submission_id}/grade")
def faculty_grade(submission_id: int, grade: Grade, x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    if not one("SELECT id FROM submissions WHERE id=?", (submission_id,)):
        raise HTTPException(404, "Submission not found")
    with connect() as db:
        db.execute("UPDATE submissions SET faculty_score=?,feedback=? WHERE id=?", (grade.score, grade.feedback, submission_id))
    return {"id": submission_id, "faculty_score": grade.score}


@app.get("/api/admin/datasets")
def datasets(x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    return dataset_status()


@app.get("/api/admin/export.csv")
def export_csv(x_admin_password: str = Header(default="")):
    admin(x_admin_password)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["session_id", "student_id", "mode", "topic", "created_at", "provisional_score", "understanding_score", "reasoning_score", "answer_score", "understanding_confidence", "faculty_score"])
    for item in rows("SELECT s.id,s.student_id,s.mode,s.topic,s.created_at,u.provisional_score,a.understanding_score,a.reasoning_score,a.answer_score,a.confidence AS understanding_confidence,u.faculty_score FROM sessions s LEFT JOIN submissions u ON u.session_id=s.id LEFT JOIN session_assessments a ON a.session_id=s.id"):
        writer.writerow([item[key] for key in ("id", "student_id", "mode", "topic", "created_at", "provisional_score", "understanding_score", "reasoning_score", "answer_score", "understanding_confidence", "faculty_score")])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=scaffoldai_anonymous_export.csv"})
