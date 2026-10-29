"""Verifies the predefined content and core logic.

Note: this test (not the app) runs the BUILT-IN example code to prove each
stored answer is the true output. The app itself never executes code.
"""
import contextlib
import io
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


def test_sample_mode_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert not logic.gemini_available()
    text, from_ai, err = logic.explain_concept("Loops", "what is range?")
    assert not from_ai and "range" in text and err
    q, from_ai, _ = logic.generate_practice("Tuples")
    assert not from_ai and q["answer"] in q["choices"]
    text, from_ai, _ = logic.explain_wrong(EXAMPLES[0], "3 3")
    assert not from_ai and EXAMPLES[0]["answer"] in text
