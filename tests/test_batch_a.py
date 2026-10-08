"""Batch A fixtures (task 1.1): 10 fake finals plus the answer key.

Checks the fixtures are valid and fake, the key fits the rubric, and the parser catches every
problem the key says was seeded. Regenerate the fixtures with easygrade/fixtures/make_batch_a.py.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

import nbformat

from easygrade.pipeline.notebook.config import load_config
from easygrade.pipeline.notebook.models import NotebookCells
from easygrade.pipeline.notebook.parse import parse_notebook, write_notebook_cells

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "easygrade" / "fixtures" / "batch_a"
KEY = json.loads((ROOT / "easygrade" / "eval" / "answer_key.json").read_text(encoding="utf-8"))

# Section ids and point maxima of the CAP3321C Final Project rubric (200 points).
SECTIONS = {"data_cleaning": 40, "analysis_viz": 50, "interpretation": 30,
            "code_quality": 25, "presentation": 35, "collaboration": 20}


def lenient_config():
    """Notebooks are named final.ipynb in the bundle, so judge them on structure, not file name."""
    data = load_config().model_dump()
    data["filename_pattern"] = r"^.+\.ipynb$"
    return type(load_config()).model_validate(data)


class BatchAKeyTests(unittest.TestCase):
    def test_ten_teams_with_a_folder_each(self):
        self.assertEqual(sorted(KEY["teams"]), [f"team-{i:03d}" for i in range(1, 11)])
        for team in KEY["teams"]:
            self.assertTrue((BATCH / team).is_dir(), team)

    def test_rubric_sections_match_and_total_200(self):
        self.assertEqual(sum(SECTIONS.values()), 200)
        for team, entry in KEY["teams"].items():
            self.assertEqual(sorted(entry["planned_levels"]), sorted(SECTIONS), team)

    def test_every_level_is_valid(self):
        for team, entry in KEY["teams"].items():
            for section, level in entry["planned_levels"].items():
                self.assertIn(level, KEY["level_keys"] + [None], f"{team} {section}")

    def test_seeded_problems_are_listed(self):
        seeded = {t: [p["flag"] for p in e["seeded_problems"]] for t, e in KEY["teams"].items()}
        self.assertGreaterEqual(sum(1 for v in seeded.values() if v), 3)
        for flag in ("NOTEBOOK_MISSING", "NOTEBOOK_EMPTY", "NAME_NOT_FOUND"):  # the three the plan requires
            self.assertTrue(any(flag in v for v in seeded.values()), flag)

    def test_quality_is_varied(self):
        levels = {lv for e in KEY["teams"].values() for lv in e["planned_levels"].values() if lv}
        self.assertEqual(levels, {"excellent", "good", "needs_work"})


class BatchAFixtureTests(unittest.TestCase):
    def test_transcripts_are_valid(self):
        for team in KEY["teams"]:
            with self.subTest(team):
                t = json.loads((BATCH / team / "transcript.json").read_text(encoding="utf-8"))
                self.assertEqual(t["team_id"], team)
                self.assertEqual(t["status"], "ok")
                self.assertTrue(t["segments"])
                ids = [s["id"] for s in t["segments"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all(s["start_s"] < s["end_s"] for s in t["segments"]))

    def test_notebooks_are_valid_and_the_missing_one_is_missing(self):
        for team, entry in KEY["teams"].items():
            path = BATCH / team / "final.ipynb"
            missing = any(p["flag"] == "NOTEBOOK_MISSING" for p in entry["seeded_problems"])
            self.assertEqual(path.exists(), not missing, team)
            if path.exists():
                nbformat.validate(nbformat.read(str(path), as_version=4))

    def test_only_invented_people_appear(self):
        # Real teammates' names must never end up in fixtures (FERPA / team rule).
        banned = re.compile(r"valery|ortiz|matias|gonzalez|lisboa|gimenez|diego|jorge|lucas(?!\s+ferreira)|@", re.I)
        for path in BATCH.glob("team-*/*"):  # the README is documentation, not fixture data
            if path.is_file():
                self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), path)

    def test_generator_is_deterministic(self):
        import subprocess
        import sys

        before = {p: p.read_bytes() for p in BATCH.rglob("*") if p.is_file()}
        key_before = (ROOT / "easygrade" / "eval" / "answer_key.json").read_bytes()
        subprocess.run([sys.executable, str(ROOT / "easygrade" / "fixtures" / "make_batch_a.py")],
                       check=True, capture_output=True)
        after = {p: p.read_bytes() for p in BATCH.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(key_before, (ROOT / "easygrade" / "eval" / "answer_key.json").read_bytes())


class BatchAParserTests(unittest.TestCase):
    """The parser must produce valid output for every notebook, and flag every seeded problem."""

    def test_parser_catches_seeded_problems_and_nothing_else(self):
        parser_flags = {"NOTEBOOK_EMPTY", "NAME_NOT_FOUND", "EXEC_ORDER", "ERROR_OUTPUT"}
        for team, entry in KEY["teams"].items():
            path = BATCH / team / "final.ipynb"
            if not path.exists():
                continue
            with self.subTest(team), tempfile.TemporaryDirectory() as d:
                res = parse_notebook(path, team, d, lenient_config())
                out = write_notebook_cells(res, d)
                NotebookCells.model_validate(json.loads(out.read_text(encoding="utf-8")))
                got = {f.code for f in res.flags}
                expected = {p["flag"] for p in entry["seeded_problems"]} & parser_flags
                self.assertTrue(expected <= got, f"missing {expected - got}")
                if team == "team-009":  # an empty notebook also has no header; that is expected
                    continue
                self.assertEqual(got - {"HEADER_RULES"} if "NAME_NOT_FOUND" in expected else got, expected,
                                 f"unexpected flags in {team}")

    def test_clean_teams_have_names_and_charts(self):
        with tempfile.TemporaryDirectory() as d:
            res = parse_notebook(BATCH / "team-001" / "final.ipynb", "team-001", d, lenient_config())
            self.assertEqual([n.name for n in res.names], KEY["teams"]["team-001"]["students"])
            self.assertEqual(len(res.images), 2)
            self.assertEqual(res.flags, [])


if __name__ == "__main__":
    unittest.main()
