# Notebook fixtures

Only fake or anonymized data. Never execute these notebooks; parse them as data.
Names used: Alex Rivera, Sam Chen. Hand-made files and seeded files are generated with `nbformat`;
`real_anon_*` are copies of a teammate's coursework (shared with permission) with real names replaced.

| File | Demonstrates | Expected parser result |
|---|---|---|
| hand_01_basic.ipynb | Clean notebook, 2 names in first cell, one PNG chart (`display_data`), stream and `execute_result` outputs, nbformat 4.5 | No flags. 2 names, 1 image |
| hand_02_error.ipynb | One name (Sam Chen), one chart, a `NameError` error output | `ERROR_OUTPUT` (cell 3, `has_error` true) |
| hand_03_out_of_order.ipynb | execution_counts `[1,5,3,None,2]`, one never-run code cell, one chart | `EXEC_ORDER` (strictly_increasing false, skipped + out_of_order cells), unexecuted_code_cells = [4] |
| real_anon_01.ipynb | Lab, 10 chart images, large run counts with gaps (1, 28, 3, ...), no name in cells | `EXEC_ORDER`; `NAME_NOT_FOUND` (name only existed in the filename) |
| real_anon_02.ipynb | Lab, no images, executed in order with a few skipped numbers, no name in cells | Skipped counts only; `NAME_NOT_FOUND` |
| real_anon_03.ipynb | Exercise, never run (all execution_count null, no outputs), contains `!wget`/magics | unexecuted code cells (notebook never run); `syntax_ok` false on cell 3 is a magic, not a real error (see DECISIONS 0.5); `NAME_NOT_FOUND` |
| real_anon_04.ipynb | Exercise, tables (`application/vnd.google.colaboratory.intrinsic+json`), no images, counts skip numbers, shell command cell | Skipped counts; `NAME_NOT_FOUND` |
| real_anon_05.ipynb | Case-study starter, nbformat 4.5, 1 image, never run, name in a "Group Members" list (`Name 1: Alex Rivera`) | `NAME_NOT_FOUND` (the name is in a later "Group Members" cell, outside the configured header cell); unexecuted cells |
| real_anon_06.ipynb | Exercise with 8 seaborn images, Colab metadata, no name in cells | `NAME_NOT_FOUND` |
| seeded_empty.ipynb | Zero cells | `NOTEBOOK_EMPTY` |
| seeded_no_name.ipynb | Header with title and course but no name | `NAME_NOT_FOUND` |
| seeded_syntax_error.ipynb | Cell 1 has a syntax error (`def broken(:`); cell 2 is `open('pwned.txt','w').write('x')` for the no-execution test (parsing must NOT create `pwned.txt`) | `syntax_ok` false on cell 1; no `pwned.txt` after parsing |

Note: no real notebook available had an error output; use hand_02_error for `ERROR_OUTPUT`.
