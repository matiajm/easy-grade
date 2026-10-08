"""Batch B (task 2.8): the HOLD-OUT set of 10 fake finals. Never tune prompts on it."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import nbformat

from easygrade.pipeline.notebook.config import load_config
from easygrade.pipeline.notebook.models import NotebookCells
from easygrade.pipeline.notebook.parse import parse_notebook, write_notebook_cells

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "easygrade" / "fixtures" / "batch_b"
KEY = json.loads((BATCH / "answer_key.json").read_text(encoding="utf-8"))
KEY_A = json.loads((ROOT / "easygrade" / "eval" / "answer_key.json").read_text(encoding="utf-8"))
SECTIONS = ["data_cleaning", "analysis_viz", "interpretation", "code_quality", "presentation", "collaboration"]


def relaxed():
    data = load_config().model_dump()
    data["filename_pattern"] = r"^.+\.ipynb$"
    return type(load_config()).model_validate(data)


class BatchBKeyTests(unittest.TestCase):
    def test_marked_holdout_with_ten_teams_disjoint_from_batch_a(self):
        self.assertTrue(KEY["holdout"])
        self.assertEqual(len(KEY["teams"]), 10)
        self.assertFalse(set(KEY["teams"]) & set(KEY_A["teams"]))
        names_a = {n for e in KEY_A["teams"].values() for n in e["students"]}
        names_b = {n for e in KEY["teams"].values() for n in e["students"]}
        self.assertFalse(names_a & names_b)

    def test_levels_are_valid_and_varied(self):
        seen = set()
        for team, entry in KEY["teams"].items():
            self.assertEqual(sorted(entry["planned_levels"]), sorted(SECTIONS), team)
            seen |= set(entry["planned_levels"].values())
        self.assertEqual(seen, {"excellent", "good", "needs_work"})

    def test_required_mix(self):
        groups = [e.get("group") for e in KEY["teams"].values()]
        self.assertGreaterEqual(groups.count("non_native_english"), 3)
        flags = [p["flag"] for e in KEY["teams"].values() for p in e["seeded_problems"]]
        self.assertIn("PARTNER_CONTRIBUTION_UNCHECKABLE", flags)  # a partner-contribution case
        self.assertIn("EXEC_ORDER", flags)
        self.assertIn("ERROR_OUTPUT", flags)

    def test_holdout_is_recorded_in_the_decisions_log(self):
        log = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertRegex(log, r"(?i)hold-out")


class BatchBFixtureTests(unittest.TestCase):
    def test_files_are_valid(self):
        for team in KEY["teams"]:
            with self.subTest(team):
                nbformat.validate(nbformat.read(str(BATCH / team / "final.ipynb"), as_version=4))
                t = json.loads((BATCH / team / "transcript.json").read_text(encoding="utf-8"))
                self.assertEqual((t["team_id"], t["status"]), (team, "ok"))

    def test_only_invented_people(self):
        banned = re.compile(r"valery|ortiz|matias|gonzalez|lisboa|gimenez|diego|jorge|lucas|@", re.I)
        for path in BATCH.glob("team-*/*"):
            self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), path)

    def test_non_native_style_changes_the_prose_but_not_the_facts(self):
        # Compare a non-native team's summaries with the clean wording: slips appear, numbers and code stay.
        cells = nbformat.read(str(BATCH / "team-012" / "final.ipynb"), as_version=4).cells
        prose = " ".join(c.source for c in cells if c.cell_type == "markdown")
        self.assertRegex(prose, r"We drop them|in average|did convert|are remaining|stored like")
        self.assertIn("**Students:** Thiago Almeida, Fatima Zahra", cells[0].source)  # header untouched
        self.assertTrue(any("dropna" in c.source for c in cells if c.cell_type == "code"))

    def test_partner_contribution_cases(self):
        for team in ("team-014", "team-020"):
            with self.subTest(team), tempfile.TemporaryDirectory() as d:
                a, b = KEY["teams"][team]["students"]
                res = parse_notebook(BATCH / team / "final.ipynb", team, d, relaxed())
                resp = res.header.fields["responsibilities"]
                self.assertIn(a, resp)
                self.assertNotIn(b, resp)  # only one partner is credited
        transcript = json.loads((BATCH / "team-014" / "transcript.json").read_text(encoding="utf-8"))
        text = " ".join(s["text"] for s in transcript["segments"])
        self.assertNotIn(KEY["teams"]["team-014"]["students"][1].split()[0], text)  # the other partner never speaks

    def test_generator_is_deterministic(self):
        before = {p: p.read_bytes() for p in BATCH.rglob("*") if p.is_file()}
        subprocess.run([sys.executable, str(ROOT / "easygrade" / "fixtures" / "make_batch_b.py")],
                       check=True, capture_output=True)
        self.assertEqual(before, {p: p.read_bytes() for p in BATCH.rglob("*") if p.is_file()})


class BatchBParserTests(unittest.TestCase):
    def test_parser_flags_the_seeded_problems(self):
        parser_flags = {"EXEC_ORDER", "ERROR_OUTPUT", "NOTEBOOK_EMPTY", "NAME_NOT_FOUND"}
        for team, entry in KEY["teams"].items():
            with self.subTest(team), tempfile.TemporaryDirectory() as d:
                res = parse_notebook(BATCH / team / "final.ipynb", team, d, relaxed())
                out = write_notebook_cells(res, d)
                NotebookCells.model_validate(json.loads(out.read_text(encoding="utf-8")))
                got = {f.code for f in res.flags}
                expected = {p["flag"] for p in entry["seeded_problems"]} & parser_flags
                self.assertEqual(got, expected)
                self.assertEqual([n.name for n in res.names], entry["students"])


if __name__ == "__main__":
    unittest.main()
