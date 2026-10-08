# EasyGrade: Team Plan (Updated)

Source of truth: the PRD (PRD.pdf). Everything here is ordered by **dependency only**. There are no dates, weeks, durations or time estimates. A task starts when its "Needs" are done, not before.

The email assistant (EasyReply, the existing `easy-reply` app) stays parked and untouched until grading works.

---

## 0. Decisions locked in, and where this plan departs from the PRD

### Answers given for this plan

| # | Decision | Detail |
|---|---|---|
| D-001 | Stack | Python pipeline (ingest, parser, grader, runner) plus a TypeScript/Next.js UI (review and export). Bundle files are the only link between the two. |
| D-002 | Delivery | Runs locally on the professor's laptop, like a desktop app: one launch command starts the pipeline and the UI. An installer is optional (cut list). Nothing is hosted. Whisper and the notebook parser run on the same laptop. |
| D-003 | Grades | One grade per team. The result is written to one CSV row per team member, all with the same grade. |
| D-004 | Canvas zip layout | **Assumed, not verified.** No real example exists. See the assumption below. |
| D-005 | Skills | Technical: Diego, Lucas, Matias. Valery: professor experience (flows, screens, wording, acceptance). Jorge: test data and testing. |

**Assumed Canvas zip layout (D-004):** one zip containing a notebook (`.ipynb`) and, when present, a video file per team, either in one folder per team or as flat files sharing a file-name stem. Canvas file names usually contain student names and IDs, so Ingest treats them as private (see the manifest rules). Videos submitted as Canvas media recordings or links may **not** be in the zip. Ingest must handle "video missing" as a normal case. The professor's answer replaces this assumption (task 0.2).

### Where the PRD and the brief disagree (and what this plan does)

| # | PRD says | Brief says | This plan |
|---|---|---|---|
| A | TypeScript, Next.js, Zod | Python, Pydantic | Python pipeline plus TypeScript UI (D-001). Pydantic is the source of truth for the schemas, and the TypeScript types are generated from them. |
| B | Matias builds the test set, Diego tests speech-to-text, the email dashboard is the base for the UI | Jorge owns test data, Lucas owns Ingest and Whisper, Diego owns the Grader | The brief's owners win. The Whisper quality check is Lucas's, with Jorge checking transcripts by ear. |
| C | The professor downloads and uploads finals. Canvas access is out of scope. | The input is the Canvas download zip | Compatible: the professor downloads the zip himself and drops it in. The tool never touches Canvas. |
| D | Rubric allows presentations up to 10 minutes. Videos are described as 5 minutes at most (open question 14). | 5 minutes at most | The limit is a config value (`max_video_seconds` in `config/assignment.json`), set to 5 minutes. The professor confirms in 0.2. |
| E | The Presentation criterion needs speaker labels. | Whisper only, and Whisper does not label speakers by itself. | `speaker_labels_available: false` by default. "Both partners presented" is flagged for the professor to check. |
| F | Milestones ("Week 1", "M2", "pilot batch") | No dates | Replaced by stages and gates. PRD targets are kept as gate criteria, with no dates. |
| G | Valery drafts the AI-usage flag wording | Jorge owns the wording of flags | Jorge drafts it with the professor. Valery puts it in the UI. |
| H | Three different accuracy thresholds: 80% of sections within one level ("what good looks like"), fewer than 70% of submissions means narrow to flags only, under 60% means change | Not stated | **Proposed, to confirm in the decisions log:** target is at least 80% of sections within one level. Under 80%, keep iterating the prompt. Under 70% on the hold-out set, switch to flags-only mode (cut list step 8). The 60% line is dropped because 70% triggers first. |
| I | Grader checks that scores are in range and adds up the total | Also: **verify every quote** | Added: a citation verifier. A quote that cannot be found in the transcript or notebook is never shown as verified evidence. |
| J | The professor-facing UI is built by the team | Valery owns Review and export but is not a coder | Valery owns the design, flows, wording and acceptance. She builds the UI with Claude Code, with Matias as backup. Matias writes and reviews the export guard. See risk 5 and Valery's plan. |

---

## 1. Roles

| Part | Owner | Backup | Why |
|---|---|---|---|
| 1. Ingest (unzip, match, Whisper, flags) | **Lucas** | Matias | Tech lead. File handling and local Whisper setup are the most likely to break on the professor's laptop. Lucas also runs the pipeline end to end. |
| 2. Notebook parser and checks | **Matias** | Lucas | Self-contained Python (nbformat, ast). Smaller than the other parts, so Matias also has time for the offline test suite and for backing up two parts. |
| 3. Grader (Claude call, validation, citation verifier, AI-usage flag, evals, injection tests) | **Diego** | Matias | Diego has the Claude/Anthropic work. It is the heaviest part, so Jorge writes the test inputs and Matias reviews. |
| 4. Review and export | **Valery** | Lucas | Valery owns the professor's experience. Lucas backs up the code because he knows the whole pipeline. |
| 5. Test data and professor input | **Jorge** | Valery | Jorge is the single channel to the professor and owns the fake finals and the answer key. Valery already works with the professor on screens. |

**Load balance:** Diego has the heaviest part, so injection fixtures and answer keys go to Jorge. Lucas has two parts plus the runner, so his backup duty is the lightest. Matias has the lightest part and takes the most backup and review work.

---

## 2. Interface contract

Parts talk **only** through files in one folder per team:

```
bundles/<team_id>/manifest.json         written by Ingest (part 1)
bundles/<team_id>/transcript.json       written by Ingest (part 1)
bundles/<team_id>/notebook_cells.json   written by Parser (part 2)
bundles/<team_id>/suggestion.json       written by Grader (part 3)
bundles/<team_id>/review.json           written by Review (part 4)
```

**Rules for all files**
- Each file is written by **one** part and read by the parts downstream. No part imports another part's code.
- Every file starts with `schema_version` (string, `"1"`), `team_id` (opaque, such as `team-014`, never a student name) and `produced_by` (part name plus code version).
- The schemas live in `contracts/` as Pydantic models, exported to JSON Schema. TypeScript types for the UI are generated from the JSON Schema. Unknown fields are ignored by readers.
- `bundles/` is git-ignored. Only fake examples in `fixtures/` are committed.
- `flags` everywhere use one shared registry, `contracts/flags.json`: `{code, message, severity: info|warn|block}`. Codes: `VIDEO_MISSING`, `VIDEO_UNREADABLE`, `VIDEO_TOO_LONG`, `NOTEBOOK_MISSING`, `NOTEBOOK_UNREADABLE`, `NOTEBOOK_EMPTY`, `NO_MATCH`, `NAME_NOT_FOUND`, `HEADER_RULES`, `FILENAME_RULES`, `EXEC_ORDER`, `ERROR_OUTPUT`, `LOW_CONFIDENCE_AUDIO`, `NO_SPEAKER_LABELS`, `QUOTE_UNVERIFIED`, `LOW_CONFIDENCE_SECTION`, `AI_USAGE_REVIEW`, `INJECTION_SUSPECTED`, `PARTNER_CONTRIBUTION_UNCHECKABLE`, `GRADER_FAILED`.

**Shared inputs (not per team)**

| File | Owner | Content |
|---|---|---|
| `config/rubric.json` | Valery (professor confirms) | Six categories, three levels each with point ranges, "judged from" and "limits" text, from the PRD table. Total 200. |
| `config/assignment.json` | Jorge | Assigned questions, `max_video_seconds`, header and file-name rules, `redact_names` (true/false). |
| `eval/answer_key.json` | Jorge | Expected level per section per fake team, plus which problems are seeded. Used only by evals. Never given to the model. |

### manifest.json (Ingest)

| Field | Type | Notes |
|---|---|---|
| `source_name` | string | Original name in the zip. **Local only:** it may contain student names, so it is never logged, never sent to Claude and never copied into other files. |
| `video` | `{path, status: ok\|missing\|unreadable, duration_seconds, over_limit}` | `path` relative to the bundle's working copy, null if missing |
| `notebook` | `{path, status: ok\|missing\|unreadable, size_bytes}` | "unreadable" = zero bytes, not valid JSON or not `.ipynb`. An empty notebook is the Parser's check. |
| `match` | `{method: folder\|filename_stem\|none, ambiguous: bool}` | |
| `flags` | list of flags | |
| `ingest_status` | `ok\|partial\|failed` | `partial` = a file is missing, so the rest still run |

### transcript.json (Ingest)

| Field | Type | Notes |
|---|---|---|
| `status` | `ok\|empty\|failed` | `empty` or `failed` means no section may be graded from the transcript |
| `language`, `duration_seconds` | string, number | |
| `engine` | `{name: "whisper", model_size, local: true}` | Shows that the video never left the laptop |
| `speaker_labels_available` | bool | `false` by default |
| `segments` | list of `{id, start_s, end_s, text, confidence 0-1, speaker: null}` | `id` is what evidence cites |
| `low_confidence_segment_ids` | list of ids | |
| `flags` | list of flags | |

### notebook_cells.json (Parser)

| Field | Type | Notes |
|---|---|---|
| `names` | list of `{name, cell_index}` | Names read from the header. These are the only place names are read from. |
| `header` | `{found, fields, rules_ok}` and `filename_ok` | Rules come from `config/assignment.json` |
| `cells` | list of `{index, cell_type, source, execution_count, outputs[], has_error, syntax_ok}` | `outputs[]` = `{kind: text\|table\|error\|image, text (truncated), image_ref}`. The notebook is never executed. |
| `images` | list of `{cell_index, path, mime}` | Charts saved in the notebook, extracted as files |
| `checks` | `{empty, execution_order: {strictly_increasing, skipped, out_of_order_cells}, error_cells, unexecuted_code_cells}` | "Runs top to bottom" is judged from saved outputs and cell order only |
| `flags` | list of flags | |

### suggestion.json (Grader)

| Field | Type | Notes |
|---|---|---|
| `status` | `ok\|failed\|needs_manual` | A failed grade never becomes a number |
| `model`, `prompt_version`, `rubric_version` | strings | Every eval run is tied to a prompt version |
| `names_sent_to_model` | bool | `false` when `redact_names` is on |
| `sections` | list of `{section_id, level, score, max_points, confidence: low\|medium\|high, rationale, checkable: full\|partial\|none, evidence[], flags[]}` | `evidence[]` = `{source: transcript\|notebook, ref: segment_id\|cell_index, quote, verified: bool}` |
| `total` | number | **Computed by code**, never taken from the model |
| `comments` | map `section_id` to text | Draft feedback per rubric section |
| `ai_usage` | `{status: no_concern\|review, evidence[], note}` | `review` requires at least one verified evidence item. Wording is never a verdict. |
| `validation` | `{scores_in_range, quotes_checked, quotes_verified, errors[]}` | |
| `flags` | list of flags | |

### review.json (Review)

| Field | Type | Notes |
|---|---|---|
| `students` | list of `{name, source: notebook\|professor_edit}` and `notebook_name` | One shared grade for all (D-003) |
| `sections` | list of `{section_id, suggested_level, suggested_score, final_level, final_score, edited, comment_draft, comment_final}` | |
| `total` | number | Recomputed by code from `final_score` |
| `grade_reason` | string | Built from final levels plus verified evidence |
| `ai_usage` | `{suggested, professor_agrees_useful: true\|false\|null}` | Feeds the "flag usefulness" measure |
| `flags_acknowledged` | list of flag codes | |
| `status` | `needs_review\|reviewed` | Only the professor's action sets `reviewed` |
| `opened_at`, `reviewed_at`, `reviewed_by` | timestamps, `"professor"` | Feeds the review-time measure |

**CSV export rule:** a team is exported only if `status == "reviewed"`, `total == sum(final_score)`, and every `final_score` is within its level's range. Anything else is refused with a clear reason. Each export is logged (team, count of rows, refused rows). Columns follow the PRD: `student_name, notebook_name, grade, grade_reason, flags, comments, ai_usage, status`.

---

## 3. Stages and tasks

"Runs with" lists tasks that can run in parallel inside the stage. Every task's definition of done also includes the shared definition of done in section 7.

### Stage 0: Foundations

| ID | Owner | Deliverable | Definition of done | Needs | Runs with |
|---|---|---|---|---|---|
| 0.1 | Lucas | Contracts v1: Pydantic models, JSON Schemas, flag registry, rubric and assignment config schemas, one valid and one invalid example per file | Every example validates or fails as expected. All five owners approved the PR. | none | 0.2, 0.4, 0.5 |
| 0.2 | Jorge | Professor request pack sent and answers logged: rubric text, assigned questions and dataset description, a real zip layout (or description), 3 to 5 graded examples with names removed, header and file-name rules, AI-use policy, video limit, whether MDC allows transcripts and notebooks to go to an AI service, speaker labels | Each question has an answer or "unanswered plus our assumption" in the decisions log | none | 0.1, 0.4, 0.5 |
| 0.3 | Valery | `config/rubric.json` from the PRD table, `config/assignment.json` skeleton, paper sketches of three screens (results list, evidence view, export) | Rubric totals 200 and every range matches the PRD table. Jorge cross-checked it. Sketches use the example bundles. | 0.1 | 0.4, 0.5, 0.6 |
| 0.4 | Diego | Repo scaffold (`pipeline/`, `ui/`, `contracts/`, `fixtures/`, `eval/`, `config/`), CI (schema validation, tests, real-data guard), `.gitignore` for `bundles/`, zips, videos and `.env*`, `docs/DECISIONS.md`, Claude smoke test: one fake section graded through tool use into a Pydantic model | CI runs on a PR. The guard fails on a file outside `fixtures/` that looks like a student file. The smoke test passes. | none | 0.1, 0.2, 0.5 |
| 0.5 | Matias | nbformat spike on 3 hand-made notebooks: extract names, outputs, images, execution order | Spike notes logged: what is easy, what is hard | none | 0.1, 0.2, 0.4 |
| 0.6 | Lucas | Whisper spike: install locally, transcribe one clip recorded by the team, note accuracy and speaker-label support | Notes logged: install steps, speed on a normal laptop, timestamps available, speaker labels yes/no | none (after 0.1 is submitted for review) | 0.3, 0.4, 0.5 |

**Gate 0**

| Must be true | Checked by | Final say |
|---|---|---|
| Contracts merged and approved by all five. Rubric matches the PRD table. CI green. Request pack sent. Smoke test, nbformat spike and Whisper spike recorded. Initial decisions entered. | Lucas | Lucas (technical). The professor has final say on rubric content when answered. |

### Stage 1: Build each part alone, on fake data

| ID | Owner | Deliverable | Definition of done | Needs | Runs with |
|---|---|---|---|---|---|
| 1.1 | Jorge | Batch A fixtures: 10 fake finals (notebooks written by the team), each with a hand-written transcript, plus `eval/answer_key.json`. At least 3 seeded problems: missing file, empty notebook, no name. Realistic notebooks, reviewed with Matias. | Every notebook is valid JSON, every answer-key level is inside the rubric's ranges, seeded problems are listed in the key. No real data. | 0.1, 0.2, 0.3 | 1.3, 1.6, 1.8 |
| 1.2 | Jorge | Fake clips and fake zip: video clips recorded by the team reading the hand-written scripts, including one noisy, one unreadable and one over the limit, assembled into a zip in the assumed Canvas layout (both folder and flat variants) | The zip opens, the clips play (except the unreadable one) and the layout matches D-004 | 1.1 | 1.3 to 1.9 |
| 1.3 | Lucas | Ingest: unzip, match video to notebook, validate files, write `manifest.json` with flags | Fake zip produces correct manifests, including `NO_MATCH`, `VIDEO_MISSING`, `VIDEO_UNREADABLE`, `NOTEBOOK_MISSING`. `source_name` never appears in logs or other files. | 0.1 (1.2 for the final check) | 1.1, 1.5 to 1.9 |
| 1.4 | Lucas | Whisper step: local transcription into `transcript.json` with timestamps, confidence, low-confidence ids, `speaker_labels_available: false` | Runs on the fake clips and validates against the schema. Over-limit and unreadable clips give the right flags. The video is never copied outside the laptop. | 0.1, 0.6, 1.3 | 1.5 to 1.9 |
| 1.5 | Matias | Parser: `notebook_cells.json` with names, header and file-name checks, syntax check (ast), execution order, errors, empty detection, extracted chart images. Never executes code. | All batch A notebooks produce valid output. Each seeded problem gives its flag. A test proves no cell is run. | 0.1, 0.5, 1.1 (first 3 hand-made notebooks are enough to start) | 1.3, 1.4, 1.6 to 1.9 |
| 1.6 | Diego | Grader core: prompt, tool use, Pydantic validation, per-section range check, code-computed total, `suggestion.json`. Runs on hand-written example bundles. | Output validates. An out-of-range score is rejected and sets `needs_manual`, never clamped silently. Total is always code-computed. Submission text only ever goes in as data, never in the system prompt. | 0.1, 0.3, 0.4 | 1.3 to 1.5, 1.7 to 1.9 |
| 1.7 | Diego | Citation verifier: every quote is checked against the cited transcript segment or notebook cell (exact match after whitespace normalization) | A made-up quote gets `verified: false` and a `QUOTE_UNVERIFIED` flag. A real quote verifies. A section with no verified evidence is flagged and marked `LOW_CONFIDENCE_SECTION`. | 0.1 | 1.6, 1.8, 1.9 |
| 1.8 | Valery | Review UI v1 on example bundles: results list (flagged first), rubric table with suggested level and evidence beside it, side-by-side transcript segment and notebook cell, edit level, score and comment, mark reviewed, write `review.json` | A reviewer can open a team, change a level, see the total update from code, and mark it reviewed. Reads only from bundles. Types come from the generated schema. Lucas reviewed the PR. | 0.1, 0.3 | 1.3 to 1.7 |
| 1.9 | Valery (Matias writes and reviews the guard) | CSV export that refuses `needs_review` rows and writes one row per student with the shared grade, plus an export log | Tests: a `needs_review` team is refused, a total that does not match is refused, a reviewed team exports correct rows. Zero unreviewed rows can reach the CSV. | 1.8 | 1.3 to 1.7 |

**Gate 1**

| Must be true | Checked by | Final say |
|---|---|---|
| Each part passes its own tests on fixtures alone. Schemas validate. Seeded cases pass: Ingest flags missing and unreadable files, Parser flags empty and nameless notebooks, Grader rejects out-of-range scores and unverified quotes, export refuses `needs_review`. Each owner demoed to a teammate who is not the backup. FERPA check done on every PR. | The demo partner (Ingest→Matias, Parser→Diego, Grader→Lucas, Review→Jorge, Test data→Matias) | Lucas |

### Stage 2: Connect, and measure for the first time

| ID | Owner | Deliverable | Definition of done | Needs | Runs with |
|---|---|---|---|---|---|
| 2.1 | Lucas | Runner: one command that takes a zip and runs ingest, Whisper, parser and grader per team, writing bundles, with a progress log and a summary of failed teams | Fake zip end to end. One broken team does not stop the others. A failed part writes a clear flag and status. No part imports another's code. | Gate 1 | 2.3 to 2.5, 2.8 |
| 2.2 | Jorge | Integration pass 1: run batch A through the runner, compare with the answer key, log every difference as an issue for the right owner (team id, expected, actual) | A written report: seeded problems caught vs missed, defects by owner | 2.1, 1.1, 1.2 | 2.3 to 2.5 |
| 2.3 | Diego | Eval harness v1: level agreement (suggested level within one level of the key, per section), hard-failure recall, results tied to `prompt_version` | A script that prints both numbers for a batch. Baseline for batch A recorded in the decisions log. | 1.6, 1.7, 1.1 | 2.1, 2.2, 2.4, 2.5 |
| 2.4 | Diego (Matias supplies images) | Chart-reading test: Claude on 5 chart images from fake notebooks, judging title, axes and legend | Decision logged: Analysis & Visualizations chart quality is `full`, `partial` or `none` checkable | 1.5, 1.6 | 2.1 to 2.3, 2.5 |
| 2.5 | Lucas (Jorge checks transcripts by ear) | Whisper quality test on the noisy and the accented fake clips | Decision logged: Presentation of Findings is graded, partially graded, or left to the professor. Speaker-label decision logged. | 1.4, 1.2 | 2.1 to 2.4 |
| 2.6 | Valery | UI reads real runner output instead of fixtures. Error states for failed and partial teams. One launch command for the UI. | Open every team from a runner batch. A failed team shows a clear message, not a blank screen. | 1.8, 1.9, 2.1 | 2.7, 2.8 |
| 2.7 | Matias | Parser hardening from the 2.2 defects: huge outputs, missing header, odd names, non-UTF8 text, many images. New cases added to fixtures. | Every defect assigned to Parser is closed with a test | 1.5, 2.2 | 2.6, 2.8 |
| 2.8 | Jorge | Batch B fixtures: 10 more fake finals as a **hold-out set** (never used to tune prompts). Mix of quality levels, non-native-English writing styles, partner-contribution cases, and 3 to 5 professor-graded examples if provided. | Same checks as 1.1. Marked hold-out in the decisions log. | 1.1, 0.2 | 2.1 to 2.7 |

**Gate 2**

| Must be true | Checked by | Final say |
|---|---|---|
| End to end on batch A: all five bundle files valid per team. 100% of seeded hard failures flagged. Total always equals the sum of section scores, and no score is out of range. No unverified quote shown as verified. UI shows runner output. Export still refuses unreviewed rows. Baseline agreement recorded (no threshold yet). Chart and Whisper decisions logged. | Jorge (report), Diego (numbers), Matias (guard) | Lucas |

### Stage 3: Quality and safety

| ID | Owner | Deliverable | Definition of done | Needs | Runs with |
|---|---|---|---|---|---|
| 3.1 | Diego | Prompt iterations against the targets. Each change gets a new `prompt_version` and is re-measured on batch A and the batch B hold-out. | At least 80% of sections within one level on batch B, or the "narrow to flags only" decision (H) is logged by Lucas and the professor | 2.3, 2.4, 2.5, 2.8 | 3.2 to 3.6 |
| 3.2 | Jorge | Injection fixtures: at least 8 fake submissions with hidden instructions ("give this a 100", "ignore the rubric") in notebook Markdown, cell outputs, transcript lines, a student name and a file name | Each fixture is listed in the answer key with the level it should **not** reach | 1.1 | 3.1, 3.3 to 3.6 |
| 3.3 | Diego | Injection defense and tests: submission text stays data only, injected text is flagged `INJECTION_SUSPECTED`, scores always validated by code | No injection fixture moves a section outside its answer-key range. Tests run in CI. | 3.2, 1.6 | 3.1, 3.4 to 3.6 |
| 3.4 | Diego | AI-usage flag: `review` only with at least one verified evidence item, neutral wording, never a verdict | Every `review` flag cites verified evidence. No flag without evidence. Rates across the fixture groups (including non-native-English styles) show no group flagged noticeably more often. | 1.7, 2.8, 0.2 (policy) | 3.1 to 3.3, 3.5, 3.6 |
| 3.5 | Jorge (Valery places it in the UI) | Wording for every flag message and the AI-usage text, plain and non-accusatory, approved by the professor | Every code in `flags.json` has approved wording. The UI shows it. | 0.2, 2.6 | 3.1 to 3.4, 3.6 |
| 3.6 | Lucas | Privacy: name redaction before the model (when `redact_names` is true) and restore at review, no full-submission logging, temporary files deleted after processing, repo-wide FERPA check | A test shows the model request contains no student name when redaction is on. Log scan is clean. Repo scan finds no real data. | 2.1, 1.5 | 3.1 to 3.5 |
| 3.7 | Matias | Offline regression suite: recorded model responses so CI runs the full fixture pipeline without calling Claude | CI runs batches A and B and the injection set offline, and fails if a bundle breaks its schema | 2.1, 3.1 (first prompt version) | 3.3 to 3.6 |
| 3.8 | Valery | Review polish: flagged-first order, "check this yourself" markers for criteria with limits (Collaboration, Presentation without speaker labels, chart quality when partial), play the video at a transcript timestamp | Walked through with Jorge on batch B. Every limit in the rubric table is visible on screen. | 2.6, 2.5, 3.5 | 3.1 to 3.7 |

**Gate 3**

| Must be true | Checked by | Final say |
|---|---|---|
| Agreement target met on the hold-out batch (or the narrow decision logged). Recall of seeded hard failures is 100% on A and B. All injection fixtures handled. Every `review` flag has verified evidence and the group check is recorded. Wording approved by the professor (or an assumption logged). Privacy test passes. Offline suite is green. | Matias (suite), Jorge (reports), Lucas (privacy, FERPA) | Lucas on technical items. The professor on wording and policy. The whole team plus the professor on any "narrow to flags only" decision. |

### Stage 4: Local app and professor trial

| ID | Owner | Deliverable | Definition of done | Needs | Runs with |
|---|---|---|---|---|---|
| 4.1 | Lucas | Local launch: one command starts the pipeline and the UI. Setup guide for the professor's laptop (Whisper install, API key in a local env file that is never committed). | A teammate who did not build it installs and runs it on their own laptop from the guide alone | Gate 3 | 4.2 prep |
| 4.2 | Jorge and Valery | Professor session: fake batch first, then sample finals with names removed. Record review time per submission (app timestamps), comment edit rate, flag-usefulness ticks, agreement with the professor's final levels, and issues. | Numbers and an issue list entered in the decisions log | 4.1, Gate 3 | none |
| 4.3 | Valery and Matias fix UI and parser issues. Diego re-evaluates prompts on professor-graded examples. | Each issue from 4.2 closed or consciously deferred (logged) | 4.2 | none |
| 4.4 | Whole team | Final measurement against the PRD's keep, change or stop rule | One decisions log entry with the numbers and the decision | 4.3 | none |

**Gate 4 (keep, change or stop)**

| Rule | Checked by | Final say |
|---|---|---|
| Keep: review time per submission drops by at least 50% against the professor's own baseline, agreement is at least 80%, and there are zero guardrail incidents. Change: agreement is below the target, so go back to Stage 3 with the professor's examples. Stop: any privacy incident, or any grade exported without review. | Lucas (numbers), Jorge (report) | The professor decides whether to adopt. Lucas stops the pilot on any guardrail incident. |

### Stage 5: Walk (only after Gate 4 says keep)

| ID | Owner | Deliverable |
|---|---|---|
| 5.1 | Valery | Per-student feedback letter in the professor's voice |
| 5.2 | Valery, Matias | Rubric editor |
| 5.3 | Diego | Calibration with 3 to 5 professor-graded examples used as reference |
| 5.4 | Lucas | Whole-class batches with progress, retries and clear failures |
| 5.5 | Jorge, Matias | CSV in the Canvas gradebook import format (verify with the professor) |
| 5.6 | Lucas | Installer |

---

## 4. Gates summary

| Gate | Passes when | Checks | Final say |
|---|---|---|---|
| 0 | Contracts approved, CI green, spikes and request pack done | Lucas | Lucas |
| 1 | Each part passes alone on fixtures, cross-demo done | Demo partner | Lucas |
| 2 | End-to-end batch A, seeded failures 100% flagged, guard holds, baseline recorded | Jorge, Diego, Matias | Lucas |
| 3 | Agreement target on the hold-out, injection handled, privacy test, wording approved | Matias, Jorge, Lucas | Lucas, plus the professor on wording and policy |
| 4 | Keep, change or stop rule | Lucas, Jorge | The professor adopts. Lucas can stop the pilot. |

---

## 5. Critical path

```
0.1 contracts → 1.6 grader core (also needs 0.3 rubric, 0.4 scaffold)
              → 2.1 runner (needs 1.3 ingest, 1.4 Whisper, 1.5 parser, 1.6, 1.7)
              → 2.2 integration pass 1 (needs 1.1 and 1.2 fixtures)
              → 2.3 eval baseline
              → 3.1 prompt iterations (needs 2.8 hold-out batch)
              → Gate 3 → 4.1 local launch → 4.2 professor session → Gate 4
```

**Near-critical (a delay here threatens the chain):**
- **0.2 → 0.3 → 1.1:** the rubric and test data depend on the professor's answers. If these stall, the whole of Stage 1 test data stalls.
- **2.5 Whisper quality:** if poor, the Presentation criterion changes and the demo story changes.
- **2.8 hold-out batch:** without it, 3.1 cannot honestly measure agreement.

---

## 6. Personal plans

### Lucas: Ingest owner, runner, tech lead

**Role:** You turn a Canvas zip into clean per-team bundles (files plus transcripts), run the whole pipeline from one command, and make the final technical call at every gate.

**Your tasks, in order**

| Order | Task | Deliverable | Done when |
|---|---|---|---|
| 1 | 0.1 Contracts v1 | Schemas, Pydantic models, flag registry, examples | All five owners approved the PR |
| 2 | 0.6 Whisper spike | Notes on local install, speed, timestamps, speaker labels | Notes in the decisions log |
| 3 | 1.3 Ingest | `manifest.json` per team with flags | Fake zip gives the right flags. `source_name` never leaks. |
| 4 | 1.4 Whisper step | `transcript.json` | Valid on all fake clips. Over-limit and unreadable clips flagged. |
| 5 | 2.1 Runner | One command, per-team failure isolation | Fake zip end to end, a broken team does not stop others |
| 6 | 2.5 Whisper quality decision | Decision on Presentation grading and speaker labels | Logged |
| 7 | 3.6 Privacy | Redaction test, log scan, repo scan | Tests pass |
| 8 | 4.1 Local launch | One-command start and setup guide | A teammate runs it from the guide alone |
| 9 | 4.4 Final measurement | Keep, change or stop entry | Logged |

**You need from others**
- Before 0.1: everyone's review of the contract PR.
- Before 1.3's final check: the fake zip from **Jorge (1.2)**.
- Before 2.1: the Parser (**Matias**) and the Grader plus verifier (**Diego**), each passing Gate 1.
- Before 2.5: the noisy and accented clips from **Jorge (1.2)**, who also checks transcripts by ear.

**Others wait on you**
- 0.1 unblocks everyone. This is the first task, so do it first.
- 1.3 and 1.4 unblock the Gate 1 demo and 2.1.
- 2.1 unblocks Jorge (2.2), Valery (2.6) and Diego (2.3 on real runs).

**Start immediately:** 0.1, then 0.6. **Must wait:** 1.4 (needs 1.3), 2.1 (needs Gate 1), 3.6 (needs 2.1).

**Pair or get a review**
- Matias reviews your contract PR for notebook fields.
- Diego reviews the contract's `suggestion.json`.
- Valery reviews `review.json`.

**If blocked:** post "blocked on X, doing Y meanwhile" in the team channel. If the professor's layout is the blocker, tell Jorge to ask and use the D-004 assumption meanwhile. **If you finish early:** review open PRs (you are the merger), then help Diego with eval fixtures or Valery with the UI code.

---

### Matias: Notebook parser owner, test suite, backup for Ingest, Grader and Review's export guard

**Role:** You read each notebook as data (never running it) and produce the facts about it: names, structure, execution order, errors, images. You also build the offline test suite and guard the export rule.

**Your tasks, in order**

| Order | Task | Deliverable | Done when |
|---|---|---|---|
| 1 | 0.5 nbformat spike | Notes on 3 hand-made notebooks | Logged |
| 2 | Review 0.1 | Comments on notebook fields in the contract | Approved |
| 3 | 1.5 Parser | `notebook_cells.json` | All batch A notebooks valid, each seeded problem flagged, a test proves nothing is executed |
| 4 | 1.9 Export guard (pair with Valery) | Guard function and tests | `needs_review` refused, mismatched total refused |
| 5 | 1.1 review (with Jorge) | Realistic notebooks | Approved |
| 6 | 2.4 support | Chart images for Diego's test | Delivered |
| 7 | 2.7 Parser hardening | Defects from 2.2 closed, new fixtures | Each has a test |
| 8 | 3.7 Offline regression suite | Recorded-response tests in CI | Batches A, B and injection run without calling Claude |
| 9 | 4.3 | Fix parser issues from the professor session | Closed or logged |

**You need from others**
- **Lucas (0.1):** the contract.
- **Jorge (1.1):** fake notebooks beyond your first 3.
- **Valery (1.8):** `review.json` writing, before the export guard (1.9).
- **Diego (3.1):** a first prompt version, before the offline suite (3.7).

**Others wait on you**
- 1.5 unblocks Lucas's runner (2.1) and Diego's chart test (2.4).
- 1.9 unblocks Gate 1.
- 3.7 unblocks Gate 3.

**Start immediately:** 0.5. **Must wait:** 1.9 (needs 1.8), 2.7 (needs 2.2), 3.7 (needs 2.1 and 3.1).

**Pair or get a review:** pair with Valery on 1.9. Jorge on notebook realism. You review Jorge's injection fixtures and Diego's tests for notebook-related cases.

**If blocked:** hand-write a notebook yourself and keep going. Tell Jorge you need more. **If you finish early:** you are the backup for Ingest and Grader. Offer Diego a review of the verifier, or write extra seeded cases.

---

### Diego: Grader owner, citation verifier, evals, injection defense, AI-usage flag

**Role:** You turn a transcript plus notebook facts into a suggested level, score and verified evidence per rubric section, and you prove with numbers that it is accurate and safe.

**Your tasks, in order**

| Order | Task | Deliverable | Done when |
|---|---|---|---|
| 1 | 0.4 Repo scaffold, CI, Claude smoke test | Folders, CI, decisions log, working smoke test | CI runs on a PR, smoke test passes |
| 2 | 1.6 Grader core | `suggestion.json` | Out-of-range scores rejected, total computed by code, text only ever as data |
| 3 | 1.7 Citation verifier | Verified flag on each quote | Made-up quote fails, real quote passes |
| 4 | 2.3 Eval harness | Agreement and recall numbers | Baseline for batch A logged |
| 5 | 2.4 Chart reading test | Chart decision | Logged |
| 6 | 3.2/3.3 Injection defense (with Jorge's fixtures) | Defense and CI tests | No fixture moves a section outside its range |
| 7 | 3.4 AI-usage flag | `review` with verified evidence | Group check recorded |
| 8 | 3.1 Prompt iterations | Agreement on the hold-out | At least 80% (or the narrow decision logged) |
| 9 | 4.3 | Re-evaluate on professor-graded examples | Numbers logged |

**You need from others**
- **Lucas (0.1):** the contract, before 1.6.
- **Valery (0.3):** `rubric.json`, before 1.6.
- **Jorge (1.1, 2.8, 3.2):** answer key, batch B, injection fixtures.
- **Matias (1.5):** chart images, before 2.4.
- **Lucas (2.5):** Whisper decision, before 3.1.
- **Jorge (0.2):** AI-use policy, before 3.4.

**Others wait on you**
- 0.4 unblocks everyone (repo and CI). Do it first, in parallel with Lucas's 0.1.
- 1.6 and 1.7 unblock Lucas's runner (2.1) and Gate 1.
- 2.3 unblocks 3.1.
- 3.1 unblocks Gate 3 and Matias's offline suite (3.7).

**Start immediately:** 0.4. **Must wait:** 1.6 (needs 0.1 and 0.3), 2.4 (needs 1.5), 3.3 (needs 3.2).

**Pair or get a review:** Lucas reviews the grader PR. Matias reviews the verifier. Jorge reviews the AI-usage wording. Share eval numbers with the whole team after every prompt version.

**If blocked:** write your own hand-made example bundles from the contract examples and keep going. **If you finish early:** you are the heaviest part, so first check whether Jorge needs help with fixtures. Then pick up 5.3 (calibration) only after Gate 4.

---

### Valery: Review and export owner, professor experience

**Role:** You design and build what the professor actually sees, from the results list to the CSV, so reviewing is faster than grading from scratch and every grade stays in the professor's hands.

**Your tasks, in order**

| Order | Task | Deliverable | Done when |
|---|---|---|---|
| 1 | 0.3 Rubric config and sketches | `config/rubric.json`, `config/assignment.json` skeleton, 3 paper sketches | Totals 200, Jorge cross-checked, sketches use example bundles |
| 2 | 1.8 Review UI v1 | Results list, evidence view, edits, mark reviewed, `review.json` | Open a team, change a level, see the code-computed total, mark reviewed |
| 3 | 1.9 CSV export (with Matias) | Export that refuses `needs_review` | Refusal tests pass, one row per student, shared grade |
| 4 | 2.6 Real output and error states | UI reads runner output | Every team opens, failed teams show a clear message |
| 5 | 3.5 Wording in UI (Jorge writes it) | Approved text on screen | Every flag has wording |
| 6 | 3.8 Review polish | Flagged-first, "check this yourself" markers, video at timestamp | Walked through with Jorge on batch B |
| 7 | 4.2 Professor session (with Jorge) | Timing and feedback | Entered in the decisions log |
| 8 | 4.3 | Fix top UI issues | Closed |

**You need from others**
- **Lucas (0.1):** contract and generated TypeScript types, before 1.8.
- **Jorge (0.2, 3.5):** professor answers and approved flag wording.
- **Lucas (2.1):** the runner, before 2.6.
- **Matias (1.9):** pairing on the export guard.
- **Lucas (2.5):** Whisper decision, before 3.8.

**Others wait on you**
- 0.3 unblocks Diego (1.6), Jorge (1.1) and the rest.
- 1.8 and 1.9 unblock Gate 1.
- 2.6 unblocks Jorge's later testing and the professor session.

**Start immediately:** 0.3 (sketches can start as soon as 0.1 has examples). **Must wait:** 1.8 (needs 0.1 and 0.3), 2.6 (needs 2.1), 3.8 (needs 2.5 and 3.5).

**Pair or get a review:** build with Claude Code. Lucas reviews every UI PR. Matias writes and reviews the export guard with you. Jorge tests each screen as a non-coder.

**If blocked on code:** ask Lucas (backup) or Matias early instead of struggling, and say exactly what you tried. The fallback is to keep the screens as clickable sketches while a teammate builds the data side. **If you finish early:** help Jorge with fixtures and flag wording, or draft the professor-facing guide for 4.1.

---

### Jorge: Test data and professor input, QA

**Role:** You are the team's single link to the professor and the owner of every fake final, the answer key and the test reports, so the rest of the team can prove the tool works without real student data.

**Your tasks, in order**

| Order | Task | Deliverable | Done when |
|---|---|---|---|
| 1 | 0.2 Professor request pack | Questions sent, answers logged | Every question has an answer or a logged assumption |
| 2 | 1.1 Batch A fixtures and answer key | 10 fake finals, key, 3+ seeded problems | Valid notebooks, key levels inside rubric ranges |
| 3 | 1.2 Fake clips and zip | Noisy, unreadable and over-limit clips, fake zip | Zip opens in both layouts |
| 4 | 2.2 Integration pass 1 | Report of seeded problems caught or missed | Defects assigned to owners |
| 5 | 2.8 Batch B hold-out | 10 more fakes (hold-out) | Marked hold-out in the log |
| 6 | 3.2 Injection fixtures | 8+ hidden-instruction fakes | Each has its forbidden level in the key |
| 7 | 3.5 Flag and AI-usage wording | Approved wording | Professor approved |
| 8 | 4.2 Professor session (with Valery) | Report | Entered in the decisions log |

**You need from others**
- **Lucas (0.1) and Valery (0.3):** contracts and rubric, before 1.1.
- **Lucas (2.1):** the runner, before 2.2.
- **Matias:** review of notebook realism.
- **Diego:** which seeded cases he needs.

**Others wait on you**
- 0.2 unblocks the rubric (Valery 0.3), the AI-use policy (Diego 3.4) and the Canvas zip assumption (Lucas 1.3).
- 1.1 unblocks Matias (1.5) and Diego (2.3).
- 1.2 unblocks Lucas (1.3 final check, 2.5).
- 2.8 unblocks Diego (3.1).
- 3.2 unblocks Diego (3.3).

**Start immediately:** 0.2. **Must wait:** 1.1 (needs 0.1, 0.2, 0.3), 2.2 (needs 2.1), 3.5 (needs 2.6).

**Pair or get a review:** Matias reviews notebook realism. Valery sits with you on professor questions about screens and wording. Diego tells you which test cases he needs.

**If blocked (professor does not answer):** log the assumption, send the shortest possible follow-up with one question, and carry on with the team-written fixtures. See risk 1. **If you finish early:** write more seeded problems, read other people's flag wording as a first-time user, or backup Valery on screen testing.

---

## 7. Working process

**Board columns:** To do → In progress → In review → Done. One owner per card. A card names its "Needs" and what it unblocks.

**Moving a task to Done**
1. The owner opens a pull request linked to the task ID.
2. A reviewer who is not the owner approves (see the review table).
3. Every item in the definition of done below is ticked in the PR.
4. Lucas merges.
5. The owner moves the card, and the person unblocked is told in the channel.

**Definition of done (all tasks)**
- [ ] Tests pass in CI.
- [ ] Runs on fake data only, from `fixtures/`.
- [ ] Output validates against the contract schema.
- [ ] Pull request reviewed and approved.
- [ ] FERPA check done: no real names, grades, emails, videos or screenshots anywhere in the diff, no names or full submissions in logs, no secrets.
- [ ] Decisions log updated if a choice was made.

**Who reviews what**

| Area | Primary reviewer | Second |
|---|---|---|
| Contracts | All five owners | Lucas merges |
| Ingest, runner | Matias | Diego |
| Parser | Lucas | Diego |
| Grader, evals | Lucas | Matias |
| Review UI, export | Lucas | Matias (guard) |
| Fixtures, answer key | Matias | Valery |

**Changing a bundle file format**
1. Open an issue with the proposed change, why, and which parts are affected.
2. The producing part's owner and every consuming part's owner reply approve or object.
3. A PR changes `contracts/`, bumps `schema_version`, updates every fixture and example, and keeps a backward note.
4. Lucas merges only when all affected owners approved. Nobody changes a field in their own code first.

**When blocked**
1. Post in the channel: "Blocked on X for task Y. I'm doing Z meanwhile."
2. If the blocker is a teammate, they answer or name a time-neutral next step ("after I finish 1.3").
3. If the blocker is a decision, add it to the decisions log as open and ask Lucas.
4. If nobody can unblock it, use the backup (section 1) or switch to the "finish early" list in your personal plan.

**When to ask the professor:** only about the rubric, grading intent, AI-use policy, data access rules (MDC approval), file layout, video limit, and review of wording. Only **Jorge** contacts the professor, with one batched message at a time. Technical questions never go to the professor.

**Decisions log:** `docs/DECISIONS.md`, one table. Columns: ID, decision, options considered, who decided, why, status (open/decided). Seed it with D-001 to D-005 and A to J above. Every contract change, threshold choice, and professor answer gets an entry.

**Repo rules**
- Branches: `<name>/<task-id>-<short-name>` (example: `diego/1.6-grader-core`). One task per branch.
- All work goes through pull requests into `main`. Nobody pushes to `main`. Lucas merges.
- No real student data is ever committed: no names, grades, emails, videos, zips or screenshots. Only fake files in `fixtures/`. `bundles/`, real zips, videos and `.env*` are git-ignored, and CI fails on a stray student-like file.
- Student notebooks are never executed. This is a rule in `CLAUDE.md` for the EasyGrade work (Lucas adds it).
- Secrets live only in a local env file. The professor's laptop holds their own API key.

---

## 8. Top 5 risks

| # | Risk | Early-warning sign | Fallback |
|---|---|---|---|
| 1 | Professor does not provide sample finals or graded examples | 0.2 still unanswered when Stage 1 test data is due, or only the rubric arrives | Jorge and Matias grade the fake finals themselves from the PRD rubric. Agreement numbers are labeled "team-graded" and cannot claim the target. Jorge sends a shorter ask: 3 graded examples, names removed. Gate 3 cannot pass on agreement without them, so it passes only with this caveat logged by Lucas. |
| 2 | Whisper quality is poor (accents, noise) | 2.5: transcript words the professor or Jorge cannot match to the clip, many low-confidence segments | Try a larger Whisper model on the laptop. If still poor, notebook-only mode: the Presentation criterion is left to the professor with the transcript shown for reference (cut list step 6). Never switch to a cloud speech service without the same approval as Claude. |
| 3 | Agreement below target | 3.1: below 80% on the hold-out after the prompt iterations, or big gaps in one section | Check the weak section first (chart reading, Presentation, Collaboration). Mark that section `partial` or `none` checkable. If below 70% on the hold-out, switch to flags-and-summaries only, with no suggested grade (decision H, needs the professor and the team). |
| 4 | Videos are not in the Canvas zip | The sample zip or the professor's answer shows video links or media recordings instead of files | Ingest accepts a separate videos folder with the same matching rules. The professor downloads videos separately. If that is not possible, notebook-only mode (same as risk 2). |
| 5 | Someone is blocked or overloaded (Diego has the heaviest part. Valery is building TypeScript without a coding background.) | A card stays in progress after its dependency cleared, or the same person is named in more than one blocker | Backup steps in (section 1). Jorge takes over fixtures for Diego. Matias takes the export guard code. For the UI, Lucas pairs. If the TypeScript UI cannot be finished, the fallback is a minimal Python UI over the same `review.json`, which is possible because the contract is the only link. |

---

## 9. Cut list (drop first to last, if the team falls behind)

1. All of Stage 5 (Walk).
2. Installer (keep the one-command launch).
3. Video playback at a timestamp (keep the transcript text).
4. Suggested draft comments (keep levels and evidence).
5. The AI-usage column. Drop it entirely rather than ship it without verified evidence or group-fairness checks.
6. Automatic judging of Presentation of Findings (notebook-only mode, per risk 2).
7. Chart-quality judging (mark `partial` checkable, so the professor checks charts).
8. Narrow to flags and summaries only, with no suggested grade (decision H).

**Never cut:** the professor's review of every grade, the export guard, code-computed totals and range checks, the citation verifier, "notebooks are never executed", "the video never goes to Claude", no real data in the repo, the FERPA check on every PR.

---

## 10. One-page summary for the professor

**EasyGrade: what it is**

EasyGrade is a first-draft grader for your final projects. It reads each team's notebook and the transcript of its video, suggests a level and score for every rubric section with evidence beside it, and gives you a list to review. You check, change anything you disagree with, and download a spreadsheet. It never decides a grade for you.

**What you do**
1. Download the finals from Canvas as you do today and drop the zip in the app.
2. Wait until the batch is finished.
3. Open the results list. Submissions that need your attention come first (missing file, empty notebook, low confidence, or an AI-usage "review" flag).
4. For each team, see the rubric table, the suggested level, and the quote or notebook cell that supports it. Change whatever you disagree with.
5. Mark the team reviewed.
6. Download the CSV. Only reviewed teams are included.

**What it will never do**
- Post or change anything in Canvas.
- Export a grade you have not reviewed.
- Send your students' videos anywhere. The video is turned into text on your own computer, and only the text and the notebook go to the AI.
- Run your students' code.
- Say a student used AI. At most it marks a submission "review" with evidence for you to judge.

**Your privacy and your students'**
- It runs on your laptop. Nothing is hosted.
- Student names can be kept out of what the AI sees if your college requires it.
- The team develops only with fake submissions. No real student work is stored in the project.

**What we need from you**
1. The rubric text, and the assignment questions with a description of the dataset.
2. How the Canvas zip looks (a screenshot or description with names removed is enough), including whether videos are in it.
3. Three to five graded finals with student names removed, so we can compare our suggestions with yours.
4. Your rules for file names and notebook headers.
5. The video time limit (the PRD says both 5 and 10 minutes).
6. Your course's AI-use policy.
7. Whether MDC allows transcripts and notebooks to go to an AI service, and whether they must be deleted afterward.
8. Your approval of the wording of the flags and AI-usage notes.
9. Your time for a review session using fake or name-removed finals.

**How we will know it works:** you spend much less time per final than you do now, the suggested levels are within one rubric level of yours on at least 80% of sections, every seeded problem is flagged, and no grade is ever exported without your review. If any privacy problem happens, or any grade leaves without your review, we stop.

**What you decide:** the rubric, whether to use the tool, whether the AI may see transcripts and notebooks, and every grade.
