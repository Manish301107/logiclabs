"""End-to-end UI flows using Streamlit's AppTest (sample mode, no API key)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest
from streamlit.testing.v1 import AppTest

import logic


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(logic, "PROGRESS_FILE", tmp_path / "progress.json")
    monkeypatch.chdir(ROOT)


def new_app():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    return at


def btn(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button {label!r} not found: {[b.label for b in at.button]}")


def test_home_renders_recommendations():
    at = new_app()
    assert any("Welcome to LogicLab AI" in m.value for m in at.markdown)
    assert sum(1 for b in at.button if b.label == "Open example →") == 3


def test_explore_select_check_wrong_then_right():
    at = new_app()
    at.sidebar.radio[0].set_value("Explore Examples").run()
    assert sum(1 for b in at.button if b.label == "Open example →") == 23
    at.selectbox(key="f_topic").set_value("Loops").run()
    assert sum(1 for b in at.button if b.label == "Open example →") == 3
    at.button(key="exp-loop-sum").click().run()
    assert any("Summing with range()" in m.value for m in at.markdown)

    btn(at, "Show Hint").click().run()
    assert any("range(1, 5) produces" in i.value for i in at.info)

    at.radio(key="mc-loop-sum").set_value("15").run()
    btn(at, "Check Answer").click().run()
    assert at.error and "Not quite" in at.error[0].value
    assert any("total starts at 0" in m.value for m in at.markdown)  # explanation auto-shown

    btn(at, "✨ Ask AI why my answer is wrong").click().run()
    assert any("sample mode" in m.value for m in at.markdown)

    at.radio(key="mode-loop-sum").set_value("Type my prediction").run()
    at.text_area(key="tx-loop-sum").input(" 10 ").run()
    btn(at, "Check Answer").click().run()
    assert at.success and any("Correct" in s.value for s in at.success)

    s = logic.compute_stats(at.session_state.progress)
    assert s["total_attempts"] == 2 and s["correct"] == 1


def test_practice_quiz_scoring_and_progress():
    at = new_app()
    at.sidebar.radio[0].set_value("Practice").run()
    at.selectbox(key="quiz_topic").set_value("Tuples").run()
    btn(at, "Start quiz").click().run()
    qs = at.session_state.quiz["questions"]
    for i, q in enumerate(qs):
        wrong = next(c for c in q["choices"] if c != q["answer"])
        pick = q["answer"] if i % 2 == 0 else wrong  # alternate right/wrong
        at.radio(key=f"quiz-Tuples-{q['id']}").set_value(pick).run()
        btn(at, "Submit answer").click().run()
        next_label = "See final score" if i == len(qs) - 1 else "Next question →"
        btn(at, next_label).click().run()
    expected = sum(1 for i in range(len(qs)) if i % 2 == 0)
    assert any(f"Score: {expected} / {len(qs)}" in p.proto.text for p in at.get("progress"))

    btn(at, "✨ Generate a new practice question").click().run()
    assert any("Verified question" in m.value for m in at.markdown)

    at.sidebar.radio[0].set_value("My Progress").run()
    s = logic.compute_stats(at.session_state.progress)
    assert s["total_attempts"] == len(qs) and s["correct"] == expected
    assert any(f"Tuples — {expected}/{len(qs)} correct" in p.proto.text for p in at.get("progress"))
    btn(at, "Reset all progress").click().run()
    assert logic.compute_stats(at.session_state.progress)["total_attempts"] == 0


def test_about_page():
    at = new_app()
    at.sidebar.radio[0].set_value("About").run()
    assert any("Sample mode" in c.value for c in at.caption)
