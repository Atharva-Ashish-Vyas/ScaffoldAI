import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "scaffoldai.sqlite3"


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(os.getenv("SCAFFOLD_DB", str(DB)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, filename TEXT, course TEXT, topic TEXT, approved INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS courses(code TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, note_id INTEGER, page INTEGER, heading TEXT, content TEXT, embedding TEXT, FOREIGN KEY(note_id) REFERENCES notes(id));
        CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, course TEXT, topic TEXT, question TEXT, ideal_answer TEXT, rubric TEXT, hints TEXT, approved INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, student_id TEXT, mode TEXT, course TEXT, topic TEXT, question_id TEXT, question TEXT, hint_count INTEGER DEFAULT 0, finished INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, student_text TEXT, tutor_text TEXT, score REAL, coverage TEXT, diagnosis TEXT, traces TEXT, sources TEXT, leak_check TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, answer TEXT, provisional_score REAL, coverage TEXT, faculty_score REAL, feedback TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS session_assessments(session_id TEXT PRIMARY KEY, understanding_score REAL, reasoning_score REAL, answer_score REAL, confidence TEXT, rationale TEXT, method TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(session_id) REFERENCES sessions(id));
        CREATE TABLE IF NOT EXISTS pedagogy(dataset TEXT, example_id TEXT, student_state TEXT, pedagogical_move TEXT, tutor_example TEXT, safe INTEGER, PRIMARY KEY(dataset,example_id));
        CREATE TABLE IF NOT EXISTS dataset_imports(dataset TEXT PRIMARY KEY, records INTEGER, last_source TEXT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO courses(code,name) VALUES('ML','Machine Learning');
        INSERT OR IGNORE INTO courses(code,name) SELECT DISTINCT course,course FROM notes WHERE course IS NOT NULL AND course!='';
        INSERT OR IGNORE INTO courses(code,name) SELECT DISTINCT course,course FROM questions WHERE course IS NOT NULL AND course!='';
        """)


def rows(query, params=()):
    with connect() as db:
        return [dict(x) for x in db.execute(query, params).fetchall()]


def one(query, params=()):
    result = rows(query, params)
    return result[0] if result else None


def execute(query, params=()):
    with connect() as db:
        result = db.execute(query, params)
        return result.lastrowid


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def unpack(value, fallback=None):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
