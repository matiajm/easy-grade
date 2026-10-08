# Colab Grader — Step 1 prototype

Rubric-based grading for project assignments that include a Colab notebook (`.ipynb`) and a video walkthrough.
This step builds the parts every later step depends on: **the rubric, the grade store, and the export.**
AI notebook grading (step 2) and video grading (step 3) plug into the contract in `grader/scoring.py`.

## Desktop app

```bash
pip install -r requirements.txt
python -m grader sample-folder sample_data              # fake submissions to try it on
python app.py --folder sample_data/submissions          # open the app
```

Full step-by-step (setup in Cursor, test checklist, building the .app/.exe): **[docs/DESKTOP_APP.md](docs/DESKTOP_APP.md)**.
AI grading of notebook criteria (API key, privacy, cost): **[docs/AI_GRADING.md](docs/AI_GRADING.md)**.

## Command line

```bash
python -m grader demo demo_output       # runs the whole loop on fake data
python -m unittest discover tests       # 21 tests
```

Open `demo_output/grades.xlsx` to see the final export.

## The loop

| Step | Command | What happens |
|---|---|---|
| 1. Rubric | `python -m grader add-rubric rubrics/project2_regression.json` | Validates and saves the rubric. Also accepts `.xlsx` / `.csv`. |
| | `python -m grader rubric-template my_rubric.xlsx --with-example` | Excel template the professor fills in (one row per level). |
| 2. Import | `python -m grader ingest "<assignment>" submissions/ --roster roster.csv` | Matches each student to a notebook and a video, flags problems. |
| 3. Grade | *(step 2/3: AI)* or `scores-template` + `load-scores` | Scores per criterion. AI must pick one of the rubric's levels. |
| 4. Review | `python -m grader status "<assignment>"`, `approve --all` | Professor changes scores and approves. Edits are tracked. |
| 5. Export | `python -m grader export "<assignment>" --xlsx grades.xlsx --csv gradebook.csv --feedback-dir feedback/` | Everything analyzed, in one go. |

All data lives in one local SQLite file (`--db grades.db`), saved after every student.

## What the export contains

**`grades.xlsx`**
- **Summary**: one row per student, one column per criterion, live `SUM` total and percent, class averages. Scores the professor changed are in red; unapproved rows are yellow.
- **Detail**: every student × criterion with AI level, AI score, final score, confidence, reason and evidence (e.g. `cell 14`, `video 03:42`). Low-confidence rows are highlighted.
- **Feedback**: the comment for each student.
- **Flags**: late, missing video, notebook never run, video sent as a link, not on roster…
- **Rubric**: the rubric used, for the record.

**Gradebook CSV** (approved grades only by default)
- Simple: `student_id, student_name, email, score, points_possible`.
- Or pass `--lms-template` with the gradebook CSV exported from the LMS: the assignment's column is filled in place and the file can be imported straight back.

**Feedback files**: one `.txt` per student with the score breakdown and comments.

## Rubric format

Each criterion has an `id`, `name`, `points`, `source` (`notebook`, `video` or `both`) and levels. The top level must equal the points. See `rubrics/project2_regression.json`.

## Supported submission layouts

- One folder per student: `submissions/<student_id>/project.ipynb`, `walkthrough.mp4`
- Flat LMS bulk download: `<name>_<userid>_<subid>_<file>` (a `late` segment marks late work)

## Files

```
grader/rubric.py    rubric model, validation, Excel/CSV import, template
grader/store.py     SQLite store: assignments, submissions, scores (AI vs final)
grader/ingest.py    finds notebooks/videos per student, flags problems
grader/scoring.py   AI output JSON schema + validator, manual scores, simulated grader
grader/ai_grader.py AI notebook grader (Anthropic API)
grader/notebook.py  reads .ipynb files
grader/export.py    Excel workbook, gradebook CSV, feedback files
grader/cli.py       command line + demo
app.py              desktop app entry point
desktop/            the Python side of the app window (api, video server, notebook reader)
ui/                 the app screen (index.html) + dev_mock.js for browser-only UI work
samples/            sample notebook and video for testing
build_app.py        packages the app with PyInstaller
```

## Next steps

2. Notebook grader: parse/run the `.ipynb`, send cells + outputs + rubric to the model with `output_schema()`.
3. Video grader: local Whisper transcript + sampled frames, same schema for `video`/`both` criteria.
4. ~~Desktop review screen~~ done: see docs/DESKTOP_APP.md.
