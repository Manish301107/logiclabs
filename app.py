"""LogicLab AI — learn Python by predicting output.

Run:  streamlit run app.py
Never executes user-submitted code. Answers are checked deterministically
against verified expected outputs stored in examples_data.py.
"""
from __future__ import annotations

from html import escape
from uuid import uuid4

import streamlit as st

from api_key_storage import mount_api_key_storage
from examples_data import EXAMPLES, TOPICS
from logic import (
    EXAMPLES_BY_ID,
    build_quiz,
    check_answer,
    compute_stats,
    DIFFICULTIES,
    empty_progress,
    explain_concept,
    explain_wrong,
    gemini_available,
    generate_practice,
    generate_question_set,
    load_progress,
    recommend_examples,
    record_attempt,
    save_progress,
    sample_questions,
)

st.set_page_config(page_title="LogicLab AI — Learn Python by Predicting", page_icon="🧪", layout="wide")

PAGES = ["Home", "Explore Examples", "Practice", "My Progress", "About"]

# ---------------- Styles ----------------
st.markdown(
    """
<style>
:root{--ll-bg:#0b1020;--ll-panel:#111827;--ll-panel-2:#182338;--ll-border:#283449;--ll-text:#e8ecf5;
--ll-muted:#a2aec2;--ll-accent:#b4a5ff;--ll-accent-soft:rgba(164,142,255,.13);--ll-ok:#6ee7b7;--ll-bad:#fda4af;}
html,body{font-family:Inter,"Segoe UI Variable","Segoe UI",system-ui,sans-serif;}
.block-container{max-width:1220px;}
h1{font-size:1.95rem!important;font-weight:700!important;letter-spacing:-.04em;line-height:1.2!important;}
h2{font-size:1.4rem!important;font-weight:650!important;letter-spacing:-.025em;}
h3{font-size:1.1rem!important;font-weight:650!important;}
div[data-testid="stAppViewContainer"]{background:
radial-gradient(ellipse at 12% 0%,rgba(114,87,216,.13),transparent 34%),
radial-gradient(ellipse at 95% 35%,rgba(56,189,248,.035),transparent 28%),var(--ll-bg);}
div[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--ll-border)!important;
background:linear-gradient(145deg,rgba(255,255,255,.035),transparent 58%),var(--ll-panel);
border-radius:18px;box-shadow:0 12px 30px rgba(0,0,0,.14);transition:border-color .18s ease, transform .18s ease, box-shadow .18s ease;}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:#51477f!important;transform:translateY(-2px);
box-shadow:0 16px 36px rgba(0,0,0,.22);}
.ll-badge{display:inline-block;font-size:.72rem;padding:.12rem .55rem;border-radius:999px;margin-right:.35rem;
border:1px solid var(--ll-border);color:#bac5d8;background:var(--ll-panel-2);font-weight:550;}
.ll-badge.accent{color:#d5ccff;background:var(--ll-accent-soft);border-color:#51477f;}
.ll-muted{color:var(--ll-muted);font-size:.94rem;line-height:1.65;}
.ll-key-title{font-size:1.25rem;font-weight:700;letter-spacing:-.025em;margin-bottom:.3rem;}
.ll-kpi{font-size:1.8rem;font-weight:700;line-height:1.15;letter-spacing:-.035em;margin-top:.25rem;}
.ll-kpi-label{color:var(--ll-muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.09em;font-weight:600;}
.ll-hero{padding:1.7rem 1.8rem;border:1px solid #342e55;border-radius:18px;background:
radial-gradient(ellipse at 90% 0%,rgba(164,142,255,.18),transparent 48%),
linear-gradient(145deg,rgba(114,87,216,.09),transparent 65%),var(--ll-panel);margin-bottom:1.3rem;
box-shadow:0 16px 40px rgba(0,0,0,.16);}
.ll-ok{color:var(--ll-ok);font-weight:650}.ll-bad{color:var(--ll-bad);font-weight:650}
.stButton>button{border-radius:.7rem;border:1px solid var(--ll-border);font-weight:600;
transition:border-color .15s ease,background .15s ease,transform .15s ease,box-shadow .15s ease;min-height:2.65rem;}
.stButton>button:hover{border-color:#8f7af0;background:rgba(164,142,255,.07);transform:translateY(-1px);
box-shadow:0 5px 16px rgba(114,87,216,.16);}
.stButton>button[kind="primary"]{box-shadow:0 4px 14px rgba(114,87,216,.2);}
[data-testid="stForm"]{border:0;padding:0;}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] [data-baseweb="select"]>div{border-radius:.7rem;}
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus{border-color:#8f7af0;
box-shadow:0 0 0 1px #8f7af0;}
div[data-testid="stCode"]{border:1px solid var(--ll-border);border-radius:12px;overflow:hidden;}
div[data-testid="stProgressBar"]>div>div{background:linear-gradient(90deg,#7257d8,#a78bfa);}
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
ss.setdefault("generated_explore", {})  # (topic, difficulty) -> generated question set
ss.setdefault("practice_difficulty", "Medium")
ss.setdefault("extra_q", {})       # topic -> question dict
ss.setdefault("extra_result", {})  # topic -> {"choice", "correct"}
ss.setdefault("visitor_gemini_api_key", None)
ss.setdefault("api_key_setup_done", False)
ss.setdefault("api_key_dialog_open", False)
ss.setdefault("pending_api_key_command", None)
ss.setdefault("api_key_storage_error", None)


def persist():
    save_progress(ss.progress)


def queue_api_key_command(action: str, api_key: str | None = None):
    ss.pending_api_key_command = {
        "id": uuid4().hex,
        "action": action,
        "apiKey": api_key,
    }
    ss.api_key_dialog_open = False


def save_visitor_api_key(api_key: str):
    api_key = api_key.strip()
    if not api_key:
        ss.api_key_input_error = "Enter a Gemini API key, or continue without one."
        return
    ss.pop("api_key_input_error", None)
    queue_api_key_command("save", api_key)


def skip_visitor_api_key():
    ss.pop("api_key_input_error", None)
    ss.pop("visitor_gemini_api_key_input", None)
    queue_api_key_command("skip")


def clear_visitor_api_key():
    ss.pop("api_key_input_error", None)
    ss.pop("visitor_gemini_api_key_input", None)
    queue_api_key_command("clear")


def open_api_key_dialog():
    ss.api_key_dialog_open = True
    ss.pop("api_key_input_error", None)
    ss.pop("visitor_gemini_api_key_input", None)


@st.dialog("Connect your Gemini API key")
def api_key_dialog():
    with st.container(border=True):
        st.markdown(
            '<div class="ll-key-title">Bring your own Gemini key</div>'
            '<div class="ll-muted">Use your own quota for AI explanations and extra practice. '
            'You can replace or remove the key any time.</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Saved only in this browser. The key is sent to this app server when the AI "
            "tutor is used. Don’t save it on a shared device."
        )
        if ss.get("api_key_input_error"):
            st.error(ss.api_key_input_error)

        with st.form("visitor-gemini-key-form", clear_on_submit=False):
            api_key = st.text_input(
                "Gemini API key",
                type="password",
                key="visitor_gemini_api_key_input",
                placeholder="Paste your Gemini API key",
                help="Create or manage your key in Google AI Studio.",
            )
            save_clicked = st.form_submit_button(
                "Save key",
                type="primary",
                key="save_visitor_gemini_api_key",
                width="stretch",
            )
            skip_clicked = st.form_submit_button(
                "Continue without changing" if ss.api_key_setup_done
                else "Continue without a personal key",
                key="skip_visitor_gemini_api_key",
                width="stretch",
            )
            if ss.visitor_gemini_api_key:
                remove_clicked = st.form_submit_button(
                    "Remove saved key",
                    key="clear_visitor_gemini_api_key",
                    width="stretch",
                )
            else:
                remove_clicked = False

        if save_clicked:
            save_visitor_api_key(api_key)
            if not ss.get("api_key_input_error"):
                st.rerun()
        elif skip_clicked:
            skip_visitor_api_key()
            st.rerun()
        elif remove_clicked:
            clear_visitor_api_key()
            st.rerun()


def go(page: str, example_id: str | None = None):
    ss.nav = page
    if example_id is not None:
        ss.selected = example_id


def go_to_topic(topic: str):
    ss.nav = "Explore Examples"
    ss.recommended_topic = topic
    ss.selected = None


def find_explore_question(question_id: str):
    if question_id in EXAMPLES_BY_ID:
        return EXAMPLES_BY_ID[question_id]
    for question_set in ss.generated_explore.values():
        for question in question_set["questions"]:
            if question["id"] == question_id:
                return question
    return None


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
        if e.get("_ai"):
            st.caption("AI-generated")
        st.markdown(f"**{e['title']}**")
        st.markdown(f'<div class="ll-muted">{escape(e["description"])}</div>', unsafe_allow_html=True)
        st.button("Open question →", key=f"{key_prefix}-{e['id']}", on_click=go,
                  args=("Explore Examples", e["id"]), width="stretch")


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
                                     ("Examples solved", f"{len(s['solved'] & set(EXAMPLES_BY_ID))}/{len(EXAMPLES)}")]):
        with col, st.container(border=True):
            st.markdown(f'<div class="ll-kpi-label">{label}</div><div class="ll-kpi">{val}</div>', unsafe_allow_html=True)

    st.markdown("## Recommended topics")
    recs = recommend_examples(ss.progress)
    if recs:
        cols = st.columns(len(recs))
        for col, e in zip(cols, recs):
            with col, st.container(border=True):
                st.markdown(f"**{e['topic']}**")
                st.markdown('<div class="ll-muted">Generate a fresh set at the difficulty you choose.</div>',
                            unsafe_allow_html=True)
                st.button(
                    "Choose topic →",
                    key=f"home-rec-{e['topic']}",
                    on_click=go_to_topic,
                    args=(e["topic"],),
                    width="stretch",
                )
    else:
        st.success("You've practiced every sample topic — try a new quiz in Practice mode.")

    st.markdown("## How it works")
    h = st.columns(3)
    steps = [("1 · Pick a topic", "Generate fresh Python questions across 10 topics."),
             ("2 · Predict the output", "Type your prediction or pick from multiple choices, then Check Answer."),
             ("3 · Learn from it", "Get a hint, a line-by-line explanation, or ask the AI tutor why.")]
    for col, (t, d) in zip(h, steps):
        with col, st.container(border=True):
            st.markdown(f"**{t}**")
            st.markdown(f'<div class="ll-muted">{d}</div>', unsafe_allow_html=True)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.button("Explore topics", type="primary", on_click=go, args=("Explore Examples",), width="stretch")
    b2.button("Start a quiz", on_click=go, args=("Practice",), width="stretch")


def render_detail(e):
    st.button("← Back to questions", on_click=lambda: ss.update(selected=None))
    st.markdown(badges(e), unsafe_allow_html=True)
    st.markdown(f"# {e['title']}")
    st.markdown(f'<div class="ll-muted">{escape(e["description"])}</div>', unsafe_allow_html=True)
    if e.get("_ai"):
        st.caption("AI-generated question and answer key. Review the explanation if anything seems incorrect.")
    st.code(e["code"], language="python", line_numbers=True)
    st.markdown(f"**{e['question']}**")

    mode = st.radio("Answer mode", ["Multiple choice", "Type my prediction"], horizontal=True, key=f"mode-{e['id']}")
    if mode == "Multiple choice":
        user = st.radio("Choose the output", e["choices"], index=None, format_func=fmt_choice, key=f"mc-{e['id']}")
    else:
        user = st.text_area("Type the exact output (one line per print)", key=f"tx-{e['id']}", height=110,
                            placeholder="e.g. 3.5 3")

    c1, c2, c3 = st.columns(3)
    check = c1.button("Check Answer", type="primary", key=f"chk-{e['id']}", width="stretch")
    if c2.button("Show Hint", key=f"hint-{e['id']}", width="stretch"):
        ss.show_hint.add(e["id"])
    if c3.button("Show Explanation", key=f"exp-{e['id']}", width="stretch"):
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
            if isinstance(e["explanation"], list):
                for line in e["explanation"]:
                    st.markdown(f"- {line}")
            else:
                st.markdown(e["explanation"])

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
    if ss.selected:
        question = find_explore_question(ss.selected)
        if question:
            render_detail(question)
            return
        ss.selected = None
    st.markdown("# Explore questions")
    st.markdown(
        '<div class="ll-muted">Choose a topic and difficulty, then generate five fresh questions. '
        'Fresh question generation uses your saved personal Gemini key; otherwise, verified sample questions are shown.</div>',
        unsafe_allow_html=True,
    )
    if "recommended_topic" in ss:
        ss.f_topic = ss.pop("recommended_topic")
    if ss.get("f_topic") not in TOPICS:
        ss.pop("f_topic", None)
    topic = st.selectbox("Topic", TOPICS, key="f_topic")
    difficulty = st.segmented_control(
        "Difficulty",
        list(DIFFICULTIES),
        default="Medium",
        key="f_difficulty",
    )
    if difficulty not in DIFFICULTIES:
        st.warning("Choose a difficulty to continue.")
        return
    set_key = f"{topic}|{difficulty}"
    if st.button("Generate 5 questions", type="primary", key="generate-explore"):
        fallback = sample_questions(topic, difficulty)
        previous = [
            question
            for key, saved_set in ss.generated_explore.items()
            if key.startswith(f"{topic}|")
            for question in saved_set["questions"]
        ]
        with st.spinner("Generating fresh questions…"):
            questions, from_ai, error = generate_question_set(
                topic,
                difficulty,
                size=5,
                fallback_questions=fallback,
                avoid_questions=previous,
            )
        ss.generated_explore[set_key] = {
            "questions": questions,
            "from_ai": from_ai,
            "error": error,
        }
        ss.selected = None

    question_set = ss.generated_explore.get(set_key)
    if not question_set:
        st.info("Your questions will appear here after you generate a set.")
        return
    if question_set["error"]:
        st.info(question_set["error"])
    if question_set["from_ai"]:
        st.caption(f"Fresh {difficulty.lower()} questions generated for {topic}.")
    else:
        st.caption(
            f"Showing {len(question_set['questions'])} verified sample questions for {topic}. "
            "Hard uses intermediate samples where available."
            if difficulty == "Hard"
            else f"Showing {len(question_set['questions'])} verified sample questions for {topic}."
        )
    st.markdown(f"## {topic} · {difficulty}")
    cols = st.columns(3)
    for i, e in enumerate(question_set["questions"]):
        with cols[i % 3]:
            example_card(e, "exp")


def page_practice():
    st.markdown("# Practice")
    quiz = ss.quiz
    if quiz is None:
        st.markdown('<div class="ll-muted">A short multiple-choice quiz on one topic. Feedback after every question.</div>',
                    unsafe_allow_html=True)
        topic = st.selectbox("Choose a topic", TOPICS, key="quiz_topic")
        difficulty = st.segmented_control(
            "Difficulty",
            list(DIFFICULTIES),
            default=ss.practice_difficulty,
            key="practice_difficulty",
        )
        if difficulty not in DIFFICULTIES:
            st.warning("Choose a difficulty to continue.")
            return
        st.caption(
            "Your personal Gemini key creates five fresh questions. Without one, sample mode uses the verified examples "
            "closest to this difficulty."
        )
        if st.button("Start quiz", type="primary"):
            fallback = build_quiz(topic, difficulty=difficulty)
            with st.spinner("Preparing your quiz…"):
                questions, from_ai, error = generate_question_set(
                    topic, difficulty, size=5, fallback_questions=fallback
                )
            ss.quiz = {
                "topic": topic,
                "difficulty": difficulty,
                "questions": questions,
                "from_ai": from_ai,
                "error": error,
                "idx": 0,
                "answers": {},
            }
            st.rerun()
        return

    qs, idx = quiz["questions"], quiz["idx"]
    if quiz.get("error"):
        st.info(quiz["error"])
    difficulty = quiz.get("difficulty", "Medium")
    from_ai = quiz.get("from_ai", False)
    st.caption(f"{difficulty} · {'AI-generated' if from_ai else 'verified sample questions'}")
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
            render_extra_question(
                quiz["topic"],
                {q["id"] for q in qs},
                difficulty,
            )
        c1, c2 = st.columns(2)
        if c1.button("Retake quiz", width="stretch"):
            ss.quiz = {**quiz, "idx": 0, "answers": {}}
            st.rerun()
        if c2.button("Choose another topic", width="stretch"):
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
                    record_attempt(
                        ss.progress,
                        q["id"],
                        q["topic"],
                        ok,
                        "ai-practice" if from_ai else "practice",
                    )
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


def render_extra_question(topic: str, avoid: set, difficulty: str):
    key = f"{topic}|{difficulty}"
    if st.button("✨ Generate a new practice question", key=f"gen-{key}"):
        previous = [
            question
            for saved_key, question in ss.extra_q.items()
            if saved_key.startswith(f"{topic}|")
        ]
        with st.spinner("Creating a question…"):
            q, from_ai, err = generate_practice(topic, avoid, difficulty, previous)
        ss.extra_q[key] = {**q, "_ai": from_ai, "_err": err}
        ss.extra_result.pop(key, None)
    q = ss.extra_q.get(key)
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
        res = ss.extra_result.get(key)
        choice = st.radio("Your answer", q["choices"], index=None, format_func=fmt_choice,
                          key=f"xq-{key}-{q['id']}", disabled=bool(res))
        if not res and st.button("Check Answer", key=f"xchk-{key}"):
            if choice is None:
                st.warning("Pick an answer first.")
            else:
                ok = check_answer(choice, q["answer"])
                ss.extra_result[key] = {"choice": choice, "correct": ok}
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

    st.markdown("## Recommended topics")
    recs = recommend_examples(ss.progress)
    cols = st.columns(max(1, len(recs)))
    for col, e in zip(cols, recs):
        with col, st.container(border=True):
            st.markdown(f"**{e['topic']}**")
            st.markdown('<div class="ll-muted">Generate a fresh set at your chosen difficulty.</div>',
                        unsafe_allow_html=True)
            st.button(
                "Choose topic →",
                key=f"prog-rec-{e['topic']}",
                on_click=go_to_topic,
                args=(e["topic"],),
                width="stretch",
            )

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

- **Fresh questions:** generate five questions for any topic and choose Low, Medium, or Hard difficulty. A saved personal key is required; otherwise the verified sample questions are used.
- **Checking:** answers are compared with the question's answer key. Built-in sample questions have verified answers; AI-generated answer keys may need review.
- **AI tutor (Gemini):** explains concepts and mistakes. Tutoring can use the saved visitor key or configured deployment key.
- **Sample mode:** without a personal key, Explore, quizzes, and extra practice use the verified examples.
- **Safe by design:** the app never runs code that users type.
- **Progress:** saved for this session and in a local `progress.json` file. No login needed.
- **Your Gemini key:** optional visitor keys are stored in the current browser and sent to this app's server only when calling Gemini. Avoid saving keys on shared devices.
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
    solved_examples = len(s["solved"] & set(EXAMPLES_BY_ID))
    st.progress(min(1.0, solved_examples / len(EXAMPLES)), text=f"{solved_examples}/{len(EXAMPLES)} examples solved")
    st.caption(f"Accuracy: {s['accuracy']*100:.0f}% · {s['total_attempts']} attempts")
    st.divider()
    if gemini_available():
        st.success("AI tutor: Gemini connected", icon="✨")
        st.caption(
            "Using your saved key." if ss.visitor_gemini_api_key
            else "The tutor uses the app's configured key; fresh question generation requires your personal key."
        )
    else:
        st.info("Sample mode: built-in questions are available. Add a key for fresh Gemini questions.", icon="ℹ️")
    st.button(
        "Change API key" if ss.visitor_gemini_api_key else "Add your Gemini API key",
        on_click=open_api_key_dialog,
        width="stretch",
    )



ROUTES = {"Home": page_home, "Explore Examples": page_explore, "Practice": page_practice,
          "My Progress": page_progress, "About": page_about}

pending_api_key_command = ss.pending_api_key_command
api_key_storage_state = mount_api_key_storage(pending_api_key_command)
command_acknowledged = bool(
    pending_api_key_command
    and api_key_storage_state.get("command_id") == pending_api_key_command["id"]
)

if not api_key_storage_state.get("ready") or (pending_api_key_command and not command_acknowledged):
    st.info("Loading your saved AI settings…" if not pending_api_key_command else "Saving your key in this browser…")
    st.stop()

if command_acknowledged:
    if api_key_storage_state.get("error"):
        if pending_api_key_command["action"] == "save":
            ss.visitor_gemini_api_key = pending_api_key_command["apiKey"]
        elif pending_api_key_command["action"] == "clear":
            ss.visitor_gemini_api_key = None
        ss.api_key_setup_done = True
        ss.api_key_storage_error = api_key_storage_state["error"]
    else:
        ss.visitor_gemini_api_key = api_key_storage_state.get("api_key")
        ss.api_key_setup_done = bool(api_key_storage_state.get("setup_done"))
        ss.api_key_storage_error = None
    ss.pending_api_key_command = None
elif not api_key_storage_state.get("error"):
    ss.visitor_gemini_api_key = api_key_storage_state.get("api_key")
    ss.api_key_setup_done = bool(api_key_storage_state.get("setup_done"))
    ss.api_key_storage_error = None
else:
    ss.api_key_storage_error = api_key_storage_state["error"]

if ss.api_key_storage_error:
    st.warning(ss.api_key_storage_error)

try:
    ROUTES.get(ss.nav, page_home)()
except Exception as exc:  # last-resort guard so one bug never blanks the app
    st.error("Something went wrong on this page. Your progress is safe — try another page or refresh.")
    st.exception(exc)

render_sidebar()  # drawn after the page so stats include this run's attempt
if not ss.api_key_setup_done or ss.api_key_dialog_open:
    api_key_dialog()
