import re
from app.retrieval import embed, similarity


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def concept_match(answer, alternatives):
    lower = answer.lower()
    return any(re.search(r"\b" + re.escape(term.lower()) + r"\b", lower) for term in alternatives)


def score(answer, rubric, ideal):
    if not rubric:
        return {"score": 0, "coverage": [], "uncertain": True, "method": "no rubric"}
    total = sum(float(item.get("weight", 0)) for item in rubric)
    if total <= 0:
        raise ValueError("Rubric weights must be positive")
    coverage = []
    found = 0.0
    for item in rubric:
        synonyms = item.get("accepted_concepts", [])
        criterion = item.get("criterion", "")
        matched = concept_match(answer, synonyms)
        lexical = similarity(embed(answer), embed(criterion + " " + " ".join(synonyms)))
        met = matched or lexical >= 0.50
        if met:
            found += float(item.get("weight", 0))
        coverage.append({"criterion": criterion, "met": met, "similarity": round(lexical, 3)})
    raw = 100 * found / total
    overall = similarity(embed(answer), embed(ideal))
    if raw >= 99 and overall < 0.30:
        raw = 85
    result = min(99, int(round(raw))) if raw >= 99 else int(round(raw))
    return {"score": result, "coverage": coverage, "uncertain": overall < 0.32 or 0 < result < 99, "method": "rubric aliases and hashed lexical vector similarity; provisional, not validated semantic grading"}


def validate_hint(response, level, ideal, evidence, earlier=(), question=""):
    candidate = response.strip()
    if not candidate or len(candidate) > (500 if level >= 2 else 450 if level == 1 else 350):
        return False, "empty_or_long"
    if "```" in candidate or re.search(r"\b(final answer|correct answer|the answer is|here is the solution)\b", candidate, re.I):
        return False, "direct_answer_format"
    if candidate.count("?") != 1 or not candidate.endswith("?"):
        return False, "one_question_only"
    question_part = candidate
    question_start = r"^(?:(?:given|based on) [^,]{1,100},\s*)?(what|which|how|why|where|when|can|could|would|do|does|is|are)\b"
    if not re.match(question_start, candidate, re.I):
        pieces = re.split(r"(?<=[.!])\s+", candidate, maxsplit=1)
        if len(pieces) != 2 or len(pieces[0]) > (260 if level >= 1 else 170):
            return False, "question_only"
        introduction, question_part = pieces
        if level == 0 and not introduction.lower().startswith(("not quite", "you're close", "you are close")):
            return False, "probe_must_not_explain"
        if not re.match(question_start, question_part, re.I):
            return False, "question_only"
    if re.search(r"\b(occurs when|means that|refers to|is when|be when|is the tendency|is a model that)\b", candidate, re.I):
        return False, "definition_leak"
    if level >= 1 and re.search(r"\b(which idea|which part|what evidence)\b.{0,55}\b(approved |course )?notes\b", candidate, re.I):
        return False, "vague_hint"
    named_subject = re.search(r"^\s*(?:what is|define)\s+([a-z][a-z-]+)", question, re.I)
    if named_subject and re.search(r"\b" + re.escape(named_subject.group(1)) + r"\s+(?:is|means|occurs|refers)\b", candidate, re.I):
        return False, "definition_leak"
    focus = words(question) - {"the", "and", "for", "how", "what", "why", "can", "does", "do", "is", "are", "it", "to", "of", "in", "on", "between", "difference", "explain", "machine", "learning", "model", "models", "data", "performance", "current"}
    required_focus = 2 if "difference between" in question.lower() and len(focus) >= 2 else 1
    focus_text = question_part if level == 0 else candidate
    if focus and len(focus.intersection(words(focus_text))) < required_focus:
        return False, "off_topic"
    note_terms = set().union(*(words(item.get("content", "")) for item in evidence)) if evidence else set()
    common = {"a", "about", "all", "an", "and", "are", "as", "at", "be", "by", "can", "course", "current", "data", "do", "does", "each", "example", "examples", "for", "from", "have", "how", "idea", "if", "in", "into", "is", "it", "its", "learning", "machine", "may", "model", "models", "notes", "of", "on", "or", "our", "part", "question", "reasoning", "student", "such", "than", "that", "the", "their", "them", "these", "this", "those", "through", "to", "use", "used", "what", "when", "where", "which", "while", "with", "would", "you", "your", "approved", "think"}
    anchors = note_terms - words(question) - common
    if anchors and not anchors.intersection(words(candidate)):
        return False, "not_grounded_in_notes"
    if level >= 1 and anchors and not (anchors.intersection(words(question_part)) or re.search(r"\b(that|those|these|it|this)\b", question_part, re.I)):
        return False, "question_drift"
    answer_terms = words(ideal) - {"the", "and", "this", "that", "with", "from", "would", "should", "because", "data", "model"}
    if level <= 1 and len(answer_terms & words(candidate)) >= max(4, int(0.75 * len(answer_terms))):
        return False, "answer_overlap"
    previous = [embed(item) for item in earlier if item]
    if previous and max(similarity(embed(candidate), item) for item in previous) > 0.84:
        return False, "repeated_question"
    if not evidence:
        return False, "no_approved_evidence"
    return True, "passed_heuristic_validation"


def has_reasoning(attempt, question):
    cleaned = attempt.strip().lower().replace("’", "'")
    if not cleaned or len(words(cleaned)) < 4:
        return False
    if cleaned.rstrip("?.!") == question.strip().lower().rstrip("?.!"):
        return False
    if re.search(r"\b(don'?t know|do not know|give me (the |an? )?answer|just tell me|give me a hint|hint please)\b", cleaned):
        return False
    tentative = cleaned.startswith(("does it mean", "is it", "could it be", "would it mean", "so does", "so is"))
    if cleaned.endswith("?") and not tentative and not any(mark in cleaned for mark in ("i think", "because", "maybe", "my idea")):
        return False
    return True


def grounded_scaffold(question, attempt, level, evidence, diagnosis=None):
    if level == 0 and diagnosis and diagnosis.get("student_state") == "incorrect":
        return "Not quite. " + safe_fallback(1, question, evidence)
    return safe_fallback(level, question, evidence)


def question_subject(question):
    named = re.search(r"\bwhat is\s+(?:a |an |the )?([A-Za-z][A-Za-z-]+)", question, re.I)
    if named:
        return named.group(1)
    focus = [word for word in re.findall(r"[A-Za-z][A-Za-z-]+", question) if word.lower() not in {"explain", "difference", "between", "what", "which", "about", "the", "and", "from", "with", "model", "performance", "why", "how", "does", "do", "is", "are", "on", "of", "to", "can", "you", "identify", "means"}]
    return " and ".join(focus[:2]) if focus else "this topic"


def safe_probe(question, previous_count=0):
    subject = question_subject(question)
    if previous_count == 0:
        return f"What do you think {subject} means in your own words?"
    if previous_count == 1:
        return f"Which part of {subject} is unclear to you?"
    return f"What is one observation or example you associate with {subject}?"


def safe_fallback(level, question="", evidence=()):
    subject = question_subject(question)
    if level == 0:
        return safe_probe(question)
    note_text = " ".join(item.get("content", "") for item in evidence)
    subject_word = subject.split()[0].lower()
    sentences = re.split(r"(?<=[.!?])\s+", note_text)
    relevant = next((sentence for sentence in sentences if re.search(r"\b" + re.escape(subject_word) + r"\b", sentence, re.I)), note_text)
    excluded = words(question) | {"about", "also", "because", "been", "being", "course", "could", "each", "example", "from", "have", "into", "more", "notes", "only", "other", "their", "them", "then", "there", "these", "this", "those", "through", "under", "using", "when", "where", "which", "while", "with", "would", "occurs", "means", "refers", "model", "models", "fits", "fails", "shows", "makes"}
    clues = [word for word in re.findall(r"[a-z]{4,}", relevant.lower()) if word not in excluded]
    anchor = " ".join(clues[:2]) if clues else None
    if anchor:
        if level == 1:
            return f"The notes connect {subject} with {anchor}. What might {anchor} tell you about {subject}?"
        if level == 2:
            return f"Consider how {anchor} relates to {subject}. What example would help you test your explanation?"
        return f"Use {anchor} as one clue from the notes. How would you now explain {subject} in your own words?"
    if level == 1:
        return f"What concrete example involving {subject} could help you start reasoning through this?"
    if level == 2:
        return f"What evidence in the approved notes about {subject} supports or challenges your explanation?"
    return f"How would you revise your explanation of {subject} using a specific example from the approved notes?"
