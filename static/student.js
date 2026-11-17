const el = id => document.getElementById(id);
const PROFILE_KEY = "scaffold_profiles_v1";
const ACTIVE_PROFILE_KEY = "scaffold_active_profile_v1";
const SESSION_KEY = "scaffold_profile_sessions_v1";
const SETUP_KEY = "scaffold_profile_setup_v1";
let active = null;
let hintsUsed = 0;
let maxHints = 3;
let busy = false;
let viewToken = 0;
let courseCatalog = [];
let refreshingOnReturn = false;

function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

function errorMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).slice(1).join(" → ")}: ${item.msg || "Invalid value"}`).join("; ");
  return detail?.message || "Request failed";
}

async function api(url, method = "GET", data) {
  const response = await fetch(url, {
    method,
    headers: data === undefined ? {} : {"Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const payload = await response.json();
  if (!response.ok) throw Error(errorMessage(payload.detail));
  return payload;
}

function profileId() { return el("student").value.trim(); }
function sessionMap() { return readStored(SESSION_KEY, {}); }
function saveSetup() {
  const drafts = readStored(SETUP_KEY, {});
  drafts[profileId()] = {mode: el("mode").value, course: el("course").value, topic: el("topic").value, question_id: el("questions").value, question: el("question").value};
  localStorage.setItem(SETUP_KEY, JSON.stringify(drafts));
}
function restoreSetup(id) {
  const draft = readStored(SETUP_KEY, {})[id];
  if (!draft) return null;
  el("mode").value = draft.mode || "normal";
  el("question").value = draft.question || "";
  syncMode();
  return draft;
}
function rememberSession(id) {
  const map = sessionMap();
  if (id) map[profileId()] = id;
  else delete map[profileId()];
  localStorage.setItem(SESSION_KEY, JSON.stringify(map));
}

function addProfile(id) {
  const profiles = readStored(PROFILE_KEY, []);
  if (!profiles.includes(id)) profiles.push(id);
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profiles));
  localStorage.setItem(ACTIVE_PROFILE_KEY, id);
  el("student").value = id;
  el("profiles").replaceChildren(...profiles.map(item => new Option(item, item)));
  el("profiles").value = id;
}

function bubble(role, message, sources = []) {
  const node = document.createElement("div");
  node.className = "bubble " + role;
  node.textContent = (role === "student" ? "STUDENT\n" : "SCAFFOLDAI\n") + message;
  if (sources.length) {
    const references = document.createElement("div");
    references.className = "sources";
    references.textContent = "Sources: " + sources.map(item => `${item.file}, p./slide ${item.page}`).join("; ");
    node.append(references);
  }
  el("conversation").append(node);
  el("conversation").scrollTop = el("conversation").scrollHeight;
  return node;
}

function syncMode() {
  const mode = el("mode").value;
  document.querySelectorAll(".mode-card").forEach(card => {
    const selected = card.dataset.mode === mode;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-checked", String(selected));
  });
  el("customQuestionLabel").hidden = mode !== "normal";
  el("questions").options[0].disabled = mode !== "normal";
  if (mode !== "normal" && !el("questions").value) el("sessionStatus").textContent = "Select a faculty-approved question for this mode";
  else el("sessionStatus").textContent = "";
}

async function loadQuestions(selected = el("questions").value) {
  const questions = await api(`/api/questions?course=${encodeURIComponent(el("course").value)}&topic=${encodeURIComponent(el("topic").value)}`);
  el("questions").replaceChildren(new Option("Custom question (Guided learning only)", ""));
  questions.forEach(item => el("questions").add(new Option(item.question, item.id)));
  el("questions").value = selected || "";
  syncMode();
}

async function loadCourses(selected = el("course").value || "ML") {
  courseCatalog = await api("/api/courses");
  el("course").replaceChildren(...courseCatalog.map(course => new Option(`${course.code} · ${course.name}`, course.code)));
  el("course").value = courseCatalog.some(course => course.code === selected) ? selected : courseCatalog[0]?.code || "";
  return courseCatalog.find(course => course.code === el("course").value);
}

function loadTopics(selected = "General") {
  const course = courseCatalog.find(item => item.code === el("course").value);
  const topics = course?.topics || ["General"];
  el("topic").replaceChildren(...topics.map(topic => new Option(topic, topic)));
  el("topic").value = topics.includes(selected) ? selected : topics[0];
  el("courseStatus").textContent = course ? `${course.name}: ${course.approved_notes} approved note${course.approved_notes === 1 ? "" : "s"}. Available topics: ${topics.join(", ")}.` : "Ask faculty to add a course and approve notes.";
}

function currentQuestion() {
  return el("questions").selectedOptions[0]?.value ? el("questions").selectedOptions[0].textContent : el("question").value.trim();
}

async function refreshCoverage(question = currentQuestion()) {
  const label = el("coverageStatus");
  label.classList.remove("covered", "uncovered");
  if (!el("course").value || !el("topic").value) { label.textContent = "Select a course and topic."; return false; }
  const data = await api(`/api/coverage?course=${encodeURIComponent(el("course").value)}&topic=${encodeURIComponent(el("topic").value)}&question=${encodeURIComponent(question)}`);
  if (!data.approved_notes) {
    label.textContent = "No approved notes for this course and topic. Ask faculty to upload and approve them.";
    label.classList.add("uncovered");
    return false;
  }
  if (!question) { label.textContent = `${data.approved_notes} approved note${data.approved_notes === 1 ? "" : "s"} available. Enter a question to check coverage.`; return true; }
  if (!data.matched) {
    label.textContent = "No matching passage in these approved notes. Try a covered concept or ask faculty to upload relevant slides.";
    label.classList.add("uncovered");
    return false;
  }
  label.textContent = `Found in ${data.sources.map(source => `${source.file}, slide/page ${source.page}`).join("; ")}.`;
  label.classList.add("covered");
  return true;
}

function updateControls() {
  const usable = active && !active.finished;
  const hintAvailable = usable && active.mode !== "independent" && hintsUsed < maxHints;
  el("send").hidden = !!active && active.mode !== "normal";
  el("send").disabled = busy || !usable || active.mode !== "normal";
  el("hint").hidden = !!active && active.mode === "independent";
  el("hint").disabled = busy || !hintAvailable;
  el("hint").textContent = hintAvailable ? `Ask for hint · Level ${hintsUsed + 1}` : "No more hints available";
  el("submit").disabled = busy || !usable;
  el("hintStatus").hidden = !!active && active.mode === "independent";
  el("hintStatus").textContent = `Hints used: ${hintsUsed} of ${maxHints}. Each level is available once.`;
  el("attempt").readOnly = !!active?.finished;
  el("attempt").setAttribute("aria-busy", String(busy));
}

function showFacultyFeedback(submission) {
  el("facultyFeedback").hidden = !active?.finished;
  if (!active?.finished) return;
  if (submission?.faculty_score != null) {
    el("facultyScoreLabel").textContent = `Faculty score: ${submission.faculty_score}/100`;
    el("facultyRemarks").textContent = submission.feedback?.trim() || "No remarks were added.";
  } else {
    el("facultyScoreLabel").textContent = "Faculty evaluation pending";
    el("facultyRemarks").textContent = "Your teacher has not graded this answer yet.";
  }
}

function clearPractice() {
  active = null;
  viewToken++;
  el("practice").hidden = true;
  el("welcome").hidden = false;
  el("facultyFeedback").hidden = true;
  el("result").textContent = "";
  el("attempt").value = "";
  updateControls();
}

async function renderSession(info, scroll = false) {
  active = info;
  hintsUsed = info.hint_count || 0;
  maxHints = info.max_hints || 0;
  if (!readStored(SETUP_KEY, {})[profileId()]) {
    await loadCourses(info.course);
    loadTopics(info.topic);
    el("mode").value = info.mode;
    await loadQuestions(info.question_id || "");
    el("question").value = info.question_id ? "" : info.question;
    saveSetup();
  }
  el("practice").hidden = false;
  el("welcome").hidden = true;
  el("practiceTitle").textContent = info.question;
  el("sessionMode").textContent = info.mode === "independent" ? "INDEPENDENT Q&A" : info.mode === "exam" ? "EXAM PRACTICE" : "GUIDED LEARNING";
  el("sessionTag").textContent = info.finished ? "Completed session" : "Active session";
  const modeNotice = info.mode === "independent" ? "No AI assistance or feedback is shown during the attempt." : info.mode === "exam" ? "Only faculty-approved hints are shown during the attempt." : "Guided learning; study scores are provisional.";
  el("modeNotice").textContent = `${info.course} / ${info.topic} · ${modeNotice}`;
  el("conversation").replaceChildren();
  (info.attempts || []).forEach(item => {
    bubble("student", item.student_text);
    bubble("tutor", item.tutor_text, item.sources || []);
  });
  if (info.finished) {
    el("attempt").value = info.submission?.answer || "";
    const lines = ["Final answer submitted for evaluation."];
    if (info.mode === "normal" && info.submission?.provisional_score != null) lines.push(`Provisional answer score: ${info.submission.provisional_score}/100`);
    if (info.submission?.ideal_answer) lines.push(`Ideal answer: ${info.submission.ideal_answer}`);
    if (info.submission?.coverage?.length) lines.push(`Rubric coverage: ${JSON.stringify(info.submission.coverage)}`);
    el("result").textContent = lines.join("\n");
  } else {
    el("attempt").value = localStorage.getItem(`scaffold_attempt_${info.session_id}`) || "";
    el("result").textContent = "";
  }
  showFacultyFeedback(info.submission);
  updateControls();
  if (scroll) el("practice").scrollIntoView({behavior: "smooth", block: "start"});
}

async function restoreSession(id, scroll = false) {
  if (!id || busy) return;
  const token = ++viewToken;
  try {
    const info = await api(`/api/sessions/${encodeURIComponent(id)}`);
    if (token !== viewToken || info.student_id !== profileId()) return;
    await renderSession(info, scroll);
    rememberSession(id);
  } catch (error) {
    if (token !== viewToken) return;
    el("sessionStatus").textContent = error.message;
    if (error.message === "Session not found") { rememberSession(null); clearPractice(); await loadSessionList(); }
  }
}

async function loadSessionList(preferred = sessionMap()[profileId()]) {
  try {
    const sessions = await api(`/api/student/sessions?student_id=${encodeURIComponent(profileId())}`);
    el("savedSessions").replaceChildren(new Option("Choose a saved session", ""));
    sessions.forEach(item => el("savedSessions").add(new Option(`${item.finished ? "✓ " : "● "}${item.question.slice(0, 50)} · ${item.mode} · ${item.created_at}`, item.id)));
    const chosen = sessions.some(item => item.id === preferred) ? preferred : sessions[0]?.id;
    el("savedSessions").value = chosen || "";
    if (chosen) await restoreSession(chosen);
    else { rememberSession(null); clearPractice(); }
  } catch (error) { el("sessionStatus").textContent = error.message; }
}

async function useProfile(id) {
  if (!id) return;
  addProfile(id);
  clearPractice();
  const draft = restoreSetup(id);
  await loadCourses(draft?.course || "ML");
  loadTopics(draft?.topic || "General");
  await loadQuestions(draft?.question_id || "");
  refreshCoverage().catch(() => {});
  await loadSessionList();
  el("refresh").click();
}

async function sendTurn(requestHint) {
  if (!active || active.finished || busy) return;
  const text = el("attempt").value.trim();
  if (!requestHint && !text) { el("result").textContent = "Enter your reasoning first, or use Ask for hint."; return; }
  if (requestHint && hintsUsed >= maxHints) return;
  const level = requestHint ? hintsUsed + 1 : 0;
  const studentBubble = bubble("student", requestHint ? `Hint request · Level ${level}${text ? "\n" + text : ""}` : text);
  const pending = bubble("tutor", "Working through your question and course notes…");
  el("result").textContent = "";
  busy = true; updateControls();
  try {
    const data = await api("/api/turns", "POST", {session_id: active.session_id, attempt: text, hint_level: level, request_hint: requestHint});
    pending.remove();
    bubble("tutor", data.reply, data.sources || []);
    active.attempts = active.attempts || [];
    active.attempts.push({student_text: requestHint ? "Hint requested" : text, tutor_text: data.reply, sources: data.sources || []});
    if (requestHint) { hintsUsed = data.hint_level; active.hint_count = hintsUsed; }
    else { el("attempt").value = ""; localStorage.removeItem(`scaffold_attempt_${active.session_id}`); }
  } catch (error) {
    studentBubble.remove(); pending.remove();
    el("result").textContent = error.message;
  } finally { busy = false; updateControls(); }
}

document.querySelectorAll(".mode-card").forEach(card => card.addEventListener("click", () => { el("mode").value = card.dataset.mode; syncMode(); saveSetup(); }));
el("mode").addEventListener("change", () => { syncMode(); saveSetup(); });
el("questions").addEventListener("change", () => { syncMode(); saveSetup(); refreshCoverage().catch(error => el("coverageStatus").textContent = error.message); });
el("course").addEventListener("change", () => {
  loadTopics(); saveSetup();
  loadQuestions("").then(() => refreshCoverage()).catch(error => el("sessionStatus").textContent = error.message);
});
el("topic").addEventListener("change", () => {
  saveSetup(); loadQuestions("").then(() => refreshCoverage()).catch(error => el("sessionStatus").textContent = error.message);
});
el("question").addEventListener("input", () => { saveSetup(); el("coverageStatus").textContent = "Check note coverage before starting."; el("coverageStatus").classList.remove("covered", "uncovered"); });
el("checkCoverage").onclick = () => refreshCoverage().catch(error => el("coverageStatus").textContent = error.message);
el("profiles").addEventListener("change", () => useProfile(el("profiles").value));
el("student").addEventListener("change", () => useProfile(profileId()));
el("newProfile").onclick = () => {
  const id = `student-${(globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)).slice(0, 8)}`;
  useProfile(id);
  el("sessionStatus").textContent = `New profile ${id} created. Start a session when ready.`;
};
el("savedSessions").addEventListener("change", () => { if (el("savedSessions").value) restoreSession(el("savedSessions").value, true); });
el("attempt").addEventListener("input", () => { if (active && !active.finished) localStorage.setItem(`scaffold_attempt_${active.session_id}`, el("attempt").value); });

el("start").onclick = async () => {
  const id = profileId();
  if (!id) { el("sessionStatus").textContent = "Enter an anonymous student ID."; return; }
  addProfile(id);
  saveSetup();
  try {
    const info = await api("/api/sessions", "POST", {student_id: id, mode: el("mode").value, course: el("course").value, topic: el("topic").value, question_id: el("questions").value || null, question: el("question").value});
    rememberSession(info.session_id);
    await loadSessionList(info.session_id);
    el("sessionStatus").textContent = "New session started";
    el("practice").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) { el("sessionStatus").textContent = error.message; }
};

el("send").onclick = () => sendTurn(false);
el("hint").onclick = () => sendTurn(true);
el("submit").onclick = async () => {
  if (!active || active.finished || busy) return;
  const answer = el("attempt").value.trim();
  if (!answer) { el("result").textContent = "Enter your final answer before submitting."; return; }
  busy = true; updateControls();
  el("result").textContent = "Reviewing your final answer…";
  try {
    const data = await api("/api/submissions", "POST", {session_id: active.session_id, answer});
    active.finished = true;
    active.submission = {answer, provisional_score: data.provisional_score, faculty_score: null, feedback: null};
    el("sessionTag").textContent = "Completed session";
    const lines = [data.message];
    if (data.provisional_score != null) lines.push(`Provisional answer score: ${data.provisional_score}/100`);
    if (data.ideal_answer) lines.push(`Ideal answer: ${data.ideal_answer}`);
    if (data.coverage?.length) lines.push(`Rubric coverage: ${JSON.stringify(data.coverage)}`);
    el("result").textContent = lines.join("\n");
    localStorage.removeItem(`scaffold_attempt_${active.session_id}`);
    showFacultyFeedback(active.submission);
    await loadSessionList(active.session_id);
  } catch (error) { el("result").textContent = error.message; }
  finally { busy = false; updateControls(); }
};

el("checkFeedback").onclick = () => { if (active) restoreSession(active.session_id); };
el("refresh").onclick = async () => {
  try {
    const data = await api("/api/progress/" + encodeURIComponent(profileId()));
    const scores = data.study_scores.filter(item => typeof item === "number");
    el("progress").replaceChildren();
    const stats = document.createElement("div"); stats.className = "progress-stats";
    for (const [label, value] of [["Sessions", data.sessions.length], ["Completed", data.sessions.filter(item => item.finished).length], ["Study scores", scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) + "/100" : "—"]]) {
      const tile = document.createElement("div"); tile.className = "progress-stat";
      const count = document.createElement("strong"); count.textContent = value;
      tile.append(count, label); stats.append(tile);
    }
    el("progress").append(stats);
  } catch (error) { el("progress").textContent = error.message; }
};

async function refreshOnReturn() {
  if (refreshingOnReturn || busy) return;
  refreshingOnReturn = true;
  try {
    const course = el("course").value;
    const topic = el("topic").value;
    const selectedQuestion = el("questions").value;
    await loadCourses(course);
    loadTopics(topic);
    await loadQuestions(selectedQuestion);
    await refreshCoverage();
    if (active) await restoreSession(active.session_id);
  } catch (error) { el("sessionStatus").textContent = error.message; }
  finally { refreshingOnReturn = false; }
}
window.addEventListener("focus", refreshOnReturn);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshOnReturn(); });

const initialProfile = localStorage.getItem(ACTIVE_PROFILE_KEY) || "student001";
addProfile(initialProfile);
const initialDraft = restoreSetup(initialProfile);
syncMode();
loadCourses(initialDraft?.course || "ML")
  .then(() => loadTopics(initialDraft?.topic || "General"))
  .then(() => loadQuestions(initialDraft?.question_id || ""))
  .then(() => refreshCoverage())
  .then(() => loadSessionList())
  .then(() => el("refresh").click())
  .catch(error => el("sessionStatus").textContent = error.message);
