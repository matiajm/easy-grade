# Decisions log

| ID | Decision | Options considered | Who decided | Why | Status |
|---|---|---|---|---|---|
| 0.5 | Read notebooks with `nbformat.read(path, as_version=4)` as data only, never execute | nbformat; raw `json` | Matias (spike) | nbformat normalizes versions and validates; raw JSON is a fallback | Proposed |

## 0.5 nbformat spike notes

Spike script: `easygrade/spike/nbformat_spike.py`. Run on 12 fixtures in `easygrade/fixtures/notebooks/` (hand-made, anonymized real, seeded). `pwned.txt` was not created: reading never executes code.

### Easy
- `nbformat.read(path, as_version=4)` worked on every file, including nbformat 4.0 and 4.5 mixed.
- `cell.cell_type`, `cell.source`, `cell.execution_count` and `cell.outputs` are uniform attribute-style access.
- Image outputs: `output.data["image/png"]` is base64; `base64.b64decode` gives a valid PNG directly (10 images extracted from one lab).
- Error outputs are `output_type == "error"` with `ename`, `evalue`, `traceback`: trivial to detect.
- Empty notebook (zero cells) loads fine, so `NOTEBOOK_EMPTY` is just `len(cells) == 0` (also decide: only blank cells?).
- Out-of-order and skipped counts are readable straight from `execution_count`.

### Hard / watch out
- `execution_count` is `None` for never-run cells (whole notebooks like exercise 6-1 and the laptops starter). Distinguish "never run" from "run out of order". Real notebooks also have gaps (1, 2, 3, 5, 8...) from re-runs; "strictly increasing" is fine but "no skipped numbers" would flag nearly everyone. Re-run cells can also push a count to 28 early in the file.
- `source` can be a string or a list of lines depending on file; after `nbformat.read` it is a string, but join defensively.
- `image/png` value may be a string with embedded newlines or a list of strings in raw files; strip/join before decoding.
- Outputs: images arrive as `display_data` (plots) but can also be in `execute_result`; check both. Tables are `text/html` plus `text/plain`; Colab data tables use `application/vnd.google.colaboratory.intrinsic+json`, which should be ignored or truncated.
- `ast.parse` for `syntax_ok` falsely fails on IPython magics and shell lines (`!wget`, `%matplotlib inline`, `?`). Need to strip `!`/`%` lines (or use `IPython.core.inputtransformer2`, extra dependency) before judging syntax.
- Names are not reliably in the first cell. In real files the name was only in the filename (4 of 6), in a "Group Members: Name 1: ..." list, or absent; a naive regex produced junk such as "writing code in the provided cells". Name extraction needs the `assignment.json` header rules and probably a field-label list, not free regex.
- nbformat version quirks: 4.0 notebooks have no cell `id`; 4.5 has them. `nbformat.write` adds ids/normalizes, and files are re-indented, so anonymized copies are larger than originals (size is not a fidelity signal).
- Colab metadata: `metadata.colab.provenance` (source GitHub URL, timestamp) and `authorship_tag` (stripped from fixtures) can be identifying. Do not log them.
- Widgets: none observed in this sample, but `application/vnd.jupyter.widget-view+json` outputs and `metadata.widgets` can appear and fail `nbformat.validate` in older versions; handle read errors per file (`NotJSONError`, `ValidationError`) and flag instead of crashing.
- No real sample had an error output, so error handling was verified only on the hand-made fixture.
- Windows: reading from OneDrive-synced paths worked; file names contain spaces and "Copy of" prefixes, so filename-name checks need normalization.
- Anonymization trap: Colab stores `metadata.executionInfo.user` (`displayName`, `userId`, `photoUrl`) on many cells. A plain name replacement left the real Google `userId`; it had to be blanked separately. Any "never log identifying data" rule must cover cell metadata, not just sources and outputs.
