"""Verifies the predefined content and core logic.

Note: this test (not the app) runs the BUILT-IN example code to prove each
stored answer is the true output. The app itself never executes code.
"""
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import logic
from examples_data import EXAMPLES, PRACTICE_EXTRAS, TOPICS


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_stored_answer_matches_real_output(ex):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(ex["code"], {})
    assert logic.normalize_output(buf.getvalue()) == logic.normalize_output(ex["answer"])


@pytest.mark.parametrize("q", EXAMPLES + PRACTICE_EXTRAS, ids=[q["id"] for q in EXAMPLES + PRACTICE_EXTRAS])
def test_choices_contain_answer_once(q):
    assert q["choices"].count(q["answer"]) == 1
    assert len(set(q["choices"])) == 4
    assert q["topic"] in TOPICS


def test_content_coverage():
    assert len(EXAMPLES) >= 15
    assert {e["topic"] for e in EXAMPLES} == set(TOPICS)
    assert {e["level"] for e in EXAMPLES} == {"Beginner", "Intermediate"}
    for e in EXAMPLES:
        for k in ("title", "description", "code", "question", "answer", "hint", "explanation"):
            assert e[k]


def test_grading_is_whitespace_tolerant_but_strict_on_content():
    assert logic.check_answer("  3.5   3 \n", "3.5 3")
    assert logic.check_answer("0\n1\n\n3\n", "0\n1\n3")
    assert not logic.check_answer("3 3", "3.5 3")
    assert not logic.check_answer("", "3")


def test_stats_and_recommendations_follow_attempts():
    p = logic.empty_progress()
    logic.record_attempt(p, "loop-sum", "Loops", True, "t")
    logic.record_attempt(p, "loop-while-halve", "Loops", False, "t")
    logic.record_attempt(p, "str-slice", "Strings", True, "t")
    s = logic.compute_stats(p)
    assert s["total_attempts"] == 3 and s["correct"] == 2
    assert round(s["accuracy"], 2) == 0.67
    assert s["per_topic"]["Loops"]["accuracy"] == 0.5
    assert "Strings" in s["strengths"] and "Loops" in s["weaknesses"]
    recs = logic.recommend_examples(p)
    assert recs[0]["topic"] == "Loops"  # weakest topic first
    assert all(r["id"] not in s["solved"] for r in recs)


def test_filters_and_quiz():
    assert all(e["topic"] == "Lists" for e in logic.filter_examples(topic="Lists"))
    assert [e["id"] for e in logic.filter_examples("banana")] == ["dict-count"]
    for t in TOPICS:
        assert 4 <= len(logic.build_quiz(t)) <= 5
        for difficulty in logic.DIFFICULTIES:
            samples = logic.sample_questions(t, difficulty)
            assert len(samples) == 5
            assert len({question["id"] for question in samples}) == 5
            assert all(question["answer"] in question["choices"] for question in samples)
            assert len(logic.build_quiz(t, difficulty=difficulty)) == 5


def test_sample_mode_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        logic,
        "get_api_key",
        lambda visitor_key=None, personal_only=False: visitor_key.strip() if visitor_key else None,
    )
    assert not logic.gemini_available()
    text, from_ai, err = logic.explain_concept("Loops", "what is range?")
    assert not from_ai and "range" in text and err
    q, from_ai, _ = logic.generate_practice("Tuples")
    assert not from_ai and q["answer"] in q["choices"]
    text, from_ai, _ = logic.explain_wrong(EXAMPLES[0], "3 3")
    assert not from_ai and EXAMPLES[0]["answer"] in text


def test_generate_question_set_uses_difficulty_and_validates_full_set(monkeypatch):
    prompts = []

    def fake_gemini(prompt, personal_key_only=False):
        assert personal_key_only
        prompts.append(prompt)
        questions = [
            {
                "title": f"Loop question {index}",
                "description": "Trace a short loop.",
                "question": "What does this program print?",
                "code": f"print({index})",
                "choices": [str(index), "10", "20", "30"],
                "answer": str(index),
                "hint": "Read the value passed to print.",
                "explanation": f"The program prints {index}.",
            }
            for index in range(5)
        ]
        return json.dumps({"questions": questions}), None

    monkeypatch.setattr(logic, "ask_gemini", fake_gemini)
    questions, from_ai, error = logic.generate_question_set("Loops", "Hard", size=5)

    assert from_ai and error is None
    assert len(questions) == 5
    assert len({question["id"] for question in questions}) == 5
    assert all(question["_ai"] and question["level"] == "Advanced" for question in questions)
    assert all(question["answer"] in question["choices"] for question in questions)
    assert "exactly 5" in prompts[0] and "Hard (Advanced)" in prompts[0]


def test_question_generation_falls_back_to_matching_samples(monkeypatch):
    monkeypatch.setattr(
        logic, "ask_gemini", lambda prompt, personal_key_only=False: (None, "Gemini quota reached.")
    )

    expected = logic.sample_questions("Loops", "Hard")
    questions, from_ai, error = logic.generate_question_set("Loops", "Hard", size=5)

    assert not from_ai and error == "Gemini quota reached."
    assert [question["id"] for question in questions] == [question["id"] for question in expected]
    assert len(questions) == 5
    assert all(question["answer"] in question["choices"] for question in questions)


def test_invalid_ai_question_set_uses_complete_fallback(monkeypatch):
    invalid = {
        "questions": [{
            "title": "Bad question",
            "description": "Invalid choices.",
            "question": "What prints?",
            "code": "print(1)",
            "choices": ["1", "1", "2", "3"],
            "answer": "1",
            "hint": "Look at print.",
            "explanation": "It prints 1.",
        }]
    }
    monkeypatch.setattr(
        logic, "ask_gemini", lambda prompt, personal_key_only=False: (json.dumps(invalid), None)
    )
    fallback = logic.sample_questions("Loops", "Low")

    questions, from_ai, error = logic.generate_question_set(
        "Loops", "Low", size=1, fallback_questions=fallback
    )

    assert not from_ai
    assert "incomplete or invalid" in error
    assert questions[0]["id"] == fallback[0]["id"]


def test_visitor_api_key_overrides_configured_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "deployment-key")
    assert logic.get_api_key(" visitor-key ") == "visitor-key"


def test_fresh_questions_require_a_personal_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "deployment-key")
    assert logic.get_api_key(personal_only=True) is None


@pytest.mark.parametrize(
    ("code", "status", "message", "expected"),
    [
        (400, "INVALID_ARGUMENT", "API key not valid. Secret-value", "rejected the API key"),
        (403, "PERMISSION_DENIED", "Permission denied", "API restrictions"),
        (429, "RESOURCE_EXHAUSTED", "Quota exceeded", "quota or rate limit"),
        (404, "NOT_FOUND", "Model not found", "GEMINI_MODEL"),
        (503, "UNAVAILABLE", "Service down", "temporarily failing"),
    ],
)
def test_gemini_errors_give_specific_safe_guidance(code, status, message, expected):
    class FakeAPIError(Exception):
        def __init__(self):
            self.code = code
            self.status = status
            self.message = message

    reason = logic._gemini_error_reason(FakeAPIError())
    assert expected.lower() in reason.lower()
    assert "Secret-value" not in reason


def test_gemini_network_error_is_actionable():
    reason = logic._gemini_error_reason(TimeoutError("request timed out"))
    assert "Could not connect" in reason


def test_gemini_discovers_and_uses_a_model_when_configured_model_is_missing(monkeypatch):
    from google import genai
    from types import SimpleNamespace

    calls = []

    class ModelMissingError(Exception):
        code = 404
        status = "NOT_FOUND"
        message = "models/gemini-2.5-flash is not found for generateContent"

    class FakeModels:
        def list(self, config):
            return [
                SimpleNamespace(name="models/gemini-3.8-flash", supported_actions=["generateContent"]),
                SimpleNamespace(name="models/gemini-embedding", supported_actions=["embedContent"]),
            ]

        def generate_content(self, *, model, contents, config):
            calls.append(model)
            if model == logic.GEMINI_MODEL:
                raise ModelMissingError()
            return SimpleNamespace(text="Generated with fallback model.")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(logic, "get_api_key", lambda **kwargs: "test-personal-key")
    monkeypatch.setattr(logic, "_get_cached_fallback_model", lambda key: None)
    monkeypatch.setattr(logic, "_cache_fallback_model", lambda key, model: None)
    monkeypatch.setattr(genai, "Client", lambda api_key: FakeClient())

    text, notice = logic.ask_gemini("Generate a Python practice question.", personal_key_only=True)

    assert text == "Generated with fallback model.", notice
    assert notice == (
        f"Configured model '{logic.GEMINI_MODEL}' was unavailable; "
        "using 'gemini-3.8-flash' instead."
    )
    assert calls == [logic.GEMINI_MODEL, "gemini-3.8-flash"]


def test_gemini_fallback_uses_cached_model_without_listing(monkeypatch):
    from google import genai
    from types import SimpleNamespace

    calls = []

    class ModelMissingError(Exception):
        code = 404
        status = "NOT_FOUND"
        message = "configured model not found"

    class FakeModels:
        def list(self, config):
            raise AssertionError("Should use the cached available model first.")

        def generate_content(self, *, model, contents, config):
            calls.append(model)
            if model == logic.GEMINI_MODEL:
                raise ModelMissingError()
            return SimpleNamespace(text="Cached model worked.")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(logic, "get_api_key", lambda **kwargs: "test-personal-key")
    monkeypatch.setattr(logic, "_get_cached_fallback_model", lambda key: "gemini-3.8-flash")
    monkeypatch.setattr(logic, "_cache_fallback_model", lambda key, model: None)
    monkeypatch.setattr(genai, "Client", lambda api_key: FakeClient())

    text, notice = logic.ask_gemini("Hello")

    assert text == "Cached model worked.", notice
    assert "gemini-3.8-flash" in notice
    assert calls == [logic.GEMINI_MODEL, "gemini-3.8-flash"]
