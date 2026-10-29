"""Pure logic for LogicLab AI: grading, progress stats, recommendations, Gemini helpers.

Kept free of Streamlit so it can be unit-tested.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from examples_data import EXAMPLES, PRACTICE_EXTRAS, TOPICS, CONCEPT_NOTES

EXAMPLES_BY_ID = {e["id"]: e for e in EXAMPLES}
PROGRESS_FILE = Path(__file__).parent / "progress.json"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_MS = 30_000
GEMINI_MODEL_FALLBACKS = (
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
DIFFICULTIES = {
    "Low": "Beginner",
    "Medium": "Intermediate",
    "Hard": "Advanced",
}


# ---------- Deterministic grading ----------
def normalize_output(text: str) -> str:
    """Normalize program output for comparison: trim, collapse spaces per line, drop blank edge lines."""
    if text is None:
        return ""
    text = text.replace("\r\n", "\n").replace("\\n", "\n")
    lines = [" ".join(line.split()) for line in text.strip().split("\n")]
    lines = [l for l in lines if l != ""]
    norm = "\n".join(lines)
    # Treat a smart quote the same as a plain quote (phones auto-insert these).
    return norm.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')


def check_answer(user_answer: str, expected: str) -> bool:
    return normalize_output(user_answer) == normalize_output(expected)


# ---------- Progress ----------
def empty_progress() -> dict:
    return {"attempts": []}


def load_progress() -> dict:
    try:
        if PROGRESS_FILE.exists():
            data = json.loads(PROGRESS_FILE.read_text())
            if isinstance(data, dict) and isinstance(data.get("attempts"), list):
                return data
    except Exception:
        pass
    return empty_progress()


def save_progress(progress: dict) -> None:
    try:
        PROGRESS_FILE.write_text(json.dumps(progress, indent=2))
    except Exception:
        pass  # read-only hosting: progress still lives in session state


def record_attempt(progress: dict, qid: str, topic: str, correct: bool, source: str) -> None:
    progress["attempts"].append({"id": qid, "topic": topic, "correct": bool(correct), "source": source})


def compute_stats(progress: dict) -> dict:
    attempts = progress.get("attempts", [])
    total = len(attempts)
    correct = sum(1 for a in attempts if a["correct"])
    unique = {a["id"] for a in attempts}
    solved = {a["id"] for a in attempts if a["correct"]}
    per_topic = {}
    for t in TOPICS:
        ta = [a for a in attempts if a["topic"] == t]
        c = sum(1 for a in ta if a["correct"])
        per_topic[t] = {"attempts": len(ta), "correct": c, "accuracy": (c / len(ta)) if ta else None}
    tried = {t: v for t, v in per_topic.items() if v["attempts"]}
    strengths = [t for t, v in tried.items() if v["accuracy"] >= 0.75]
    weaknesses = [t for t, v in tried.items() if v["accuracy"] < 0.6]
    return {
        "total_attempts": total,
        "correct": correct,
        "accuracy": (correct / total) if total else 0.0,
        "unique_attempted": len(unique),
        "solved": solved,
        "attempted_ids": unique,
        "per_topic": per_topic,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


def recommend_examples(progress: dict, limit: int = 3) -> list[dict]:
    """Weak topics first, then untouched topics; never recommend already-solved examples."""
    stats = compute_stats(progress)
    solved = stats["solved"]
    pt = stats["per_topic"]

    def topic_priority(t):
        v = pt[t]
        if v["attempts"] and v["accuracy"] < 1.0:
            return (0, v["accuracy"])
        if not v["attempts"]:
            return (1, 0)
        return (2, 0)

    ordered_topics = sorted(TOPICS, key=topic_priority)
    recs = []
    for t in ordered_topics:
        for e in EXAMPLES:
            if e["topic"] == t and e["id"] not in solved and e not in recs:
                recs.append(e)
                break
        if len(recs) >= limit:
            break
    if len(recs) < limit:
        for e in EXAMPLES:
            if e["id"] not in solved and e not in recs:
                recs.append(e)
            if len(recs) >= limit:
                break
    return recs[:limit]


def filter_examples(query: str = "", topic: str = "All", level: str = "All") -> list[dict]:
    q = (query or "").strip().lower()
    out = []
    for e in EXAMPLES:
        if topic != "All" and e["topic"] != topic:
            continue
        if level != "All" and e["level"] != level:
            continue
        hay = " ".join([e["title"], e["description"], e["topic"], e["code"]]).lower()
        if q and q not in hay:
            continue
        out.append(e)
    return out


def build_quiz(topic: str, size: int = 5, difficulty: str | None = None) -> list[dict]:
    """Build a quiz, optionally limited to built-in questions matching a difficulty."""
    if difficulty is not None:
        examples = sample_questions(topic, difficulty, size)
        return [
            {
                "id": question["id"],
                "topic": topic,
                "question": question["question"],
                "code": question.get("code"),
                "choices": question["choices"],
                "answer": question["answer"],
                "explanation": (
                    " ".join(question["explanation"])
                    if isinstance(question["explanation"], list)
                    else question["explanation"]
                ),
            }
            for question in examples
        ]

    # Keep the existing five-question sample quiz for callers without a difficulty.
    qs = []
    for e in EXAMPLES:
        if e["topic"] == topic:
            qs.append({"id": e["id"], "topic": topic, "question": e["question"], "code": e["code"],
                       "choices": e["choices"], "answer": e["answer"],
                       "explanation": " ".join(e["explanation"])})
    for x in PRACTICE_EXTRAS:
        if x["topic"] == topic:
            qs.append({**x, "code": None})
    return qs[:size]


# ---------- Gemini (optional) ----------
def get_api_key(visitor_key: str | None = None, personal_only: bool = False) -> str | None:
    if visitor_key is None:
        try:
            import streamlit as st
            visitor_key = st.session_state.get("visitor_gemini_api_key")
        except Exception:
            visitor_key = None
    if visitor_key and visitor_key.strip():
        return visitor_key.strip()
    if personal_only:
        return None

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key.strip() or None
    try:
        import streamlit as st  # secrets.toml support
        secret = st.secrets.get("GEMINI_API_KEY")  # type: ignore[attr-defined]
        return secret.strip() or None if isinstance(secret, str) else None
    except Exception:
        return None


def gemini_available() -> bool:
    if not get_api_key():
        return False
    try:
        from google import genai  # noqa: F401
        return True
    except Exception:
        return False


SYSTEM_PROMPT = (
    "You are LogicLab AI, a patient Python tutor for absolute beginners. "
    "Use simple English, short sentences, and small examples. Never ask the student to run code. "
    "Keep answers under 180 words unless asked for more."
)


def _gemini_error_reason(exc: Exception) -> str:
    """Explain common Gemini failures without exposing raw server text or credentials."""
    status = str(getattr(exc, "status", "") or "").upper()
    message = str(getattr(exc, "message", "") or str(exc)).lower()
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        code = 0
    error_type = type(exc).__name__.lower()

    if code == 401 or status in {"UNAUTHENTICATED", "INVALID_API_KEY"} or (
        "api key" in message and any(term in message for term in ("invalid", "not valid", "expired"))
    ):
        return "Gemini rejected the API key. Replace your saved key, or check that it is enabled in Google AI Studio."
    if code == 403 or status in {"PERMISSION_DENIED", "PERMISSIONDENIED"}:
        return "Gemini access is forbidden. Check the key's API restrictions, project access, and region availability."
    if code == 429 or status in {"RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"}:
        return "Gemini quota or rate limit reached. Check the key's Google AI Studio project and quota, then retry."
    if code == 404 or status in {"NOT_FOUND", "MODEL_NOT_FOUND"}:
        return f"Gemini model '{GEMINI_MODEL}' was not found or is unavailable. Check the GEMINI_MODEL setting."
    if code == 400 or status in {"INVALID_ARGUMENT", "FAILED_PRECONDITION"}:
        return f"Gemini rejected the request for model '{GEMINI_MODEL}'. Check the model setting and API access."
    if "timeout" in error_type or "deadline" in status:
        return "Gemini took too long to respond. Built-in fallback content will be shown instead."
    if code >= 500 or status in {"INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED"}:
        return "Google's Gemini service is temporarily failing. Please try again later."
    if any(term in error_type for term in ("connect", "timeout", "network")):
        return "Could not connect to Gemini. Check the app server's internet access and try again."
    return (
        f"Gemini request failed ({type(exc).__name__}). Check the saved key, model setting, "
        "project quota, and Streamlit Cloud logs."
    )


def _is_missing_model_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "").upper()
    message = str(getattr(exc, "message", "") or str(exc)).lower()
    return (
        code == 404
        and (
            "model" in message
            or status in {"MODEL_NOT_FOUND", "NOT_FOUND"}
        )
    )


def _model_cache_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _get_cached_fallback_model(api_key: str) -> str | None:
    try:
        import streamlit as st

        cached = st.session_state.get("_logic_gemini_model_fallback")
        if isinstance(cached, dict) and cached.get("key") == _model_cache_key(api_key):
            model = cached.get("model")
            return model if isinstance(model, str) else None
    except Exception:
        return None
    return None


def _cache_fallback_model(api_key: str, model: str) -> None:
    try:
        import streamlit as st

        st.session_state["_logic_gemini_model_fallback"] = {
            "key": _model_cache_key(api_key),
            "model": model,
        }
    except Exception:
        return


def _discover_text_models(client) -> list[str]:
    """Find models this key can use for text generation."""
    available: set[str] = set()
    for model in client.models.list(config={"query_base": True}):
        name = getattr(model, "name", None)
        actions = getattr(model, "supported_actions", None) or []
        if not isinstance(name, str) or "generateContent" not in actions:
            continue
        model_id = name.rsplit("/", 1)[-1]
        if model_id.startswith("gemini-"):
            available.add(model_id)
    preferred = [model for model in GEMINI_MODEL_FALLBACKS if model in available]
    return preferred + sorted(available - set(preferred))


def ask_gemini(prompt: str, personal_key_only: bool = False) -> tuple[str | None, str | None]:
    """Return (text, error). Never raises."""
    key = get_api_key(personal_only=personal_key_only)
    if not key:
        reason = "No personal Gemini API key set — showing sample questions." if personal_key_only else (
            "No GEMINI_API_KEY set — showing sample-mode content."
        )
        return None, reason
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=GEMINI_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
        selected_model = GEMINI_MODEL
        try:
            resp = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            if not _is_missing_model_error(exc):
                raise

            cached_model = _get_cached_fallback_model(key)
            attempted_models = {GEMINI_MODEL}
            fallback_models = [cached_model] if cached_model else _discover_text_models(client)
            discovered_after_cache = not cached_model
            fallback_succeeded = False

            while fallback_models:
                for fallback_model in fallback_models:
                    if fallback_model in attempted_models:
                        continue
                    attempted_models.add(fallback_model)
                    try:
                        resp = client.models.generate_content(
                            model=fallback_model,
                            contents=prompt,
                            config=config,
                        )
                        selected_model = fallback_model
                        _cache_fallback_model(key, fallback_model)
                        fallback_succeeded = True
                        break
                    except Exception as fallback_error:
                        if not _is_missing_model_error(fallback_error):
                            raise
                if fallback_succeeded:
                    break
                if not discovered_after_cache:
                    fallback_models = [
                        model for model in _discover_text_models(client)
                        if model not in attempted_models
                    ]
                    discovered_after_cache = True
                else:
                    break

            if not fallback_succeeded:
                raise exc

        text = (resp.text or "").strip()
        if not text:
            return None, "Gemini returned an empty answer — showing sample-mode content."
        notice = (
            f"Configured model '{GEMINI_MODEL}' was unavailable; using '{selected_model}' instead."
            if selected_model != GEMINI_MODEL
            else None
        )
        return text, notice
    except Exception as exc:  # network, quota, invalid key, safety block...
        reason = _gemini_error_reason(exc)
        return None, f"{reason} Showing sample-mode content instead."


def sample_concept(topic: str, question: str = "") -> str:
    note = CONCEPT_NOTES.get(topic, "Pick a topic to see a summary.")
    return f"**{topic} — quick summary (sample mode)**\n\n{note}"


def sample_why_wrong(example: dict, user_answer: str) -> str:
    explanation = example["explanation"]
    explanation_lines = explanation if isinstance(explanation, list) else [explanation]
    return (
        f"**Why that isn't right (sample mode)**\n\nYou answered:\n```\n{user_answer or '(empty)'}\n```\n"
        f"The correct output is:\n```\n{example['answer']}\n```\n**Hint:** {example['hint']}\n\n"
        + "\n".join(f"- {line}" for line in explanation_lines)
    )


def explain_concept(topic: str, question: str) -> tuple[str, bool, str | None]:
    q = question.strip() or f"Explain the key ideas of {topic} in Python for a beginner."
    text, err = ask_gemini(f"Topic: {topic}\nStudent question: {q}")
    if text:
        return text, True, err
    return sample_concept(topic, q), False, err


def explain_wrong(example: dict, user_answer: str) -> tuple[str, bool, str | None]:
    if example.get("code"):
        prompt = (
            f"A beginner predicted the output of this Python program.\n\nCode:\n```python\n{example['code']}\n```\n"
            f"Correct output (verified):\n```\n{example['answer']}\n```\nStudent's answer:\n```\n{user_answer}\n```\n"
            "Explain kindly which misconception likely caused their answer, then walk through the code line by line. "
            "Do not contradict the verified correct output."
        )
    else:
        prompt = (
            f"A beginner answered this Python question:\n{example['question']}\n"
            f"Correct answer: {example['answer']}\nStudent's answer: {user_answer}\n"
            "Kindly explain the relevant Python concept and why the correct answer is right."
        )
    text, err = ask_gemini(prompt)
    if text:
        return text, True, err
    return sample_why_wrong(example, user_answer), False, err


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def sample_questions(topic: str, difficulty: str, size: int = 5) -> list[dict]:
    """Return a full built-in set, preferring examples closest to the requested difficulty."""
    if topic not in TOPICS:
        raise ValueError(f"Unknown topic: {topic}")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 10:
        raise ValueError("Question set size must be an integer from 1 to 10.")

    sample_level = "Beginner" if difficulty == "Low" else "Intermediate"
    matching_examples = [
        example for example in EXAMPLES
        if example["topic"] == topic and example["level"] == sample_level
    ]
    other_examples = [
        example for example in EXAMPLES
        if example["topic"] == topic and example["level"] != sample_level
    ]
    extras = []
    for question in PRACTICE_EXTRAS:
        if question["topic"] != topic:
            continue
        extras.append({
            **question,
            "title": question["question"],
            "description": f"Built-in practice question about {topic}.",
            "level": "Intermediate",
            "code": None,
            "hint": "Think about the Python rule this question is checking.",
        })
    return (matching_examples + extras + other_examples)[:size]


def _validated_generated_questions(data: object, topic: str, difficulty: str, size: int) -> list[dict] | None:
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return None
    items = data["questions"]
    if len(items) != size:
        return None

    questions = []
    for item in items:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        description = item.get("description")
        question = item.get("question")
        code = item.get("code")
        choices = item.get("choices")
        answer = item.get("answer")
        hint = item.get("hint")
        explanation = item.get("explanation")
        if not all(isinstance(value, str) for value in (
            title, description, question, code, answer, hint, explanation,
        )):
            return None
        if not (1 <= len(title.strip()) <= 100 and 1 <= len(description.strip()) <= 240
                and 1 <= len(question.strip()) <= 300 and 1 <= len(code.strip()) <= 1200
                and 1 <= len(answer.strip()) <= 500 and 1 <= len(hint.strip()) <= 300
                and 1 <= len(explanation.strip()) <= 1200):
            return None
        if (
            not isinstance(choices, list)
            or len(choices) != 4
            or not all(isinstance(choice, str) and 1 <= len(choice.strip()) <= 500 for choice in choices)
        ):
            return None
        clean_choices = [choice.strip() for choice in choices]
        clean_answer = answer.strip()
        if len(set(clean_choices)) != 4 or clean_choices.count(clean_answer) != 1:
            return None
        questions.append({
            "id": f"ai-{uuid4().hex}",
            "title": title.strip(),
            "description": description.strip(),
            "topic": topic,
            "level": DIFFICULTIES[difficulty],
            "question": question.strip(),
            "code": code.strip(),
            "choices": clean_choices,
            "answer": clean_answer,
            "hint": hint.strip(),
            "explanation": explanation.strip(),
            "_ai": True,
        })
    return questions


def generate_question_set(
    topic: str,
    difficulty: str,
    size: int = 5,
    fallback_questions: list[dict] | None = None,
    avoid_questions: list[dict] | None = None,
) -> tuple[list[dict], bool, str | None]:
    """Generate a validated set or return local questions without executing code."""
    if topic not in TOPICS:
        raise ValueError(f"Unknown topic: {topic}")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 10:
        raise ValueError("Question set size must be an integer from 1 to 10.")

    prompt = (
        f"Create exactly {size} fresh multiple-choice Python output-prediction questions for topic {topic}. "
        f"Difficulty: {difficulty} ({DIFFICULTIES[difficulty]}). "
        "Each question must contain a short, deterministic Python snippet that uses only basic language features "
        "and print a short output. Do not use files, network access, imports, or input(). "
        "Return ONLY a JSON object with a 'questions' array. Every item must have string keys "
        "'title', 'description', 'question', 'code', 'answer', 'hint', and 'explanation', plus "
        "'choices' (exactly four distinct strings). The answer must exactly match one choice. "
        "Keep each snippet and explanation beginner-readable, and ensure the answer follows from the code."
    )
    if avoid_questions:
        recent = [
            {"question": question.get("question", ""), "code": question.get("code") or ""}
            for question in avoid_questions[-10:]
        ]
        prompt += (
            "\nDo not repeat or lightly reword these questions or code snippets:\n"
            + json.dumps(recent, ensure_ascii=False)
        )
    text, err = ask_gemini(prompt, personal_key_only=True)
    if text:
        generated = _validated_generated_questions(_extract_json(text), topic, difficulty, size)
        if generated is not None:
            return generated, True, err
        err = (
            "Gemini returned an incomplete or invalid question set. "
            "Showing built-in questions instead."
        )

    fallback = fallback_questions if fallback_questions is not None else sample_questions(topic, difficulty)
    return [dict(question) for question in fallback[:size]], False, err


def generate_practice(
    topic: str,
    avoid_ids: set | None = None,
    difficulty: str = "Medium",
    avoid_questions: list[dict] | None = None,
) -> tuple[dict, bool, str | None]:
    """Return one new practice question, with a built-in fallback."""
    pool = sample_questions(topic, difficulty)
    avoid = avoid_ids or set()
    fresh = [question for question in pool if question["id"] not in avoid] or pool
    known_questions = [
        question for question in EXAMPLES + PRACTICE_EXTRAS
        if question["topic"] == topic and question["id"] in avoid
    ]
    questions, from_ai, err = generate_question_set(
        topic,
        difficulty,
        size=1,
        fallback_questions=fresh,
        avoid_questions=known_questions + (avoid_questions or []),
    )
    question = dict(questions[0])
    question.setdefault("code", None)
    question.setdefault("title", question["question"])
    question.setdefault("description", question["question"])
    question.setdefault("level", DIFFICULTIES[difficulty])
    return question, from_ai, err
