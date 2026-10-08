# Batch B: the HOLD-OUT set

**Never tune prompts on this set.** It measures the grader on work it was not tuned on. All data is invented (students,
numbers, dataset) and no notebook was ever run. Levels are the team's own draft, not a professor's, so any agreement
number from this set is labelled "team-graded".

What differs from batch A: 5 teams with a synthetic non-native-English writing style, 2 partner-contribution cases
(one partner credited with all the work, one of them also the only speaker), and a different spread of quality.
The style is rule-based (dropped articles, verb-form and preposition slips), not based on any real student.
Grammar slips must **not** lower a level and must **not** raise an AI-usage review: that is the fairness check.

| Team | Students | Cleaning | Viz | Interp. | Code | Present. | Collab. | Style | Seeded problems |
|---|---|---|---|---|---|---|---|---|---|
| team-011 | Anika Rao, Sebastian Wolfe | E | E | E | G | E | E | native | none |
| team-012 | Thiago Almeida, Fatima Zahra | E | G | G | E | G | E | non-native | none |
| team-013 | Hiroshi Mori, Elena Marquez | G | G | G | G | G | G | non-native | none |
| team-014 | Brandon Cole, Rosa Delgado | G | E | G | G | N | N | native | one partner credited with all the work and the only speaker (`PARTNER_CONTRIBUTION_UNCHECKABLE`) |
| team-015 | Ewa Kowalski, Mateo Fuentes | G | G | N | G | G | G | non-native | none |
| team-016 | Darnell Price, Amira Nasser | E | N | N | N | G | G | native | cells run out of order (`EXEC_ORDER`) |
| team-017 | Linh Tran, Gustavo Pires | N | N | N | N | N | G | non-native | a cell stops with an error (`ERROR_OUTPUT`) |
| team-018 | Camille Roy, Kofi Asante | G | G | E | E | E | G | native | none |
| team-019 | Ivana Petrovic, Noel Fraser | G | G | G | N | G | G | non-native | cells run out of order (`EXEC_ORDER`) |
| team-020 | Ravi Menon, Julia Hartmann | E | E | G | G | G | N | native | responsibilities credit only one partner (`PARTNER_CONTRIBUTION_UNCHECKABLE`) |

E = excellent, G = good, N = needs work. Team ids continue after batch A (team-011 to team-020), so both batches can be
evaluated together. `PARTNER_CONTRIBUTION_UNCHECKABLE` is a grader flag, not a parser flag.

Regenerate: `python easygrade/fixtures/make_batch_b.py` (shares the builder in `make_batch_a.py`, needs matplotlib).
Evaluate: `python -m easygrade.eval.run_eval easygrade/fixtures/batch_b` once suggestions exist (it reads `answer_key.json` here).
