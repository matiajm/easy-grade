# EasyGrade sample submissions (FAKE)

All data here is synthetic: the dataset, the restaurants and the students are fictional, so no real student records are involved (FERPA). The assignment is in `assignment/questions.md`.

Regenerate from the project root with `.venv/bin/python samples/make_samples.py` (needs macOS `say` and matplotlib). This rewrites `samples/submissions/` and `samples/answer_key.json`.

- **team01** `Rivera_Chen_FinalProject.ipynb`: strong reference. Clean, labeled charts, thoughtful summaries, one leftover cell, both partners speak evenly.
- **team02** `patel-okafor final.ipynb`: middle case. Wrong file name, header missing Responsibilities, `score` left as text, unlabeled Q3 axes, Q4 summary restates numbers, one partner barely speaks, and a hidden prompt-injection cell that must not change the grade.
- **team03** `Gomez_Brooks_FinalProject.ipynb`: weak case with AI-usage signals. NameError, out-of-order and null execution counts, Q3 and Q4 missing, an unlabeled chart, a chatbot phrase, a nonexistent column, an unexplained IsolationForest, and a single speaker who describes a left join the notebook never does.

`answer_key.json` holds the planned level per category, expected flags and AI-usage signals for each team.
