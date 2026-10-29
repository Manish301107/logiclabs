"""Pure logic for LogicLab AI: grading, progress stats, recommendations, Gemini helpers.

Kept free of Streamlit so it can be unit-tested.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from examples_data import EXAMPLES, PRACTICE_EXTRAS, TOPICS, CONCEPT_NOTES

EXAMPLES_BY_ID = {e["id"]: e for e in EXAMPLES}
PROGRESS_FILE = Path(__file__).parent / "progress.json"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
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
    """Build a quiz, optionally limited to built-in examples matching a difficulty."""
    if difficulty is not None:
        examples = sample_questions(topic, difficulty)
        return [
            {
                "id": example["id"],
                "topic": topic,
                "question": example["question"],
                "code": example["code"],
                "choices": example["choices"],
                "answer": example["answer"],
                "explanation": " ".join(example["explanation"]),
            }
            for example in examples[:size]
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
        return st.secrets.get("GEMINI_API_KEY")  # type: ignore[attr-defined]
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

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        text = (resp.text or "").strip()
        if not text:
            return None, "Gemini returned an empty answer — showing sample-mode content."
        return text, None
    except Exception as exc:  # network, quota, invalid key, safety block...
        msg = str(exc)
        if "API key" in msg or "401" in msg or "403" in msg or "PERMISSION" in msg:
            reason = "Gemini rejected the API key."
        elif "429" in msg or "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
            reason = "Gemini rate limit or quota reached."
        else:
            reason = "Gemini is unavailable right now."
        return None, f"{reason} Showing sample-mode content instead."


def sample_concept(topic: str, question: str = "") -> str:
    note = CONCEPT_NOTES.get(topic, "Pick a topic to see a summary.")
    return f"**{topic} — quick summary (sample mode)**\n\n{note}"


def sample_why_wrong(example: dict, user_answer: str) -> str:
    return (
        f"**Why that isn't right (sample mode)**\n\nYou answered:\n```\n{user_answer or '(empty)'}\n```\n"
        f"The correct output is:\n```\n{example['answer']}\n```\n**Hint:** {example['hint']}\n\n"
        + "\n".join(f"- {line}" for line in example["explanation"])
    )


def explain_concept(topic: str, question: str) -> tuple[str, bool, str | None]:
    q = question.strip() or f"Explain the key ideas of {topic} in Python for a beginner."
    text, err = ask_gemini(f"Topic: {topic}\nStudent question: {q}")
    if text:
        return text, True, None
    return sample_concept(topic, q), False, err


def explain_wrong(example: dict, user_answer: str) -> tuple[str, bool, str | None]:
    prompt = (
        f"A beginner predicted the output of this Python program.\n\nCode:\n```python\n{example['code']}\n```\n"
        f"Correct output (verified):\n```\n{example['answer']}\n```\nStudent's answer:\n```\n{user_answer}\n```\n"
        "Explain kindly which misconception likely caused their answer, then walk through the code line by line. "
        "Do not contradict the verified correct output."
    )
    text, err = ask_gemini(prompt)
    if text:
        return text, True, None
    return sample_why_wrong(example, user_answer), False, err


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def sample_questions(topic: str, difficulty: str) -> list[dict]:
    """Return topic examples closest to the requested difficulty."""
    if topic not in TOPICS:
        raise ValueError(f"Unknown topic: {topic}")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty: {difficulty}")

    sample_level = "Beginner" if difficulty == "Low" else "Intermediate"
    matching = [
        example for example in EXAMPLES
        if example["topic"] == topic and example["level"] == sample_level
    ]
    return matching or [example for example in EXAMPLES if example["topic"] == topic]


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
            return generated, True, None
        err = "Gemini's questions were not in a usable format — showing built-in questions instead."

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
