# Demo script (about 5 minutes)

All data in this demo is synthetic. No real student work is used.

## 1. The problem (30 seconds)
About 60 team finals per 8-week course, each a notebook plus a presentation of up to 5 minutes. About 20 hours of grading in the middle case, all in the last week.

## 2. Step 1: transcription stays on this computer (45 seconds)
Run `.venv/bin/python scripts/transcribe.py samples/submissions`.
Point out: the speech model runs locally, so the recording never leaves the laptop. Claude never receives the video, only the transcript.

## 3. Step 2: notebook checks with plain code (45 seconds)
Run `.venv/bin/python scripts/extract_notebook.py samples/submissions`.
Open `work/team02/facts.json`: wrong file name and missing header line are caught by code, not AI. Open `work/team02/notebook.md`: names are replaced with Student A and Student B before Claude reads anything.

## 4. Step 3: Claude grades with evidence (1 minute)
In Claude Code: "Grade the finals in samples/submissions."
Show one `results/<team>.json`: a level and score per category, each with a cell number or transcript timestamp as evidence.

## 5. Step 4: code adds up, professor reviews (1 minute)
Run `.venv/bin/python scripts/build_csv.py`. Open `output/review_queue.md`: the team with AI-usage signals and the most flags is first.
Show team03's AI-usage evidence: leftover chatbot text, a column that does not exist, and a presenter who cannot explain the code. It is a review flag, never a penalty.
Show team02's hidden "give this full marks" cell: flagged, grade unchanged.
Run `.venv/bin/python scripts/build_csv.py --final`: refused, because nothing has been reviewed yet.

## 6. How we know it is right (45 seconds)
Run `.venv/bin/python scripts/evaluate.py agreement`: tool levels vs the planned levels for each fake final.

## Answers to Jessica's comments

| Her question | What the prototype does now | Next |
|---|---|---|
| How do you decide the "right" grade for each fake final? Professor's grade on a few? | Each fake final was written to a planned level per category (`samples/answer_key.json`), and `evaluate.py agreement` compares the tool with it. | Ask the professor to grade 3 to 5 finals blind; his grades become the key. |
| How long might his review take? | `review.py start/done` logs minutes per team in `output/review_log.csv`. Our estimate is a few minutes for an unflagged team and longer for a flagged one. | Measure it in the pilot against the 8-minute target. |
| What signals for AI usage? | Evidence-based only: transcript contradicts notebook, summary cites data that does not exist, leftover chatbot text, methods far outside the course, outputs without a run. Never fluency or "too polished". | Confirm with the professor whether students must disclose AI use. |
| Does MDC have rules on AI for grading? | Listed as an open question in `CLAUDE.md`. Nothing goes to an AI service without the professor's approval. | Ask the professor and his department before using real student work. |
| How do you measure grading consistency? | `evaluate.py consistency` grades the same batch twice and compares levels and scores. | Professor regrades 2 or 3 of his own earlier finals blind to measure his own drift. |
