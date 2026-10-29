# LogicLab AI

LogicLab AI helps beginners learn Python by **predicting the output of short programs**. It was built for a Samsung Innovation Campus project with Streamlit and the Google Gen AI SDK (Gemini).

## Features
- **Explore:** choose one of 10 Python topics and a Low, Medium, or Hard difficulty, then generate five fresh questions with your saved personal Gemini key. Generated sets remain available during the current session. Without a personal key, the app uses the verified built-in examples for that topic; Hard uses intermediate samples where available.
- **Check & Explain:** answer by multiple choice or by typing your prediction. Built-in answers are graded **deterministically** against verified output; generated questions are checked against their generated answer key. Extra spaces and blank lines are ignored, but the content must match. You also get Show Hint and Show Explanation.
- **Practice mode:** with a personal key, generate a five-question quiz at your chosen difficulty, with feedback after each question, a final score, mistake review, and an extra question at the same difficulty. Without one, the quiz uses matching built-in examples.
- **AI tutor (Gemini):** explains mistakes and topics. Tutoring can use the saved visitor key or configured deployment key.
- **Sample mode:** without an available key, Explore uses the 23 verified examples and quizzes use built-in questions.
- **My Progress:** attempts, correct answers, accuracy, accuracy per topic, strengths and weaknesses, and recommended next topics.
- **Safety:** the app never runs code that users type.

## Setup
Requires Python 3.10+.
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Gemini API key (optional)
1. Create a key at https://aistudio.google.com/apikey
2. Set it as an environment variable. Never put the key in the code.
   - macOS/Linux: `export GEMINI_API_KEY="your-key"`
   - Windows PowerShell: `$env:GEMINI_API_KEY="your-key"`
   - Or create `.streamlit/secrets.toml` containing `GEMINI_API_KEY = "your-key"`. This file is already listed in `.gitignore`.
3. Optional: set `GEMINI_MODEL` to change the model. The default is `gemini-2.5-flash`.

If there is no available key, the app runs in **sample mode**, and the sidebar tells you so. A visitor's saved key takes precedence over a configured deployment key for the tutor. Fresh question generation specifically requires the visitor's personal key, so users without one get the built-in sample questions even when the deployment has a key.

Visitors can also enter their own key in the app's first-visit prompt. Their key is
saved in that browser's local storage, takes precedence over the deployment key, and
can be changed or removed from the sidebar. It is not written to the repository or a
shared database, but it is sent to the app server when Gemini is used for tutoring or
personal-key question generation. Browser
storage is not encrypted, so visitors should not save keys on shared devices. They can
continue without a personal key to use the configured deployment key for tutoring and
sample mode for question generation.

Gemini-generated questions and answer keys are structurally validated, but the app
does not execute generated code or independently prove an AI-written answer. Review
its explanation if an answer seems incorrect.

## Run
```bash
streamlit run app.py
```
Then open http://localhost:8501.

## Test
```bash
pytest -q
```
The tests:
- run each **built-in** example once to prove its stored answer is the real output (only the tests do this; the app never runs code),
- confirm every multiple-choice question contains its answer exactly once,
- validate AI question-set difficulty, schema, and sample fallback,
- check grading, statistics and recommendations,
- drive the UI with Streamlit AppTest: generating fallback questions, checking an answer, the AI fallback, quiz scoring, progress updates, and reset.

## Manual test checklist
1. **Explore questions** → choose *Loops* and *Low* → generate and open *Summing with range()* in sample mode.
2. Pick `15` → **Check Answer**. You should see "Not quite" and the explanation should appear.
3. Click **Ask AI why my answer is wrong**. You'll get a Gemini answer if a key is set, otherwise the sample-mode text.
4. Switch to *Type my prediction*, type `10`, then **Check Answer**. You should see "Correct".
5. **Practice** → choose a topic and difficulty → start a quiz, answer each question, and review the final score.
6. **My Progress**: the numbers should match what you just did. **Reset all progress** clears them.

## Files
- `app.py`: the Streamlit interface (pages, navigation, styling)
- `logic.py`: grading, statistics, recommendations and Gemini calls with fallback (no Streamlit code)
- `examples_data.py`: examples, practice questions and offline concept notes
- `.streamlit/config.toml`: dark theme
- `tests/`: automated tests
- `progress.json`: created automatically to save progress between runs; delete it to start fresh
