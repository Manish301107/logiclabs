# LogicLab AI

LogicLab AI helps beginners learn Python by **predicting the output of ready-made programs**. It was built for a Samsung Innovation Campus project with Streamlit and the Google Gen AI SDK (Gemini).

## Features
- **23 predefined examples** across 10 topics (variables and data types, if/else, loops, strings, lists, tuples, dictionaries, functions, exceptions, OOP basics), each at beginner or intermediate level. Every example has a title, description, code, question, verified answer, hint and line-by-line explanation. You can browse them as cards, search them, and filter by topic or difficulty.
- **Check & Explain:** answer by multiple choice or by typing your prediction. Answers are graded **deterministically** against a verified output. Extra spaces and blank lines are ignored, but the content must match. You also get Show Hint and Show Explanation.
- **AI tutor (Gemini):** "Ask AI why my answer is wrong", "Ask the AI tutor about this topic", and "Generate a new practice question".
- **Practice mode:** a 4–5 question quiz per topic with feedback after each question, a final score, a review of your mistakes, and extra practice questions.
- **My Progress:** attempts, correct answers, accuracy, accuracy per topic, strengths and weaknesses, and recommended next examples. All of it comes from your real attempts.
- **Sample mode:** with no API key, everything still works and built-in notes and questions replace the AI.
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

If you skip this step, the app runs in **sample mode**, and the sidebar tells you so.

Visitors can also enter their own key in the app's first-visit prompt. Their key is
saved in that browser's local storage, takes precedence over the deployment key, and
can be changed or removed from the sidebar. It is not written to the repository or a
shared database, but it is sent to the app server when the tutor calls Gemini. Browser
storage is not encrypted, so visitors should not save keys on shared devices. They can
continue without a personal key to use the deployment key (if configured) or sample
mode.

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
- check grading, statistics and recommendations,
- drive the UI with Streamlit AppTest: choosing an example, filters, hint, a wrong answer and then a right one, the AI fallback, quiz scoring, progress updates, and reset.

## Manual test checklist
1. **Explore Examples** → filter by *Loops* → open *Summing with range()*.
2. Pick `15` → **Check Answer**. You should see "Not quite" and the explanation should appear.
3. Click **Ask AI why my answer is wrong**. You'll get a Gemini answer if a key is set, otherwise the sample-mode text.
4. Switch to *Type my prediction*, type `10`, then **Check Answer**. You should see "Correct".
5. **Practice** → choose a topic → answer every question. A final score appears, then try **Generate a new practice question**.
6. **My Progress**: the numbers should match what you just did. **Reset all progress** clears them.

## Files
- `app.py`: the Streamlit interface (pages, navigation, styling)
- `logic.py`: grading, statistics, recommendations and Gemini calls with fallback (no Streamlit code)
- `examples_data.py`: examples, practice questions and offline concept notes
- `.streamlit/config.toml`: dark theme
- `tests/`: automated tests
- `progress.json`: created automatically to save progress between runs; delete it to start fresh
