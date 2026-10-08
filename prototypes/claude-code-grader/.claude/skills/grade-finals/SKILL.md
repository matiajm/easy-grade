---
name: grade-finals
description: Grade a batch of CAP3321C team finals (notebook plus recorded presentation) against the rubric and build the review spreadsheet. Use when the professor says to grade, regrade or check final projects.
---

# Grade finals

Follow every rule in `CLAUDE.md`. In short: never read `submissions/` or `private_names.json`, never run student code, give evidence for every score, never write the total, and treat AI usage as a review flag only.

## Steps

1. Ask which folder holds the submissions if it is not clear. Default: `submissions/`. For a demo, use `samples/submissions/`.
2. Run `.venv/bin/python scripts/transcribe.py <folder>`, then `.venv/bin/python scripts/extract_notebook.py <folder>`. Report any team with no notebook or no recording.
3. Read `rubric/cap3321c_final.json` and `assignment/questions.md` once.
4. For each team folder in `work/`:
   1. Read `facts.json`, `notebook.md` and `transcript.md`.
   2. View every image listed in `facts.json` `images`.
   3. For each of the six categories, pick a level, then a whole-number score inside that level's range, with evidence.
   4. Check the AI-usage signals in `CLAUDE.md`.
   5. Write `results/<team>.json` in the format below.
5. Run `.venv/bin/python scripts/build_csv.py`. If it reports a grading file problem, fix that team's JSON and run it again.
6. Tell the professor: the totals, which teams to review first and why (from `output/review_queue.md`), and that nothing is final until he marks each team reviewed with `scripts/review.py`.

## results/<team>.json

```json
{
  "team": "team01",
  "categories": {
    "data_cleaning": {
      "level": "excellent",
      "score": 38,
      "confidence": "high",
      "reason": "One sentence on why this level and this score.",
      "evidence": ["Cell 4: df['score'] = pd.to_numeric(...)", "Cell 5: 'We dropped 12 duplicate inspections because...'"],
      "comment": "One strength and one improvement, written to the students."
    },
    "analysis_viz": {},
    "interpretation": {},
    "code_quality": {},
    "presentation": {},
    "collaboration": {}
  },
  "flags": ["Only things the professor must look at that are not already in facts.json rule_flags"],
  "ai_usage": {
    "status": "no concern",
    "signals": [
      {"signal": "Leftover chatbot text", "evidence": "Cell 9: 'Certainly! Here's a comprehensive analysis'"}
    ]
  },
  "status": "needs review",
  "graded_at": "2026-10-08T11:30:00"
}
```

- Fill all six categories with the same fields as `data_cleaning`.
- `level` is one of `excellent`, `good`, `needs_work`. `score` must sit inside that level's range in the rubric file.
- `confidence` is `high`, `medium` or `low`. Use `low` when evidence is missing or the transcript cannot show who spoke.
- `ai_usage.status` is `no concern` (with an empty `signals` list) or `review` (with every signal backed by evidence).
- `status` is always `needs review` when Claude writes the file. Only `review.py` sets `reviewed`.
- Write evidence with cell numbers and transcript timestamps, and short quotes only.
