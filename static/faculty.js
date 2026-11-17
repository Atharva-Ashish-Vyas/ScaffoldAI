const el = id => document.getElementById(id);
const pw = () => el("password").value;
const PASSWORD_KEY = "scaffold_faculty_password_v1";
const SELECTED_KEY = "scaffold_faculty_selected_v1";
const DRAFT_KEY = "scaffold_faculty_draft_v1";
const PAGE_DRAFT_KEY = "scaffold_faculty_page_draft_v1";
let selectedSession = sessionStorage.getItem(SELECTED_KEY) || "";

function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).slice(1).join(" → ")}: ${item.msg || "Invalid value"}`).join("; ");
  return detail?.message || "Request failed";
}

async function req(url, method = "GET", body, form = false) {
  const options = {method, headers: {"X-Admin-Password": pw()}};
  if (body !== undefined) {
    options.body = form ? body : JSON.stringify(body);
    if (!form) options.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); }
  catch { data = {}; }
  if (!response.ok) throw Error(errorMessage(data.detail));
  return data;
}

function itemBox(textValue) {
  const box = document.createElement("div");
  box.className = "item";
  const text = document.createElement("span");
  text.textContent = textValue;
  box.append(text);
  return box;
}

function showUnderstanding(detail) {
  const panel = el("understanding");
  panel.replaceChildren();
  const result = detail.understanding;
  const title = document.createElement("strong");
  title.textContent = result?.understanding_score == null ? "Understanding score unavailable" : `Provisional understanding: ${result.understanding_score}/100`;
  const explanation = document.createElement("span");
  explanation.textContent = result
    ? `Answer: ${result.answer_score ?? "—"}/100 · Reasoning: ${result.reasoning_score ?? "not observed"}${result.reasoning_score == null ? "" : "/100"} · Confidence: ${result.confidence}\n${result.rationale}\nFaculty review required.`
    : "The score appears after the student submits a final answer.";
  panel.append(title, explanation);
}

function saveDraft() {
  if (!selectedSession) return;
  sessionStorage.setItem(DRAFT_KEY, JSON.stringify({session_id: selectedSession, score: el("facultyScore").value, feedback: el("feedback").value}));
}

function savePageDraft() {
  sessionStorage.setItem(PAGE_DRAFT_KEY, JSON.stringify({course: el("course").value, topic: el("topic").value, questionCourse: el("questionCourse").value, questionTopic: el("questionTopic").value, questionJson: el("questionJson").value}));
}

async function inspectSession(id) {
  const detail = await req(`/api/admin/sessions/${encodeURIComponent(id)}`);
  selectedSession = id;
  sessionStorage.setItem(SELECTED_KEY, id);
  el("details").textContent = JSON.stringify(detail, null, 2);
  el("details").closest("details").open = true;
  showUnderstanding(detail);
  const submission = detail.submissions?.[0];
  el("reassess").disabled = !submission;
  el("submissionId").value = submission?.id || "";
  const draft = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null");
  el("facultyScore").value = draft?.session_id === id ? draft.score : submission?.faculty_score ?? "";
  el("feedback").value = draft?.session_id === id ? draft.feedback : submission?.feedback || "";
  el("gradeStatus").textContent = submission ? "" : "This session has no submitted answer yet.";
}

function renderNotes(notes) {
  el("notes").replaceChildren();
  notes.forEach(item => {
    const box = itemBox(`${item.filename} · ${item.course}/${item.topic} · ${item.chunks} chunks · ${item.approved ? "Approved" : "Unapproved"}`);
    const button = document.createElement("button");
    button.textContent = item.approved ? "Revoke" : "Approve";
    button.onclick = async () => {
      try { await req(`/api/admin/notes/${item.id}/approval?approved=${!item.approved}`, "POST"); await load(); }
      catch (error) { el("status").textContent = error.message; }
    };
    box.append(button); el("notes").append(box);
  });
}

function renderQuestions(questions) {
  el("questions").replaceChildren();
  questions.forEach(item => {
    const box = itemBox(`${item.id}: ${item.question} · ${item.approved ? "Approved" : "Draft"}`);
    const button = document.createElement("button");
    button.textContent = item.approved ? "Revoke" : "Approve";
    button.onclick = async () => {
      try { await req(`/api/admin/questions/${encodeURIComponent(item.id)}/approval?approved=${!item.approved}`, "POST"); await load(); }
      catch (error) { el("status").textContent = error.message; }
    };
    box.append(button); el("questions").append(box);
  });
}

function renderDatasets(datasets) {
  el("datasets").replaceChildren();
  datasets.forEach(item => {
    const card = document.createElement("div"); card.className = "dataset-card";
    const name = document.createElement("strong"); name.textContent = item.dataset;
    const count = document.createElement("span"); count.textContent = `${item.imported_records} imported records`;
    const safe = document.createElement("span"); safe.textContent = `${item.safe_probing_examples} probing · ${item.safe_hint_examples} hint examples`;
    card.append(name, count, safe); el("datasets").append(card);
  });
}

function renderCourses(courses) {
  let pageDraft = null;
  try { pageDraft = JSON.parse(sessionStorage.getItem(PAGE_DRAFT_KEY) || "null"); }
  catch { pageDraft = null; }
  const savedCourse = pageDraft?.course || "";
  const selected = el("course").value || savedCourse || "ML";
  el("course").replaceChildren(...courses.map(course => new Option(`${course.code} · ${course.name}`, course.code)));
  el("course").value = courses.some(course => course.code === selected) ? selected : courses[0]?.code || "";
  const selectedQuestionCourse = el("questionCourse").value || pageDraft?.questionCourse || "ML";
  el("questionCourse").replaceChildren(...courses.map(course => new Option(`${course.code} · ${course.name}`, course.code)));
  el("questionCourse").value = courses.some(course => course.code === selectedQuestionCourse) ? selectedQuestionCourse : courses[0]?.code || "";
  el("courses").replaceChildren();
  courses.forEach(course => {
    const box = itemBox(`${course.code} · ${course.name} · ${course.approved_notes} approved note${course.approved_notes === 1 ? "" : "s"} · Topics: ${course.topics.join(", ")}`);
    const select = document.createElement("button");
    select.type = "button"; select.textContent = "Use for upload";
    select.onclick = () => { el("course").value = course.code; savePageDraft(); el("notes-section").scrollIntoView({behavior: "smooth"}); };
    box.append(select); el("courses").append(box);
  });
}

function renderSessions(sessions) {
  el("sessions").replaceChildren();
  sessions.forEach(item => {
    const box = itemBox(`${item.student_id} · ${item.mode} · ${item.topic} · ${item.question.slice(0, 55)}`);
    const badge = document.createElement("span");
    badge.className = "score-badge";
    badge.textContent = item.understanding_score == null ? "Understanding: pending" : `Understanding: ${item.understanding_score}/100`;
    const actions = document.createElement("span"); actions.className = "item-actions";
    const inspect = document.createElement("button"); inspect.textContent = "Inspect";
    inspect.onclick = () => inspectSession(item.id).catch(error => el("gradeStatus").textContent = error.message);
    const remove = document.createElement("button"); remove.className = "delete-session"; remove.textContent = "Delete";
    remove.onclick = async () => {
      if (!window.confirm(`Delete this session for ${item.student_id}? Its conversation, submission, and scores will be removed.`)) return;
      try {
        await req(`/api/admin/sessions/${encodeURIComponent(item.id)}`, "DELETE");
        if (selectedSession === item.id) {
          selectedSession = "";
          sessionStorage.removeItem(SELECTED_KEY);
          sessionStorage.removeItem(DRAFT_KEY);
          el("details").textContent = "Select a session to inspect it.";
          el("understanding").textContent = "Select a session to see its provisional understanding score.";
          el("submissionId").value = ""; el("facultyScore").value = ""; el("feedback").value = "";
          el("reassess").disabled = true;
        }
        await load();
        el("gradeStatus").textContent = "Session deleted.";
      } catch (error) { el("gradeStatus").textContent = error.message; }
    };
    actions.append(inspect, remove); box.append(badge, actions); el("sessions").append(box);
  });
}

async function load() {
  if (!pw()) { el("status").textContent = "Enter the faculty password first."; return; }
  try {
    const [courses, notes, questions, datasets, sessions] = await Promise.all([
      req("/api/courses"), req("/api/admin/notes"), req("/api/admin/questions"), req("/api/admin/datasets"), req("/api/admin/sessions")
    ]);
    sessionStorage.setItem(PASSWORD_KEY, pw());
    renderCourses(courses); renderNotes(notes); renderQuestions(questions); renderDatasets(datasets); renderSessions(sessions);
    el("status").textContent = "Dashboard loaded";
    if (selectedSession && sessions.some(item => item.id === selectedSession)) await inspectSession(selectedSession);
  } catch (error) { el("status").textContent = error.message; }
}

el("load").onclick = load;
el("password").addEventListener("change", () => sessionStorage.setItem(PASSWORD_KEY, pw()));
el("facultyScore").addEventListener("input", saveDraft);
el("feedback").addEventListener("input", saveDraft);
["course", "topic", "questionCourse", "questionTopic", "questionJson"].forEach(id => el(id).addEventListener("input", savePageDraft));

el("newCourse").onsubmit = async event => {
  event.preventDefault();
  try {
    const created = await req("/api/admin/courses", "POST", {code: el("newCourseCode").value, name: el("newCourseName").value});
    await load();
    el("course").value = created.code;
    el("questionCourse").value = created.code;
    savePageDraft();
    el("status").textContent = `${created.code} is ready. Upload and approve its lecture notes below.`;
  } catch (error) { el("status").textContent = error.message; }
};

el("upload").onsubmit = async event => {
  event.preventDefault();
  const file = el("file").files[0];
  if (!file) { el("status").textContent = "Choose a course file first."; return; }
  const form = new FormData();
  form.set("file", file); form.set("course", el("course").value); form.set("topic", el("topic").value);
  try { await req("/api/admin/notes/upload", "POST", form, true); el("status").textContent = "Note uploaded. Review and approve it below."; await load(); }
  catch (error) { el("status").textContent = error.message; }
};

el("saveQuestion").onclick = async () => {
  try {
    const value = JSON.parse(el("questionJson").value);
    value.course = el("questionCourse").value;
    value.topic = el("questionTopic").value.trim() || "General";
    await req("/api/admin/questions", "POST", value);
    await load(); el("status").textContent = `Question saved under ${value.course}/${value.topic}.`;
  }
  catch (error) { el("status").textContent = error.message; }
};

el("grade").onclick = async () => {
  const submissionId = Number(el("submissionId").value);
  const rawScore = el("facultyScore").value.trim();
  const score = Number(rawScore);
  if (!Number.isInteger(submissionId) || submissionId <= 0) { el("gradeStatus").textContent = "Select a submitted session before grading."; return; }
  if (!rawScore || !Number.isFinite(score) || score < 0 || score > 100) { el("gradeStatus").textContent = "Enter a faculty score from 0 to 100."; el("facultyScore").focus(); return; }
  try {
    await req(`/api/admin/submissions/${submissionId}/grade`, "POST", {score, feedback: el("feedback").value});
    sessionStorage.removeItem(DRAFT_KEY);
    await load();
    el("gradeStatus").textContent = `Faculty score ${score}/100 and remarks saved. The student can now view them.`;
  } catch (error) { el("gradeStatus").textContent = error.message; }
};

el("reassess").onclick = async () => {
  if (!selectedSession) return;
  const button = el("reassess");
  button.disabled = true;
  el("gradeStatus").textContent = "Regenerating the model explanation from the student's answer and approved notes…";
  try {
    await req(`/api/admin/sessions/${encodeURIComponent(selectedSession)}/reassess`, "POST");
    await load();
    el("gradeStatus").textContent = "Model explanation regenerated. Your faculty score and remarks were kept.";
  } catch (error) { el("gradeStatus").textContent = error.message; }
  finally { button.disabled = !el("submissionId").value; }
};

el("export").onclick = async () => {
  try {
    const response = await fetch("/api/admin/export.csv", {headers: {"X-Admin-Password": pw()}});
    if (!response.ok) throw Error("Export failed. Check faculty access.");
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "scaffoldai_anonymous_export.csv"; anchor.click();
    URL.revokeObjectURL(url);
  } catch (error) { el("status").textContent = error.message; }
};

el("password").value = sessionStorage.getItem(PASSWORD_KEY) || "";
try {
  const draft = JSON.parse(sessionStorage.getItem(PAGE_DRAFT_KEY) || "null");
  if (draft) { el("course").value = draft.course || "ML"; el("topic").value = draft.topic || "General"; el("questionCourse").value = draft.questionCourse || "ML"; el("questionTopic").value = draft.questionTopic || "General"; el("questionJson").value = draft.questionJson || el("questionJson").value; }
} catch { sessionStorage.removeItem(PAGE_DRAFT_KEY); }
if (pw()) load();
