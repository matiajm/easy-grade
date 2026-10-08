# Easy Grade desktop app: test and build, step by step

This guide assumes you work in **Cursor** with the repo `matiajm/easy-grade` open.
Commands go in Cursor's terminal (**Terminal → New Terminal**). Lines starting with `#` are comments.

> **Student data rule.** The repo is public. Never commit real submissions, `_grading/` folders, or grade files.
> Only the fake sample data belongs in Git. Consider making the repo private before real data is anywhere near it.

---

## 0. One-time setup

1. **Install Python 3.12** from python.org (3.11 also works). Check it:
   ```bash
   python3 --version        # macOS
   py --version             # Windows
   ```
2. **Open the repo in Cursor**: File → Open Folder → `easy-grade`.
3. **Work on a branch** so `main` stays clean:
   ```bash
   git checkout -b desktop-app
   ```
4. **Create a virtual environment** (a private Python install for this project):
   ```bash
   # macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell)
   py -3.12 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   Your prompt now starts with `(.venv)`. Do this `activate` line every time you open a new terminal.
5. **Point Cursor at it**: `Cmd/Ctrl+Shift+P` → "Python: Select Interpreter" → pick the one in `.venv`.
6. **Install the dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
7. **Ignore files that must never be committed.** Add these lines to `.gitignore`:
   ```
   .venv/
   __pycache__/
   _grading/
   sample_data/
   *.db
   build/
   dist/
   *.spec
   ```

---

## 1. Run the automated tests

```bash
python -m unittest discover tests
```

Expected ending: `Ran 21 tests ... OK`. These cover the rubric, the database, the export, the
desktop API (open folder → rubric → grade → review → export → resume), video streaming, and notebook reading.
Run them after every change.

---

## 2. Make a sample folder to test with

```bash
python -m grader sample-folder sample_data
```

This creates `sample_data/submissions/` with 10 fictional students, using both layouts the importer supports,
a `roster.csv`, a real sample notebook (with charts) and a short sample video. It also includes the usual problems:
a late submission, a notebook saved without outputs, a missing video, a video sent as a link, and a student who submitted nothing.

---

## 3. Open the app

```bash
python app.py --folder sample_data/submissions --debug
```

- `--folder` opens straight into that folder. Without it you get the "Open submissions folder…" screen.
- `--debug` lets you right-click → **Inspect** to see the JavaScript console. Python errors print in the Cursor terminal.

---

## 4. Click-through checklist

| Step | Do this | You should see |
|---|---|---|
| 1 · Rubric | Click **Use the sample rubric** | 7 criteria, 100 points. `_grading/rubric.json` appears in the folder. |
| | Click a criterion row | Its levels open below it. |
| | **Save Excel template…** | A save dialog; the .xlsx opens in Excel with one row per level. |
| 2 · Submissions | Look at the table | 10 students with names from `roster.csv`, and flags for late, no outputs, no video, link, nothing submitted. |
| 3 · Grading | **Run simulated grader on 9 ungraded** | Progress bar, then 9 students "Needs review". (Made-up scores; real AI comes later.) |
| 4 · Review | Pick **Marcus Bell** | Notebook cells with charts on the left, score cards on the right. |
| | Click an evidence chip like `cell 5` | The notebook scrolls to that cell and highlights it. |
| | Switch to **Video**, click a `video 00:12` chip | The sample video jumps to 0:12. |
| | Click a different level on any criterion | The score changes, "changed from X" appears, plus a comment box. |
| | Type a comment, click elsewhere | "Comment saved." |
| | **Approve and go to next** | Marcus becomes Approved, the next student opens. |
| | Pick **Owen Park** (nothing submitted) | Approve is disabled until every criterion has a score. |
| 5 · Export | **Export all**, then **Show in Finder / Open folder** | `_grading/` has `grades.xlsx`, `gradebook.csv`, `feedback/`. |
| Resume | Close the app, run step 3 again | Everything is where you left it. |
| Errors | Open `grades.xlsx` in Excel, then **Export all** again (Windows) | A clear "close it in Excel" message, no crash. |

To start over: `python -m grader sample-folder sample_data` rebuilds the folder and deletes its `_grading/`.

---

## 5. Working on the screen without Python (optional)

The whole UI is `ui/index.html`. To change it quickly in a normal browser with fake data:

```bash
python -m http.server 8000
```

Open <http://localhost:8000/ui/index.html?mock> in Chrome. `ui/dev_mock.js` imitates the Python side.
Reload the page after each edit. Stop the server with `Ctrl+C`.

---

## 6. Build the double-clickable app

```bash
pip install -r requirements-dev.txt
python build_app.py
```

- **macOS:** `dist/Easy Grade.app`. Double-click to test, then open `sample_data/submissions` with it.
  The first time, macOS may say it can't verify the developer: right-click the app → **Open** → **Open**.
  Removing that warning permanently needs a paid Apple Developer account (code signing + notarization).
- **Windows:** `dist/Easy Grade/Easy Grade.exe`. Share the whole `Easy Grade` folder (zip it).
  It needs Microsoft Edge WebView2, which Windows 10/11 normally already have.
- Build on each system you need: a Mac build only runs on Mac, a Windows build only on Windows.
- To give it to the professor: zip `dist/Easy Grade.app` (or the Windows folder) and send it.
  Don't put builds in Git; attach them to a GitHub **Release** instead.

---

## 7. Commit and push

```bash
git status                      # check: no _grading/, sample_data/, dist/, .venv/
git add .
git commit -m "Desktop app: folder workflow, review screen, export"
git push -u origin desktop-app
```

Then open a Pull Request on GitHub so the team can review it before it goes into `main`.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: webview` | The venv isn't active. Run the `activate` line from step 0, then `pip install -r requirements.txt`. |
| Window opens but says "Start the app with Python" | You opened `ui/index.html` directly. Run `python app.py`. |
| Windows: pywebview install fails on `pythonnet` | Use Python 3.12 (`py -3.12 -m venv .venv`). |
| Video shows black / won't play | The file is .mov/.mkv/.avi, which the app window may not play. MP4 (H.264) is safest. |
| "already has scores under a different rubric" | You changed the rubric after grading. Use the replace button in step 1, or start a fresh folder. |
| App can't write `grades.xlsx` | Close it in Excel and export again. |

---

## How it fits together

```
app.py               opens the window, connects the page to Python
desktop/api.py       everything the screen can ask for (open folder, scores, approve, export)
desktop/media.py     local-only server so the window can play student videos
desktop/notebook.py  reads .ipynb files for display (text and images only)
ui/index.html        the screen (same design as the demo page)
ui/dev_mock.js       fake Python side for working on the screen in a browser
grader/              rubric, database, import, scoring contract, export (from step 1)
samples/             sample notebook and video used by sample-folder and the tests
build_app.py         packages the app with PyInstaller
```

Every `Api` method returns `{"ok": true, ...}` or `{"ok": false, "error": "message"}`, and the screen shows
the error message as-is, so write errors for the professor to read.

## AI grading

Notebook criteria can be graded by AI: see **[AI_GRADING.md](AI_GRADING.md)**.
The simulated grader is still available under **Testing tools** in the Grading step.
