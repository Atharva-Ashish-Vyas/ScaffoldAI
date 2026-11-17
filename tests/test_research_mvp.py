import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.storage import init, rows, one
from app.retrieval import split_text, ingest, retrieve, approve_note
from app.pedagogy import extract_teacher_moves, import_dataset
from app.assessment import has_reasoning, safe_probe, score, validate_hint
from app.agents import Provider, TutorAgents, parse_diagnosis
from app.server import app
from app import server


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SCAFFOLD_DB", str(tmp_path / "isolated.sqlite3"))
    monkeypatch.setenv("SCAFFOLD_ADMIN_PASSWORD", "test-admin")
    init()


def headers():
    return {"X-Admin-Password": "test-admin"}


def seed(tmp_path):
    note = tmp_path / "course.txt"
    note.write_text("Validation accuracy estimates performance on unseen data. A large training validation gap suggests overfitting and weaker generalization. Regularization and early stopping can sometimes help.")
    result = ingest(note, "ML", "General", True)
    return result


def question():
    return {"id": "ml-001", "course": "ML", "topic": "General", "question": "What do the training and validation scores indicate about generalization?", "ideal_answer": "Validation on unseen examples helps identify overfitting and generalization.", "rubric_points": [{"criterion": "Relates validation to unseen data", "weight": 60, "accepted_concepts": ["unseen data", "new data", "held out"]}, {"criterion": "Identifies overfitting", "weight": 40, "accepted_concepts": ["overfitting", "memorization"]}], "allowed_exam_hints": {"level_1": "Compare seen and unseen examples."}, "approved": True}


def test_extraction_chunking_and_approval(tmp_path):
    assert len(split_text("one " * 600, size=160, overlap=20)) > 1
    source = tmp_path / "note.txt"
    source.write_text("Training validation generalization overfitting regularization " * 30)
    indexed = ingest(source, "ML", "General", False)
    assert indexed["chunks"] > 1
    assert retrieve("validation generalization", "ML", "General") == []
    approve_note(indexed["note_id"])
    found = retrieve("validation generalization", "ML", "General")
    assert found and found[0]["filename"] == "note.txt" and found[0]["page"] == 1


def test_mathdial_style_filter_and_import(tmp_path):
    record = {"qid": "42", "conversation": "Teacher: (focus)What relationship should you check before deciding that?|EOM|Student: I do not know|EOM|Teacher: (telling)The answer is 20.|EOM|Teacher: (focus)How would you justify your next step?"}
    examples = extract_teacher_moves(record, "mathdial")
    assert len(examples) == 2
    assert all(not e["contains_domain_facts"] for e in examples)
    source = tmp_path / "mathdial.jsonl"
    source.write_text(json.dumps(record) + "\n")
    result = import_dataset(source, "mathdial")
    assert result["safe_examples"] == 2


def test_diagnosis_and_three_agent_order(tmp_path):
    seed(tmp_path)
    agents = TutorAgents()
    result = agents.run("Why is validation accuracy low when training accuracy is high?", "The model has memorized training examples", "ML", "General", [], 0)
    assert [x["agent"] for x in result["traces"] if "agent" in x] == ["course_retrieval", "error_diagnosis", "socratic_hint"]
    assert result["sources"][0]["page"] == 1
    assert parse_diagnosis("not-json")["action"] == "probe"
    assert result["reply"].endswith("?")


def test_missing_note_refuses_factual_assistance():
    result = TutorAgents().run("What is backpropagation?", "I don't know", "ML", "General", [], 0)
    assert result["leak_check"] == "blocked_no_evidence"
    assert len(result["traces"]) == 1


def test_rubric_paraphrase_and_leakage(tmp_path):
    rubric = [{"criterion": "Validation examines unseen data", "weight": 100, "accepted_concepts": ["held out examples", "new data"]}]
    assert score("Use new data to assess the model", rubric, "Validation measures generalization to new data")["score"] >= 85
    evidence = [{"content": "generalization"}]
    assert not validate_hint("The correct answer is overfitting", 0, "overfitting", evidence)[0]
    assert not validate_hint("Why do scores differ?", 0, "", [], [])[0]
    assert not validate_hint("Why do scores differ?", 0, "", evidence, ["Why do scores differ?"])[0]
    assert validate_hint("How does bias affect the model?", 1, "", evidence, [], "Explain training and validation performance")[1] == "off_topic"
    assert validate_hint("How does bias affect training?", 1, "", evidence, [], "Explain the difference between training and validation performance")[1] == "off_topic"
    assert validate_hint("Overfitting occurs when a model memorizes noise. How does that affect generalization?", 0, "", evidence, [], "What is overfitting?")[1] == "probe_must_not_explain"
    assert validate_hint("How does a confusion matrix show errors?", 0, "", evidence, [], "What is overfitting?")[1] == "off_topic"
    grounded = [{"content": "Overfitting concerns training noise and weak results on unseen examples."}]
    assert validate_hint("Training scores are high but unseen-data results are low. What might overfitting have to do with that gap?", 1, "", grounded, [], "What is overfitting?")[0]
    assert has_reasoning("Does it mean a model is not fit to understand responses?", "What is overfitting?")


def test_phishing_first_hint_uses_course_clue(tmp_path):
    note = tmp_path / "security.txt"
    note.write_text("Phishing is a social engineering attempt sent by email. The sender may appear to be a trusted company or boss and ask the recipient to open a link or attachment. A malicious attachment can install malware.")
    ingest(note, "CNS", "General", True)
    question = "What is phishing, and how can you identify a phishing email?"
    assert safe_probe(question) == "What do you think phishing means in your own words?"

    class BadTutor:
        def generate(self, system, user, max_tokens=180):
            if "DIAGNOSIS_JSON" in system:
                return json.dumps({"student_state": "confused", "action": "hint"})
            return "Which idea in the approved notes connects to your current reasoning?"

    result = TutorAgents(provider=BadTutor()).run(question, "Hint requested", "CNS", "General", [], 1)
    assert "phishing" in result["reply"].lower()
    assert "social engineering" in result["reply"].lower()
    assert "approved notes" not in result["reply"].lower()
    assert result["reply"].endswith("?")

    model_hint = ("To help you define phishing, consider this specific clue from the notes: it is often an email "
                  "that appears to come from someone you trust, such as a boss or a company you do business with. "
                  "Given that appearance, what specific action does the attacker encourage the recipient to take in order to compromise their computer?")
    assert validate_hint(model_hint, 1, "", retrieve(question, "CNS", "General"), [], question)[0]


def test_custom_question_stays_socratic_and_understanding_is_recorded(tmp_path, monkeypatch):
    note = tmp_path / "overfitting.txt"
    note.write_text("Overfitting occurs when a model fits training noise and fails to generalize to unseen examples.")
    ingest(note, "ML", "General", True)
    agent = TutorAgents()
    first = agent.run("What is overfitting?", "What is overfitting?", "ML", "General", [], 0)
    assert first["reply"] == "What do you think overfitting means in your own words?"
    assert "fails to generalize" not in first["reply"]
    followup = agent.run("What is overfitting?", "What is overfitting?", "ML", "General", [{"role": "student", "content": "What is overfitting?"}, {"role": "tutor", "content": first["reply"]}], 0)
    assert "overfitting" in followup["reply"] and followup["reply"] != first["reply"]

    class BadTutor:
        def __init__(self, reply):
            self.reply = reply
        def generate(self, system, user):
            if "DIAGNOSIS_JSON" in system:
                return json.dumps({"student_state": "incorrect", "misconception": "confuses overfitting with lack of understanding", "action": "counterexample", "confidence": "high"})
            return self.reply
    for bad_reply in ("Overfitting occurs when a model memorizes noise. How will it generalize?", "How does a confusion matrix show errors?"):
        guarded = TutorAgents(provider=BadTutor(bad_reply)).run("What is overfitting?", "Does it mean a model is not fit to understand responses?", "ML", "General", [], 0)
        assert guarded["reply"].startswith("Not quite.")
        assert "overfitting" in guarded["reply"] and "training noise" in guarded["reply"]
        assert guarded["leak_check"] == "misconception_guidance"
        hinted = TutorAgents(provider=BadTutor(bad_reply)).run("What is overfitting?", "Hint requested", "ML", "General", [], 1)
        assert "overfitting" in hinted["reply"] and "training noise" in hinted["reply"]
        assert "approved notes" not in hinted["reply"]

    class Assessor:
        live = True
        def generate(self, system, user, max_tokens=180):
            assert "ASSESSMENT_JSON" in system
            assert max_tokens == 300
            return json.dumps({"answer_score": 90, "reasoning_score": 70, "confidence": "medium", "rationale": "Correct explanation with some earlier uncertainty. " + "This explanation remains complete. " * 20})
    monkeypatch.setattr(server.agents, "provider", Assessor())
    sid = server.start_session(server.Start(student_id="student001", mode="normal", course="ML", topic="General", question="What is overfitting?"))["session_id"]
    with server.connect() as db:
        db.execute("INSERT INTO attempts(session_id,student_text,tutor_text) VALUES(?,?,?)", (sid, "I think it is fitting training examples too closely", "What might happen on new data?"))
    submission = server.submit(server.Submit(session_id=sid, answer="It learns noise in training and performs poorly on new data."))
    assert submission["provisional_score"] == 90
    detail = server.session_details(sid, x_admin_password="test-admin")
    assert detail["understanding"]["understanding_score"] == 83
    assert detail["understanding"]["reasoning_score"] == 70
    assert len(detail["understanding"]["rationale"]) > 400
    assert detail["understanding"]["rationale"].endswith("This explanation remains complete.")
    with server.connect() as db:
        db.execute("UPDATE session_assessments SET rationale='Old clipped text' WHERE session_id=?", (sid,))
    regenerated = server.reassess_session(sid, x_admin_password="test-admin")
    assert len(regenerated["rationale"]) > 400
    assert len(server.session_details(sid, x_admin_password="test-admin")["understanding"]["rationale"]) > 400


def test_modes_and_role_separation(tmp_path):
    seed(tmp_path)
    client = TestClient(app)
    assert client.get("/api/admin/questions").status_code == 403
    assert client.post("/api/admin/questions", headers=headers(), json=question()).status_code == 200
    assert client.get("/api/questions").json()[0]["id"] == "ml-001"
    for mode in ("normal", "exam", "independent"):
        started = client.post("/api/sessions", json={"student_id": "anon001", "mode": mode, "course": "ML", "topic": "General", "question_id": "ml-001"})
        assert started.status_code == 200
        sid = started.json()["session_id"]
        if mode == "normal":
            turn = client.post("/api/turns", json={"session_id": sid, "attempt": "Training high, validation low"})
            assert turn.status_code == 200
            assert "sources" in turn.json()
        elif mode == "exam":
            assert client.post("/api/turns", json={"session_id": sid, "attempt": "Help me", "hint_level": 0}).status_code == 403
            hint = client.post("/api/turns", json={"session_id": sid, "attempt": "Help me", "hint_level": 1, "request_hint": True})
            assert hint.status_code == 200
            assert "score" not in hint.json() and "ideal_answer" not in hint.json()
            assert client.post("/api/turns", json={"session_id": sid, "hint_level": 1, "request_hint": True}).status_code == 400
        else:
            assert client.post("/api/turns", json={"session_id": sid, "attempt": "Help me"}).status_code == 403
            assert rows("SELECT * FROM attempts WHERE session_id=?", (sid,)) == []
        final = client.post("/api/submissions", json={"session_id": sid, "answer": "Overfitting can be spotted using new data"})
        assert final.status_code == 200
        if mode in ("exam", "independent"):
            assert final.json() == {"message": "Your answer has been submitted for evaluation."}
        else:
            assert "provisional_score" in final.json()


def test_admin_grading_export_and_persistence(tmp_path):
    seed(tmp_path)
    client = TestClient(app)
    client.post("/api/admin/questions", headers=headers(), json=question())
    sid = client.post("/api/sessions", json={"student_id": "anon008", "mode": "independent", "course": "ML", "topic": "General", "question_id": "ml-001"}).json()["session_id"]
    client.post("/api/submissions", json={"session_id": sid, "answer": "new data checks generalization"})
    sub = one("SELECT id FROM submissions WHERE session_id=?", (sid,))
    grade = client.post(f"/api/admin/submissions/{sub['id']}/grade", headers=headers(), json={"score": 91, "feedback": "Clear reasoning"})
    assert grade.status_code == 200
    assert one("SELECT faculty_score FROM submissions WHERE id=?", (sub["id"],))["faculty_score"] == 91
    assert "anon008" in client.get("/api/admin/export.csv", headers=headers()).text


def test_guided_hints_are_explicit_once_and_ordered(tmp_path):
    seed(tmp_path)
    client = TestClient(app)
    client.post("/api/admin/questions", headers=headers(), json=question())
    sid = client.post("/api/sessions", json={"student_id": "anon009", "mode": "normal", "course": "ML", "topic": "General", "question_id": "ml-001"}).json()["session_id"]
    def hint(level):
        return client.post("/api/turns", json={"session_id": sid, "hint_level": level, "request_hint": True})
    assert hint(2).status_code == 400
    assert hint(1).status_code == 200
    assert hint(1).status_code == 400
    assert client.post("/api/turns", json={"session_id": sid, "attempt": "Training is on seen data", "hint_level": 1}).status_code == 400
    assert client.post("/api/turns", json={"session_id": sid, "attempt": "Training is on seen data"}).status_code == 200
    assert hint(2).status_code == 200
    assert hint(3).status_code == 200
    assert hint(3).status_code == 400
    assert one("SELECT hint_count FROM sessions WHERE id=?", (sid,))["hint_count"] == 3


def test_student_restores_session_and_receives_faculty_grade(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(server.agents, "provider", Provider(live=False))
    server.save_question(server.Question(**question()), x_admin_password="test-admin")
    started = server.start_session(server.Start(student_id="anon010", mode="independent", course="ML", topic="General", question_id="ml-001"))
    sid = started["session_id"]
    assert server.student_sessions("anon010")[0]["id"] == sid
    assert server.student_session(sid)["finished"] is False
    server.submit(server.Submit(session_id=sid, answer="Validation on new data reveals whether training generalizes."))
    detail = server.session_details(sid, x_admin_password="test-admin")
    submission_id = detail["submissions"][0]["id"]
    server.faculty_grade(submission_id, server.Grade(score=91, feedback="Good comparison; discuss the size of the gap."), x_admin_password="test-admin")
    restored = server.student_session(sid)
    assert restored["finished"] is True
    assert restored["submission"]["faculty_score"] == 91
    assert "discuss the size" in restored["submission"]["feedback"]
    assert "ideal_answer" not in restored["submission"]
    assert "provisional_score" not in restored["submission"]
    with pytest.raises(HTTPException) as denied:
        server.delete_session(sid, x_admin_password="wrong")
    assert denied.value.status_code == 403
    assert server.delete_session(sid, x_admin_password="test-admin") == {"deleted": sid}
    assert server.student_sessions("anon010") == []
    assert one("SELECT * FROM submissions WHERE session_id=?", (sid,)) is None
    assert one("SELECT * FROM session_assessments WHERE session_id=?", (sid,)) is None
    guided = server.start_session(server.Start(student_id="anon010", mode="normal", course="ML", topic="General", question_id="ml-001"))
    server.turn(server.Turn(session_id=guided["session_id"], attempt="Training seems high but validation seems low."))
    resumed = server.student_session(guided["session_id"])
    assert resumed["attempts"][0]["student_text"] == "Training seems high but validation seems low."
    assert resumed["attempts"][0]["tutor_text"]
    server.submit(server.Submit(session_id=guided["session_id"], answer="Validation on new data checks generalization."))
    completed = server.student_session(guided["session_id"])
    assert completed["submission"]["ideal_answer"] == question()["ideal_answer"]


def test_separate_course_selection_and_question_coverage(tmp_path):
    created = server.save_course(server.Course(code="cns", name="Computer Network Security"), x_admin_password="test-admin")
    assert created["code"] == "CNS"
    note = tmp_path / "security.txt"
    note.write_text("Phishing uses deceptive messages to persuade people to reveal passwords. Password hygiene includes strong unique passphrases.")
    ingest(note, "CNS", "General", True)
    catalog = server.courses()
    cns = next(item for item in catalog if item["code"] == "CNS")
    assert cns["approved_notes"] == 1 and "General" in cns["topics"]
    assert server.course_coverage("CNS", "General", "What is phishing?")["matched"] is True
    assert server.course_coverage("CNS", "General", "What is packet spoofing?")["matched"] is False
    with pytest.raises(HTTPException) as unsupported:
        server.start_session(server.Start(student_id="anon011", mode="normal", course="CNS", topic="General", question="What is packet spoofing?"))
    assert unsupported.value.status_code == 409
    started = server.start_session(server.Start(student_id="anon011", mode="normal", course="CNS", topic="General", question="What is phishing?"))
    assert started["session_id"]
