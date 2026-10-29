"""LogicLab AI — learn Python by predicting output.

Run:  streamlit run app.py
Never executes user-submitted code. Answers are checked deterministically
against verified expected outputs stored in examples_data.py.
"""
from __future__ import annotations

import streamlit as st

from examples_data import EXAMPLES, TOPICS
from logic import (
    EXAMPLES_BY_ID,
    build_quiz,
    check_answer,
    compute_stats,
    empty_progress,
    explain_concept,
    explain_wrong,
    filter_examples,
    gemini_available,
    generate_practice,
    load_progress,
    recommend_examples,
    record_attempt,
    save_progress,
)

st.set_page_config(page_title="LogicLab AI — Learn Python by Predicting", page_icon="🧪", layout="wide")

PAGES = ["Home", "Explore Examples", "Practice", "My Progress", "About"]

# ---------------- Styles ----------------
st.markdown(
    """
<style>
:root{--ll-bg:#0b1020;--ll-panel:#111827;--ll-panel-2:#182338;--ll-border:#283449;--ll-text:#e8ecf5;
--ll-muted:#a2aec2;--ll-accent:#b4a5ff;--ll-accent-soft:rgba(164,142,255,.13);--ll-ok:#6ee7b7;--ll-bad:#fda4af;}
html,body{font-family:Inter,"Segoe UI",system-ui,sans-serif;}
.block-container{max-width:1180px;}
h1{font-size:1.85rem!important;font-weight:700!important;letter-spacing:-.035em;line-height:1.2!important;}
h2{font-size:1.35rem!important;font-weight:650!important;letter-spacing:-.02em;}
h3{font-size:1.08rem!important;font-weight:650!important;}
div[data-testid="stAppViewContainer"]{background:
radial-gradient(ellipse at 12% 0%,rgba(114,87,216,.10),transparent 34%),var(--ll-bg);}
div[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--ll-border)!important;
background:linear-gradient(145deg,rgba(255,255,255,.025),transparent 52%),var(--ll-panel);
border-radius:16px;box-shadow:0 10px 28px rgba(0,0,0,.12);transition:border-color .18s ease, transform .18s ease, box-shadow .18s ease;}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:#51477f!important;transform:translateY(-2px);
box-shadow:0 14px 32px rgba(0,0,0,.2);}
.ll-badge{display:inline-block;font-size:.72rem;padding:.12rem .55rem;border-radius:999px;margin-right:.35rem;
border:1px solid var(--ll-border);color:#bac5d8;background:var(--ll-panel-2);font-weight:550;}
.ll-badge.accent{color:#d5ccff;background:var(--ll-accent-soft);border-color:#51477f;}
.ll-muted{color:var(--ll-muted);font-size:.94rem;line-height:1.65;}
.ll-kpi{font-size:1.8rem;font-weight:700;line-height:1.15;letter-spacing:-.035em;margin-top:.25rem;}
.ll-kpi-label{color:var(--ll-muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.09em;font-weight:600;}
.ll-hero{padding:1.7rem 1.8rem;border:1px solid #342e55;border-radius:18px;background:
radial-gradient(ellipse at 90% 0%,rgba(164,142,255,.14),transparent 48%),
linear-gradient(145deg,rgba(114,87,216,.09),transparent 65%),var(--ll-panel);margin-bottom:1.3rem;
box-shadow:0 16px 40px rgba(0,0,0,.16);}
.ll-ok{color:var(--ll-ok);font-weight:650}.ll-bad{color:var(--ll-bad);font-weight:650}
.stButton>button{border-radius:.7rem;border:1px solid var(--ll-border);font-weight:600;
transition:border-color .15s ease,background .15s ease,transform .15s ease,box-shadow .15s ease;}
.stButton>button:hover{border-color:#8f7af0;transform:translateY(-1px);box-shadow:0 5px 16px rgba(114,87,216,.16);}
.stButton>button[kind="primary"]{box-shadow:0 4px 14px rgba(114,87,216,.2);}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] [data-baseweb="select"]>div{border-radius:.7rem;}
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus{border-color:#8f7af0;
box-shadow:0 0 0 1px #8f7af0;}
div[data-testid="stCode"]{border:1px solid var(--ll-border);border-radius:12px;overflow:hidden;}
code,pre{font-size:.9rem!important;}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------- State ----------------
ss = st.session_state
if "progress" not in ss:
    ss.progress = load_progress()
ss.setdefault("nav", "Home")
ss.setdefault("selected", None)
ss.setdefault("results", {})      # example_id -> {"answer", "correct"}
ss.setdefault("show_hint", set())
ss.setdefault("show_expl", set())
ss.setdefault("ai_text", {})       # key -> (text, from_ai, err)
ss.setdefault("quiz", None)
ss.setdefault("extra_q", {})       # topic -> question dict
ss.setdefault("extra_result", {})  # topic -> {"choice", "correct"}


def persist():
    save_progress(ss.progress)


def go(page: str, example_id: str | None = None):
    ss.nav = page
    if example_id is not None:
        ss.selected = example_id


def badges(e):
    return (f'<span class="ll-badge accent">{e["topic"]}</span>'
            f'<span class="ll-badge">{e["level"]}</span>')


def fmt_choice(c: str) -> str:
    return c.replace("\n", "  ⏎  ")


def example_card(e, key_prefix: str):
    stats = compute_stats(ss.progress)
    status = "✓ Solved" if e["id"] in stats["solved"] else ("Attempted" if e["id"] in stats["attempted_ids"] else "")
    with st.container(border=True):
        st.markdown(badges(e) + (f'<span class="ll-badge">{status}</span>' if status else ""), unsafe_allow_html=True)
        st.markdown(f"**{e['title']}**")
        st.markdown(f'<div class="ll-muted">{e["description"]}</div>', unsafe_allow_html=True)
        st.button("Open example →", key=f"{key_prefix}-{e['id']}", on_click=go,
                  args=("Explore Examples", e["id"]), use_container_width=True)


# ---------------- Pages ----------------
def page_home():
    s = compute_stats(ss.progress)
    st.markdown(
        '<div class="ll-hero"><h1 style="margin:0">Welcome to LogicLab AI</h1>'
        '<div class="ll-muted" style="margin-top:.4rem">Read a short Python program, predict what it prints, '
        'and get instant line-by-line feedback. No coding setup needed.</div></div>',
        unsafe_allow_html=True,
    )
    c = st.columns(4)
    for col, (label, val) in zip(c, [("Attempts", s["total_attempts"]), ("Correct", s["correct"]),
                                     ("Accuracy", f"{s['accuracy']*100:.0f}%"),
                                     ("Examples solved", f"{len(s['solved'])}/{len(EXAMPLES)}")]):
        with col, st.container(border=True):
            st.markdown(f'<div class="ll-kpi-label">{label}</div><div class="ll-kpi">{val}</div>', unsafe_allow_html=True)

    st.markdown("## Recommended next")
    recs = recommend_examples(ss.progress)
    if recs:
        cols = st.columns(len(recs))
        for col, e in zip(cols, recs):
            with col:
                example_card(e, "home-rec")
    else:
        st.success("You've solved every example — try Practice mode for more.")

    st.markdown("## How it works")
    h = st.columns(3)
    steps = [("1 · Pick an example", "Browse 23 ready-made programs across 10 beginner topics."),
             ("2 · Predict the output", "Type your prediction or pick from multiple choices, then Check Answer."),
             ("3 · Learn from it", "Get a hint, a line-by-line explanation, or ask the AI tutor why.")]
    for col, (t, d) in zip(h, steps):
        with col, st.container(border=True):
            st.markdown(f"**{t}**")
            st.markdown(f'<div class="ll-muted">{d}</div>', unsafe_allow_html=True)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.button("Explore examples", type="primary", on_click=go, args=("Explore Examples",), use_container_width=True)
    b2.button("Start a quiz", on_click=go, args=("Practice",), use_container_width=True)


def render_detail(e):
    st.button("← Back to all examples", on_click=lambda: ss.update(selected=None))
    st.markdown(badges(e), unsafe_allow_html=True)
    st.markdown(f"# {e['title']}")
    st.markdown(f'<div class="ll-muted">{e["description"]}</div>', unsafe_allow_html=True)
    st.code(e["code"], language="python", line_numbers=True)
    st.markdown(f"**{e['question']}**")

    mode = st.radio("Answer mode", ["Multiple choice", "Type my prediction"], horizontal=True, key=f"mode-{e['id']}")
    if mode == "Multiple choice":
        user = st.radio("Choose the output", e["choices"], index=None, format_func=fmt_choice, key=f"mc-{e['id']}")
    else:
        user = st.text_area("Type the exact output (one line per print)", key=f"tx-{e['id']}", height=110,
                            placeholder="e.g. 3.5 3")

    c1, c2, c3 = st.columns(3)
    check = c1.button("Check Answer", type="primary", key=f"chk-{e['id']}", use_container_width=True)
    if c2.button("Show Hint", key=f"hint-{e['id']}", use_container_width=True):
        ss.show_hint.add(e["id"])
    if c3.button("Show Explanation", key=f"exp-{e['id']}", use_container_width=True):
        ss.show_expl.add(e["id"])

    if check:
        if not user or not str(user).strip():
            st.warning("Choose or type an answer first.")
        else:
            ok = check_answer(user, e["answer"])
            ss.results[e["id"]] = {"answer": user, "correct": ok}
            record_attempt(ss.progress, e["id"], e["topic"], ok, "explore")
            persist()
            ss.ai_text.pop(f"wrong-{e['id']}", None)

    if e["id"] in ss.show_hint:
        st.info(f"**Hint:** {e['hint']}", icon="💡")

    res = ss.results.get(e["id"])
    if res:
        if res["correct"]:
            st.success("Correct! Nice prediction.", icon="✅")
        else:
            st.error("Not quite. Compare your answer with the explanation below.", icon="❌")
            ss.show_expl.add(e["id"])
            k = f"wrong-{e['id']}"
            if st.button("✨ Ask AI why my answer is wrong", key=f"why-{e['id']}"):
                with st.spinner("Asking the tutor…"):
                    ss.ai_text[k] = explain_wrong(e, res["answer"])
            if k in ss.ai_text:
                text, from_ai, err = ss.ai_text[k]
                if err:
                    st.caption(err)
                with st.container(border=True):
                    st.markdown(("**AI tutor (Gemini)**\n\n" if from_ai else "") + text)

    if e["id"] in ss.show_expl:
        with st.container(border=True):
            st.markdown("**Correct output**")
            st.code(e["answer"], language="text")
            st.markdown("**Line-by-line explanation**")
            for line in e["explanation"]:
                st.markdown(f"- {line}")

    with st.expander("✨ Still confused? Ask the AI tutor about this topic"):
        q = st.text_input("Your question", key=f"cq-{e['id']}", placeholder=f"e.g. When should I use {e['topic'].lower()}?")
        if st.button("Explain", key=f"cbtn-{e['id']}"):
            with st.spinner("Thinking…"):
                ss.ai_text[f"concept-{e['id']}"] = explain_concept(e["topic"], q)
        if f"concept-{e['id']}" in ss.ai_text:
            text, from_ai, err = ss.ai_text[f"concept-{e['id']}"]
            if err:
                st.caption(err)
            st.markdown(text)


def page_explore():
    if ss.selected and ss.selected in EXAMPLES_BY_ID:
        render_detail(EXAMPLES_BY_ID[ss.selected])
        return
    st.markdown("# Explore Examples")
    st.markdown(f'<div class="ll-muted">{len(EXAMPLES)} predefined programs. Open one to predict its output.</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1.3, 1])
    q = c1.text_input("Search", placeholder="Search titles, topics or code…", key="search")
    topic = c2.selectbox("Topic", ["All"] + TOPICS, key="f_topic")
    level = c3.selectbox("Difficulty", ["All", "Beginner", "Intermediate"], key="f_level")
    items = filter_examples(q, topic, level)
    if not items:
        st.info("No examples match those filters.")
        return
    cols = st.columns(3)
    for i, e in enumerate(items):
        with cols[i % 3]:
            example_card(e, "exp")


def page_practice():
    st.markdown("# Practice")
    quiz = ss.quiz
    if quiz is None:
        st.markdown('<div class="ll-muted">A short multiple-choice quiz on one topic. Feedback after every question.</div>',
                    unsafe_allow_html=True)
        topic = st.selectbox("Choose a topic", TOPICS, key="quiz_topic")
        n = len(build_quiz(topic))
        st.caption(f"{n} questions")
        if st.button("Start quiz", type="primary"):
            ss.quiz = {"topic": topic, "questions": build_quiz(topic), "idx": 0, "answers": {}}
            st.rerun()
        return

    qs, idx = quiz["questions"], quiz["idx"]
    if idx >= len(qs):
        score = sum(1 for a in quiz["answers"].values() if a["correct"])
        st.markdown(f"## Quiz complete — {quiz['topic']}")
        st.progress(score / len(qs), text=f"Score: {score} / {len(qs)}")
        wrong = [q for q in qs if not quiz["answers"][q["id"]]["correct"]]
        if not wrong:
            st.success("Perfect score! 🎉")
        else:
            st.markdown("### Review your mistakes")
            for q in wrong:
                with st.container(border=True):
                    st.markdown(f"**{q['question']}**")
                    if q.get("code"):
                        st.code(q["code"], language="python")
                    st.markdown(f"<span class='ll-bad'>Your answer:</span> `{fmt_choice(quiz['answers'][q['id']]['choice'])}`  \n"
                                f"<span class='ll-ok'>Correct:</span> `{fmt_choice(q['answer'])}`", unsafe_allow_html=True)
                    st.markdown(q["explanation"])
            st.markdown("### Extra practice for this topic")
            render_extra_question(quiz["topic"], {q["id"] for q in qs})
        c1, c2 = st.columns(2)
        if c1.button("Retake quiz", use_container_width=True):
            ss.quiz = {**quiz, "idx": 0, "answers": {}}
            st.rerun()
        if c2.button("Choose another topic", use_container_width=True):
            ss.quiz = None
            st.rerun()
        return

    q = qs[idx]
    st.progress(idx / len(qs), text=f"{quiz['topic']} · Question {idx + 1} of {len(qs)}")
    with st.container(border=True):
        st.markdown(f"**{q['question']}**")
        if q.get("code"):
            st.code(q["code"], language="python")
        answered = quiz["answers"].get(q["id"])
        choice = st.radio("Your answer", q["choices"], index=None, format_func=fmt_choice,
                          key=f"quiz-{quiz['topic']}-{q['id']}", disabled=bool(answered))
        if not answered:
            if st.button("Submit answer", type="primary"):
                if choice is None:
                    st.warning("Pick an answer first.")
                else:
                    ok = check_answer(choice, q["answer"])
                    quiz["answers"][q["id"]] = {"choice": choice, "correct": ok}
                    record_attempt(ss.progress, q["id"], q["topic"], ok, "practice")
                    persist()
                    st.rerun()
        else:
            if answered["correct"]:
                st.success("Correct!", icon="✅")
            else:
                st.error(f"Incorrect. The answer is: {fmt_choice(q['answer'])}", icon="❌")
            st.markdown(q["explanation"])
            label = "See final score" if idx == len(qs) - 1 else "Next question →"
            if st.button(label, type="primary"):
                quiz["idx"] += 1
                st.rerun()


def render_extra_question(topic: str, avoid: set):
    if st.button("✨ Generate a new practice question", key=f"gen-{topic}"):
        with st.spinner("Creating a question…"):
            q, from_ai, err = generate_practice(topic, avoid)
        ss.extra_q[topic] = {**q, "_ai": from_ai, "_err": err}
        ss.extra_result.pop(topic, None)
    q = ss.extra_q.get(topic)
    if not q:
        return
    with st.container(border=True):
        if q.get("_err"):
            st.caption(q["_err"])
        st.markdown(('<span class="ll-badge accent">AI-generated</span>' if q["_ai"]
                     else '<span class="ll-badge">Verified question</span>'), unsafe_allow_html=True)
        st.markdown(f"**{q['question']}**")
        if q.get("code"):
            st.code(q["code"], language="python")
        res = ss.extra_result.get(topic)
        choice = st.radio("Your answer", q["choices"], index=None, format_func=fmt_choice,
                          key=f"xq-{topic}-{q['id']}", disabled=bool(res))
        if not res and st.button("Check Answer", key=f"xchk-{topic}"):
            if choice is None:
                st.warning("Pick an answer first.")
            else:
                ok = check_answer(choice, q["answer"])
                ss.extra_result[topic] = {"choice": choice, "correct": ok}
                record_attempt(ss.progress, q["id"], topic, ok, "ai-practice" if q["_ai"] else "practice")
                persist()
                st.rerun()
        if res:
            (st.success if res["correct"] else st.error)(
                "Correct!" if res["correct"] else f"Incorrect. The answer is: {fmt_choice(q['answer'])}")
            st.markdown(q["explanation"])
            if q["_ai"]:
                st.caption("This question and its answer key were written by AI. Double-check anything that looks off.")


def page_progress():
    st.markdown("# My Progress")
    s = compute_stats(ss.progress)
    if s["total_attempts"] == 0:
        st.info("No attempts yet. Open an example or start a quiz — your stats will appear here.")
    c = st.columns(4)
    for col, (label, val) in zip(c, [("Questions attempted", s["unique_attempted"]), ("Total attempts", s["total_attempts"]),
                                     ("Correct answers", s["correct"]), ("Accuracy", f"{s['accuracy']*100:.0f}%")]):
        with col, st.container(border=True):
            st.markdown(f'<div class="ll-kpi-label">{label}</div><div class="ll-kpi">{val}</div>', unsafe_allow_html=True)

    st.markdown("## By topic")
    for t in TOPICS:
        v = s["per_topic"][t]
        if v["attempts"]:
            st.progress(v["accuracy"], text=f"{t} — {v['correct']}/{v['attempts']} correct ({v['accuracy']*100:.0f}%)")
        else:
            st.progress(0.0, text=f"{t} — not attempted yet")

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Strengths** (≥ 75% accuracy)")
        st.markdown("\n".join(f"- {t}" for t in s["strengths"]) or "_Keep practicing to find your strengths._")
    with c2, st.container(border=True):
        st.markdown("**Needs work** (< 60% accuracy)")
        st.markdown("\n".join(f"- {t}" for t in s["weaknesses"]) or "_No weak topics yet._")

    st.markdown("## Recommended next examples")
    recs = recommend_examples(ss.progress)
    cols = st.columns(max(1, len(recs)))
    for col, e in zip(cols, recs):
        with col:
            example_card(e, "prog-rec")

    st.divider()
    if st.button("Reset all progress"):
        ss.progress = empty_progress()
        ss.results, ss.show_hint, ss.show_expl, ss.quiz = {}, set(), set(), None
        persist()
        st.rerun()


def page_about():
    st.markdown("# About LogicLab AI")
    st.markdown(
        """
LogicLab AI is a Samsung Innovation Campus project that helps beginners learn Python by **reading and predicting**
instead of writing code from scratch.

- **Predefined examples:** 23 verified programs across 10 topics, at beginner and intermediate levels.
- **Checking you can trust:** every answer is compared with a verified expected output. The AI never grades the built-in questions.
- **AI tutor (Gemini):** explains concepts, explains mistakes and writes extra practice questions.
- **Sample mode:** with no API key, all examples, checks, quizzes and progress still work, and built-in notes replace the AI.
- **Safe by design:** the app never runs code that users type.
- **Progress:** saved for this session and in a local `progress.json` file. No login needed.
"""
    )
    st.caption(f"AI status: {'Gemini connected' if gemini_available() else 'Sample mode (no GEMINI_API_KEY)'}")


# ---------------- Sidebar ----------------
def render_sidebar():
  with st.sidebar:
    st.markdown("### 🧪 LogicLab AI")
    st.caption("Learn Python by predicting output")
    st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    s = compute_stats(ss.progress)
    st.caption("Your progress")
    st.progress(min(1.0, len(s["solved"]) / len(EXAMPLES)), text=f"{len(s['solved'])}/{len(EXAMPLES)} examples solved")
    st.caption(f"Accuracy: {s['accuracy']*100:.0f}% · {s['total_attempts']} attempts")
    st.divider()
    if gemini_available():
        st.success("AI tutor: Gemini connected", icon="✨")
    else:
        st.info("Sample mode: no GEMINI_API_KEY. Everything except live AI answers works.", icon="ℹ️")



ROUTES = {"Home": page_home, "Explore Examples": page_explore, "Practice": page_practice,
          "My Progress": page_progress, "About": page_about}

try:
    ROUTES.get(ss.nav, page_home)()
except Exception as exc:  # last-resort guard so one bug never blanks the app
    st.error("Something went wrong on this page. Your progress is safe — try another page or refresh.")
    st.exception(exc)

render_sidebar()  # drawn after the page so stats include this run's attempt
