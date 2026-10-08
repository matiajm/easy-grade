# EasyGrade

A first-pass grader for CAP3321C team finals (Jupyter notebook plus recorded presentation). The recording is transcribed on this computer, Claude grades the transcript and notebook against the rubric with evidence, plain code checks the scores and builds a spreadsheet, and the professor reviews and approves every grade.

Rules and details: [CLAUDE.md](CLAUDE.md).

## Status: reference prototype, not the team pipeline

Built for the 2026-10-08 demo to show the whole loop working end to end on synthetic data. It does **not** use the bundle contract in `TEAM PLAN UPDATED.md` yet, and it does not replace anyone's part. Pieces the owners may want to reuse:

| Prototype file | Team plan part (owner) |
|---|---|
| `scripts/transcribe.py` (local faster-whisper, low-confidence segments) | 1. Ingest and Whisper (Lucas) |
| `scripts/extract_notebook.py` (cells, chart images, header, file name, execution order, name replacement) | 2. Notebook parser (Matias) |
| `.claude/skills/grade-finals/SKILL.md`, grading rules in `CLAUDE.md` | 3. Grader (Diego) |
| `scripts/build_csv.py` (range checks, total, export lock), `scripts/review.py` (review time log) | 4. Review and export (Valery) |
| `samples/` (3 fake finals, answer key), `scripts/evaluate.py` (agreement, consistency) | 5. Test data (Jorge) |

Example output from the demo run (two blind grading runs) is in `samples/example_run/`: all 18 category levels within one level of the answer key, 3 of 3 AI-usage flags right, 16 of 18 levels the same across the two runs. Known gap: names misheard by the speech model are not replaced.

## Setup (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Try it on the fake finals

Open this folder in Claude Code and say: "Grade the finals in samples/submissions." Or run the steps yourself:

```bash
.venv/bin/python scripts/transcribe.py samples/submissions
.venv/bin/python scripts/extract_notebook.py samples/submissions
# Claude grades each team into results/<team>.json (grade-finals skill)
.venv/bin/python scripts/build_csv.py
.venv/bin/python scripts/evaluate.py agreement
```

Results: `output/grades_draft.csv` and `output/review_queue.md`.

## Real finals

Put each team in its own folder under `submissions/` (one `.ipynb` and one video), then run the same steps on `submissions`. Review each team with `scripts/review.py`, then export with `scripts/build_csv.py --final`.

`submissions/`, `work/`, `results/` and `output/` never go in git.
