"""Parser tests. Run with:  python -m unittest discover tests

The parser must never execute notebook code; test_no_code_is_executed proves it.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import nbformat

from easygrade.pipeline.notebook.config import load_config
from easygrade.pipeline.notebook.models import Cell, NotebookCells
from easygrade.pipeline.notebook.checks import execution_order, is_empty
from easygrade.pipeline.notebook.names import extract_names
from easygrade.pipeline.notebook.parse import parse_notebook, syntax_ok, write_notebook_cells

FIXTURES = Path(__file__).resolve().parents[1] / "easygrade" / "fixtures" / "notebooks"


def codes(result):
    return [f.code for f in result.flags]


def cell(i, count, src="x = 1", kind="code"):
    return Cell(index=i, cell_type=kind, source=src, execution_count=count)


class FixtureTests(unittest.TestCase):
    def parse(self, name):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return parse_notebook(FIXTURES / name, "team-001", self.tmp.name)

    def test_every_fixture_gives_valid_output(self):
        for path in sorted(FIXTURES.glob("*.ipynb")):
            with self.subTest(path.name), tempfile.TemporaryDirectory() as d:
                res = parse_notebook(path, "team-001", d)
                out = write_notebook_cells(res, d)
                NotebookCells.model_validate(json.loads(out.read_text(encoding="utf-8")))
                for img in res.images:
                    self.assertTrue((Path(d) / img.path).is_file())

    def test_clean_notebook_has_no_flags(self):
        r = self.parse("hand_01_basic.ipynb")
        self.assertEqual(codes(r), [])
        self.assertEqual([n.name for n in r.names], ["Alex Rivera", "Sam Chen"])
        self.assertEqual(len(r.images), 1)
        self.assertTrue(r.filename_ok)

    def test_error_output_flagged(self):
        r = self.parse("hand_02_error.ipynb")
        self.assertIn("ERROR_OUTPUT", codes(r))
        self.assertEqual(r.checks.error_cells, [3])
        self.assertTrue(r.cells[3].has_error)

    def test_out_of_order_flagged(self):
        r = self.parse("hand_03_out_of_order.ipynb")
        eo = r.checks.execution_order
        self.assertIn("EXEC_ORDER", codes(r))
        self.assertFalse(eo.strictly_increasing)
        self.assertEqual(eo.out_of_order_cells, [3, 5])
        self.assertTrue(eo.skipped)
        self.assertEqual(r.checks.unexecuted_code_cells, [4])

    def test_empty_notebook_flagged(self):
        r = self.parse("seeded_empty.ipynb")
        self.assertTrue(r.checks.empty)
        self.assertIn("NOTEBOOK_EMPTY", codes(r))

    def test_nameless_notebook_flagged(self):
        r = self.parse("seeded_no_name.ipynb")
        self.assertEqual(r.names, [])
        self.assertIn("NAME_NOT_FOUND", codes(r))
        self.assertEqual(r.header.fields.get("course"), "CAP0000")

    def test_syntax_error_detected_but_magics_are_not(self):
        r = self.parse("seeded_syntax_error.ipynb")
        self.assertFalse(r.cells[1].syntax_ok)
        r3 = self.parse("real_anon_03.ipynb")  # contains !wget and % magics
        self.assertFalse([c.index for c in r3.cells if c.syntax_ok is False])

    def test_never_run_notebook_is_unexecuted_not_out_of_order(self):
        r = self.parse("real_anon_03.ipynb")
        self.assertTrue(r.checks.unexecuted_code_cells)
        self.assertNotIn("EXEC_ORDER", codes(r))

    def test_rerun_gaps_are_not_flagged(self):
        r = self.parse("real_anon_02.ipynb")  # counts 1..9, 11..31
        self.assertNotIn("EXEC_ORDER", codes(r))

    def test_one_bad_cell_is_pinpointed(self):
        r = self.parse("real_anon_01.ipynb")  # counts 1, 28, 3, 4, ...
        self.assertEqual(r.checks.execution_order.out_of_order_cells, [3])

    def test_image_extraction_counts(self):
        self.assertEqual(len(self.parse("real_anon_01.ipynb").images), 10)

    def test_metadata_not_copied(self):
        r = self.parse("real_anon_06.ipynb")
        blob = r.model_dump_json()
        for key in ("colab", "executionInfo", "userId", "photoUrl"):
            self.assertNotIn(key, blob)


class SafetyTests(unittest.TestCase):
    def test_no_code_is_executed(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "pwned.txt"
            nb = nbformat.v4.new_notebook()
            nb.cells = [
                nbformat.v4.new_markdown_cell("Name: Alex Rivera"),
                nbformat.v4.new_code_cell(f"open({str(marker)!r}, 'w').write('x')"),
                nbformat.v4.new_code_cell(f"import os; os.makedirs({str(marker)!r} + '_dir')"),
            ]
            path = Path(d) / "evil.ipynb"
            nbformat.write(nb, str(path))
            cwd = os.getcwd()
            os.chdir(d)  # also catches relative-path writes such as open('pwned.txt','w')
            try:
                nb.cells[1].source = "open('pwned.txt','w').write('x')"
                nbformat.write(nb, str(path))
                res = parse_notebook(path, "team-009", Path(d) / "out")
            finally:
                os.chdir(cwd)
            self.assertFalse(marker.exists())
            self.assertFalse((Path(d) / "pwned.txt").exists())
            self.assertFalse(Path(str(marker) + "_dir").exists())
            self.assertEqual(len(res.cells), 3)
            self.assertTrue(all(c.execution_count is None for c in res.cells))

    def test_unreadable_files_are_flagged_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "broken.ipynb"
            bad.write_text("{ not json", encoding="utf-8")
            self.assertEqual(codes(parse_notebook(bad, "team-1", d)), ["NOTEBOOK_UNREADABLE"])
            self.assertEqual(codes(parse_notebook(Path(d) / "missing.ipynb", "team-1", d)),
                             ["NOTEBOOK_UNREADABLE"])

    def test_team_id_must_be_opaque(self):
        with self.assertRaises(ValueError):
            parse_notebook(FIXTURES / "hand_01_basic.ipynb", "Alex Rivera", ".")


class UnitTests(unittest.TestCase):
    def test_execution_order_cases(self):
        eo = execution_order([cell(0, 1), cell(1, 2), cell(2, 4)])
        self.assertTrue(eo.strictly_increasing)
        self.assertFalse(eo.skipped)
        eo = execution_order([cell(0, 2), cell(1, 2)])  # equal count = not strictly increasing
        self.assertEqual(eo.out_of_order_cells, [1])
        eo = execution_order([cell(0, None), cell(1, None)])  # never run
        self.assertFalse(eo.skipped)
        eo = execution_order([cell(0, 1), cell(1, None), cell(2, 2)])
        self.assertTrue(eo.skipped)
        eo = execution_order([cell(0, 1), cell(1, 2), cell(2, None)])  # trailing unrun cell
        self.assertFalse(eo.skipped)

    def test_empty_detection(self):
        self.assertTrue(is_empty([]))
        self.assertTrue(is_empty([cell(0, None, "  \n", "code"), cell(1, None, "", "markdown")]))
        self.assertFalse(is_empty([cell(0, None, "# Title", "markdown")]))

    def test_name_formats(self):
        cfg = load_config()
        cases = {
            "**Team members:** Alex Rivera, Sam Chen": ["Alex Rivera", "Sam Chen"],
            "Student: Alex Rivera and Sam Chen": ["Alex Rivera", "Sam Chen"],
            "# Project\nBy Alex Rivera & Sam Chen": ["Alex Rivera", "Sam Chen"],
            "Name - Alex Rivera": ["Alex Rivera"],
            "- Students: Alex Rivera; Sam Chen": ["Alex Rivera", "Sam Chen"],
            "Welcome to the project. Write code in the cells.": [],
            "Name: writing code in the provided cells. Do not edit.": [],
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertEqual([n.name for n in extract_names(text, 0, cfg)], expected)

    def test_syntax_ok(self):
        self.assertTrue(syntax_ok("x = 1"))
        self.assertTrue(syntax_ok("!pip install foo\n%matplotlib inline\nx = 1"))
        self.assertTrue(syntax_ok("for i in range(3):\n    !echo $i\n    print(i)"))
        self.assertFalse(syntax_ok("def f(:"))
        self.assertIsNone(syntax_ok("%%bash\nls -l"))
        self.assertIsNone(syntax_ok("   "))

    def test_header_rules_and_filename_flags(self):
        data = load_config().model_dump()
        data["header_rules"]["required_fields"] = ["names", "course", "date"]
        cfg = type(load_config()).model_validate(data)
        with tempfile.TemporaryDirectory() as d:
            res = parse_notebook(FIXTURES / "hand_01_basic.ipynb", "team-1", d, cfg)
            self.assertIn("HEADER_RULES", codes(res))
            self.assertFalse(res.header.rules_ok)
            self.assertNotIn("date", res.header.fields)
            nb = Path(d) / "bad name!!.ipynb"
            nb.write_bytes((FIXTURES / "hand_01_basic.ipynb").read_bytes())
            res = parse_notebook(nb, "team-1", d)
            self.assertFalse(res.filename_ok)
            self.assertIn("FILENAME_RULES", codes(res))


if __name__ == "__main__":
    unittest.main()
