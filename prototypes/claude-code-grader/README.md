# EasyGrade

A first-pass grader for CAP3321C team finals (Jupyter notebook plus recorded presentation). The recording is transcribed on this computer, Claude grades the transcript and notebook against the rubric with evidence, plain code checks the scores and builds a spreadsheet, and the professor reviews and approves every grade.

Rules and details: [CLAUDE.md](CLAUDE.md).

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
