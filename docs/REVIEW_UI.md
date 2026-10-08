# The review dashboard

The app's screen follows Valery's design (`docs/design/review-flow-sketch.html`) and runs on the app's real backend
(`desktop/`, `grader/`). It also uses Matias's notebook parser and export guard (`easygrade/`). Everything here uses fake
sample data unless you open a real folder.

## The flow

1. **Start.** Pick the rubric (a dropdown of the app's rubrics, with a preview of each category's point ranges) or
   **Replace rubric** with an Excel, CSV or JSON file: you see what was read before you use it. Choose the submissions
   folder, or **Use the sample folder** (10 fake CAP3321C teams). Changing the rubric of a graded batch asks first.
2. **Check the matches.** Each team's notebook and video, matched by the names in the file names. A team with no video
   gets a menu: pick a loose file that doesn't name a student (like `IMG_4821.MOV`), or "No video for this team". Both
   choices are saved in `_grading/matching.json` and can be undone. Then choose how grades are suggested: **AI** (needs a
   key in Settings), **made-up scores** (testing only), or **by hand**.
3. **Grading.** Finds the files, reads every notebook with the notebook parser (header, file name, run order, errors),
   then suggests grades. Video transcription is not connected yet, so that step shows as skipped and the presentation
   score is yours to enter.
4. **Review.** One row per team: grade, what needs your attention, AI usage, and **Mark reviewed**. A row opens into an
   overall summary with the strongest and weakest category, what to check, and how the grade adds up (a bar, the level,
   the reason and the evidence for each category). **Change a score** types any number from 0 to the category's points; the
   level, the total and the strongest/weakest follow. Evidence chips (`cell 5`, `video 00:12`) open a drawer with the
   notebook (the cell highlighted) or the video at that moment. A team with a missing score shows **Add missing score**
   and can't be marked reviewed.
5. **Download.** **Download Excel** writes `_grading/grades_review.xlsx` (Grades, Details, Rubric tabs, with formulas, so
   changing a yellow score on Details updates the level, the team total and the Grades tab). **Download CSV** writes
   `_grading/grades.csv` (student name, score, needs your attention, AI usage; one row per student, the team's grade for
   each). Only reviewed teams are written, and both go through the export guard (`easygrade/pipeline/export/guard.py`):
   a team whose total isn't the sum of its scores, or that has a missing score, is refused and listed. Names and comments
   that start with `=`, `+`, `-` or `@` are neutralised. Each CSV export is logged by team id in `export_log.jsonl`.
   **More exports** keeps the older full export (Excel summary, gradebook CSV, feedback files).

## How the data maps

| The design shows | It comes from |
|---|---|
| A team | One submission (student id). Names like `Isabel Moreno & Daniel Park` in `roster.csv` become the team's members. |
| Grade, level, bar | The category scores. A level covers a range (`min` in the rubric JSON); the AI picks one level and gets its `score`. |
| What to check | Missing scores, the import flags (late, no video...), the parser's findings, and AI "only X% sure" notes. |
| Overall, strongest, weakest | Built by code from the scores. |
| AI usage | **Not connected.** Every team shows "Not checked" and the Excel says "Not checked". Nothing is invented. |

## Try it in a browser

```bash
python -m desktop.devserver        # http://127.0.0.1:8765/
```

The page is the same `ui/index.html`; `ui/dev_bridge.js` replaces pywebview and sends each call to the real backend.
Settings are read from your user folder as usual, so use a throwaway `EASYGRADE_CONFIG_DIR` if you don't want a saved
key to be used.

## Tests

- `tests/test_review_api.py`: rubric ranges, matching, notebook checks, the review list and the guarded exports.
- `tests/test_ui_e2e.py`: the whole flow in a headless Edge or Chrome, on fake data, with settings isolated so no key is
  found. Needs `playwright` (skipped without it). `EASYGRADE_UI_SHOTS=<folder>` saves a screenshot of every screen.

## Known gaps

- **AI usage** and **video transcripts** are not connected, so the AI-usage column is "Not checked" and the
  presentation is scored by hand.
- The AI grader (Lucas's) grades the notebook categories only. The AI's score for a level is the top of the range for
  Excellent and the middle for the others; the professor adjusts.
- A team's name comes from `roster.csv` or the file name. Teams are graded as one submission; the CSV and Excel write one
  row per member.
