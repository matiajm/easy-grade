# AI grading (notebook criteria)

The app can now ask an AI model to draft scores for the rubric's **notebook** criteria.
Video criteria are still scored by hand in Review until the video grader is added.

## How it works

For each student, `grader/ai_grader.py`:

1. Reads the notebook: code, outputs, markdown and up to 8 chart images.
2. Replaces the student's full name, ID and email with `[STUDENT]` (Settings → "Remove names before sending").
3. Sends the rubric's notebook criteria and the notebook to the model. The model must answer through one tool,
   `submit_grades`, whose shape is `output_schema(rubric)`: one rubric level per criterion, a reason, evidence
   (`cell N`), a confidence, feedback and flags.
4. Checks the answer. If a score isn't one of the rubric's levels, it tells the model what was wrong and asks once
   more. If it's still wrong, that student is reported as failed and you grade it by hand.
5. Saves the scores as drafts (status "Needs review") and writes what was sent to `_grading/ai_log/<student>.json`
   (no API key, no image data).

Scores you changed by hand are kept when you re-grade. Nothing is final until you approve it.

## Step by step

### 1. Get the update into the repo

Do this in Cursor's terminal, inside your `easy-grade` folder:

```bash
git status                      # should say "nothing to commit"; commit first if not
git checkout desktop-app
git pull
git checkout -b ai-grading
cp -R ~/Downloads/easy-grade-ai-update/. .
git status
```

`git status` should show:

- **modified:** `.cursor/rules/easy-grade.mdc`, `README.md`, `desktop/api.py`, `desktop/notebook.py`,
  `docs/DESKTOP_APP.md`, `grader/scoring.py`, `requirements.txt`, `ui/index.html`
- **new:** `desktop/settings.py`, `docs/AI_GRADING.md`, `grader/ai_grader.py`, `grader/notebook.py`,
  `tests/test_ai_grader.py`

### 2. Install and test

```bash
source .venv/bin/activate
pip install -r requirements.txt     # adds certifi (SSL certificates for the API call)
python -m unittest discover tests   # expect: Ran 21 tests ... OK
```

The AI tests use a fake API: no key, no internet, no cost.

### 3. Add your API key in the app

```bash
python app.py --folder sample_data/submissions
```

1. Click **Settings** (top right).
2. Paste the API key, check the model name, and click **Save**.
3. Click **Test connection**. You should see "Connected. Model: …".

The key is saved only on this computer, in `~/Library/Application Support/Easy Grade/settings.json` (macOS)
or `%APPDATA%\Easy Grade\settings.json` (Windows). It is never written to the repo or the submissions folder.
Never paste the key into code, chat or commits. If it leaks, delete it in your API console and make a new one.

### 4. Grade the sample

1. In **1 · Rubric**, click **Use the sample rubric** if it isn't loaded yet.
2. In **3 · Grading**, click **Grade 9 ungraded notebooks with AI**. Three students are graded at a time.
   You see progress and tokens used. **Stop** finishes the students in progress, then stops.
3. In **4 · Review**, open a student. Notebook criteria now have AI reasons, `cell N` evidence and a
   confidence. Video criteria say "Not scored yet": click a level for each before you can approve.
4. Open `sample_data/submissions/_grading/ai_log/1002.json` to see exactly what was sent for Marcus.

To start fresh: `python -m grader sample-folder sample_data` (the API key is kept).

### 5. Commit and push

```bash
git add .
git commit -m "AI grading for notebook criteria, settings screen"
git push -u origin ai-grading
```

## Cost and limits

- The sample notebook is roughly 2,000 text tokens plus 2 small images per request, and about 700 tokens back.
  Real notebooks vary a lot. Grade 3–5 real ones first and check the cost in your API console before a full class.
- Set a monthly spending limit in the API console.
- To spend less: a smaller model in Settings, or turn off "Send chart images".

## Privacy

- Sent: the rubric, and the notebook's code, outputs, markdown and charts.
- Not sent: videos, the roster, emails, file names, grades.
- Name removal catches the full name, "Last, First", the ID (5+ characters) and the email. A first name written
  alone ("Hi, I'm Ana") is not caught. Single words aren't removed on purpose: a student named Price would
  otherwise erase every `price` column.
- Get the professor's college IT approval before grading real students (see the FERPA discussion in the team plan).

## Troubleshooting

| Message | Fix |
|---|---|
| "The API key was rejected" | Re-paste the key in Settings. Check it's active in the API console. |
| "Model '…' wasn't found" | Copy the exact model name from the API console into Settings. |
| "Too many requests or the spending limit was reached" | Wait a minute, or raise the limit in the console. |
| "Couldn't reach the AI service" | Check the internet connection. On a school network, a firewall may block it. |
| `CERTIFICATE_VERIFY_FAILED` in the terminal | `pip install -r requirements.txt` again (installs certifi). |
| "didn't fit the rubric twice" | Grade that student by hand. If it happens often, send me the `ai_log` file. |

## Code map

```
grader/ai_grader.py   request building, name removal, API call with retries, answer checking
grader/notebook.py    reads .ipynb (moved here from desktop/)
desktop/settings.py   API key and options, stored per computer user
desktop/api.py        get_settings, save_settings, test_connection, grade_student
ui/index.html         Settings window, AI buttons in Grading, progress, Stop
tests/test_ai_grader.py   fake-API tests
```
