# Batch A: 10 fake finals

All invented: students, numbers and the dataset (Miami-Dade restaurant inspections, 2025). Nothing is real, and
no notebook was ever run: outputs are typed in, the way a saved notebook looks after a run.

Each team folder has `final.ipynb` and `transcript.json` (team-008 has only the transcript: it never submitted a
notebook). The expected grades are in `../../eval/answer_key.json`. E = excellent, G = good, N = needs work, - = no grade expected.

| Team | Students | Cleaning | Viz | Interp. | Code | Present. | Collab. | Seeded problems |
|---|---|---|---|---|---|---|---|---|
| team-001 | Isabel Moreno, Daniel Park | E | E | E | E | E | E | none |
| team-002 | Camila Reyes, Omar Haddad | E | E | G | E | G | E | none |
| team-003 | Nadia Petrov, Elijah Brooks | G | G | G | G | G | G | none |
| team-004 | Tomas Ibarra, Grace Okoye | G | G | G | N | G | G | cells run out of order (`EXEC_ORDER`) |
| team-005 | Layla Haddad, Victor Salazar | E | G | N | G | G | G | none |
| team-006 | Marco Bianchi, Sofia Duarte | N | N | N | N | G | G | a cell stops with an error (`ERROR_OUTPUT`); cells run out of order (`EXEC_ORDER`) |
| team-007 | Hannah Weiss, Kwame Mensah | G | E | G | G | N | G | none |
| team-008 | Rafael Costa, Mei Tanaka | - | - | - | - | G | - | no notebook submitted (`NOTEBOOK_MISSING`) |
| team-009 | Aaliyah Grant, Leandro Ferreira | N | N | N | N | G | N | empty notebook (`NOTEBOOK_EMPTY`) |
| team-010 | Priscilla Ng, Jonas Lindqvist | G | G | E | G | G | N | no student names in the header (`NAME_NOT_FOUND`) |

The rubric is the 200-point CAP3321C Final Project rubric: cleaning 40, analysis and visualizations 50,
interpretation 30, code quality 25, presentation 35, collaboration 20. The levels in the key are a draft:
Valery's `config/rubric.json` (task 0.3) and Jorge's review replace them when they are ready.

**Regenerate:** `python easygrade/fixtures/make_batch_a.py` (needs matplotlib). The output is deterministic, and
`tests/test_batch_a.py` fails if the committed files drift from the generator.

**File names:** notebooks are called `final.ipynb`, as the plan says, so the parser's CAP3321C file-name rule
(`Lastname1_Lastname2_FinalProject.ipynb`) does not apply to them. Tests use a relaxed file-name pattern.
