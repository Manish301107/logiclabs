"""Pure logic for LogicLab AI: grading, progress stats, recommendations, Gemini helpers.

Kept free of Streamlit so it can be unit-tested.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from examples_data import EXAMPLES, PRACTICE_EXTRAS, TOPICS, CONCEPT_NOTES

EXAMPLES_BY_ID = {e["id"]: e for e in EXAMPLES}
PROGRESS_FILE = Path(__file__).parent / "progress.json"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


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


def build_quiz(topic: str, size: int = 5) -> list[dict]:
    """Deterministic multiple-choice quiz for a topic: its examples + extra concept questions."""
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
def get_api_key(visitor_key: str | None = None) -> str | None:
    if visitor_key is None:
        try:
            import streamlit as st
            visitor_key = st.session_state.get("visitor_gemini_api_key")
        except Exception:
            visitor_key = None
    if visitor_key and visitor_key.strip():
        return visitor_key.strip()

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


def ask_gemini(prompt: str) -> tuple[str | None, str | None]:
    """Return (text, error). Never raises."""
    key = get_api_key()
    if not key:
        return None, "No GEMINI_API_KEY set — showing sample-mode content."
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


def generate_practice(topic: str, avoid_ids: set | None = None) -> tuple[dict, bool, str | None]:
    """Returns (question, from_ai, error). Falls back to a verified local question."""
    prompt = (
        f"Create ONE new beginner multiple-choice question about Python {topic}. "
        "Return ONLY JSON with keys: question (string), code (short Python snippet or empty string), "
        "choices (array of exactly 4 strings), answer (one of the choices, exactly), explanation (string). "
        "The code must be deterministic and print a short output."
    )
    text, err = ask_gemini(prompt)
    if text:
        data = _extract_json(text)
        if (isinstance(data, dict) and isinstance(data.get("choices"), list) and len(data["choices"]) == 4
                and data.get("answer") in data["choices"] and data.get("question")):
            return ({"id": f"ai-{abs(hash(data['question'])) % 10**8}", "topic": topic,
                     "question": str(data["question"]), "code": data.get("code") or None,
                     "choices": [str(c) for c in data["choices"]], "answer": str(data["answer"]),
                     "explanation": str(data.get("explanation", ""))}, True, None)
        err = "Gemini's question was not in a usable format — showing a built-in question instead."
    avoid = avoid_ids or set()
    pool = [x for x in PRACTICE_EXTRAS if x["topic"] == topic]
    fresh = [x for x in pool if x["id"] not in avoid] or pool
    q = dict(fresh[0])
    q.setdefault("code", None)
    return q, False, err
