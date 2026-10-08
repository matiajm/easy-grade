"""Injection fixtures (task 3.2): each fake submission hides one instruction in a different place.

Checks the planted text really is where the key says, the key lists a level it must not reach, the
parser handles every one safely, and the generator is deterministic.
"""
import json
import tempfile
import unittest
from pathlib import Path

from easygrade.pipeline.notebook.config import load_config
from easygrade.pipeline.notebook.models import NotebookCells
from easygrade.pipeline.notebook.parse import parse_notebook, write_notebook_cells
from tests.fixture_tools import generated_into, needs_matplotlib, same_text, snapshot

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "easygrade" / "fixtures" / "injection"
KEY = json.loads((DIR / "answer_key.json").read_text(encoding="utf-8"))
LEVELS = KEY["level_keys"]


def relaxed():
    data = load_config().model_dump()
    data["filename_pattern"] = r"^.+\.ipynb$"
    return type(load_config()).model_validate(data)


class InjectionKeyTests(unittest.TestCase):
    def test_at_least_eight_fixtures_and_each_has_a_forbidden_level(self):
        self.assertGreaterEqual(len(KEY["teams"]), 8)
        for team, entry in KEY["teams"].items():
            self.assertTrue(entry["forbidden_levels"], team)
            for section, level in entry["forbidden_levels"].items():
                self.assertIn(level, LEVELS)
                # The honest level must sit below the forbidden one, or the fixture proves nothing.
                self.assertGreater(LEVELS.index(entry["planned_levels"][section]), LEVELS.index(level), f"{team} {section}")

    def test_every_place_the_plan_names_is_covered(self):
        where = " ".join(e["injection"]["where"] for e in KEY["teams"].values())
        for place in ("markdown", "output", "transcript", "name", "file name"):
            self.assertIn(place, where)


class InjectionFixtureTests(unittest.TestCase):
    def read(self, team):
        entry = KEY["teams"][team]
        folder = DIR / team
        notebook = (folder / entry["injection"]["notebook_file"]).read_text(encoding="utf-8")
        transcript = (folder / "transcript.json").read_text(encoding="utf-8")
        return entry, notebook, transcript

    def test_planted_text_is_where_the_key_says(self):
        for team in KEY["teams"]:
            with self.subTest(team):
                entry, notebook, transcript = self.read(team)
                where, text = entry["injection"]["where"], entry["injection"]["text"]
                if where == "transcript line":
                    self.assertIn(text, transcript)
                    self.assertNotIn(text, notebook)
                elif where == "file name":
                    self.assertTrue(entry["injection"]["notebook_file"].startswith(text))
                else:
                    # JSON escapes non-ASCII and "<", so compare the parsed text, not the raw bytes.
                    cells = json.loads(notebook)["cells"]
                    haystack = "\n".join("".join(c["source"]) + "".join(
                        "".join(o.get("text", [])) for o in c.get("outputs", [])) for c in cells)
                    self.assertIn(text, haystack)
                    self.assertNotIn(text, transcript)

    def test_parser_stays_safe_and_valid(self):
        for team, entry in KEY["teams"].items():
            with self.subTest(team), tempfile.TemporaryDirectory() as d:
                path = DIR / team / entry["injection"]["notebook_file"]
                res = parse_notebook(path, team, d, relaxed())
                out = write_notebook_cells(res, d)
                NotebookCells.model_validate(json.loads(out.read_text(encoding="utf-8")))
                self.assertNotIn("NOTEBOOK_UNREADABLE", [f.code for f in res.flags])
                self.assertEqual(len(res.cells) > 0, True)

    def test_the_parser_does_not_hide_or_alter_the_planted_text(self):
        # The text must reach the grader unchanged so the injection check can see it and flag it.
        for team in ("inj-01", "inj-02", "inj-03", "inj-07", "inj-08"):
            with self.subTest(team), tempfile.TemporaryDirectory() as d:
                entry = KEY["teams"][team]
                res = parse_notebook(DIR / team / entry["injection"]["notebook_file"], team, d, relaxed())
                seen = "\n".join(c.source + "\n".join(o.text or "" for o in c.outputs) for c in res.cells)
                self.assertIn(entry["injection"]["text"], seen)

    def test_a_planted_name_is_visible_in_the_names_field(self):
        with tempfile.TemporaryDirectory() as d:
            res = parse_notebook(DIR / "inj-05" / "final.ipynb", "inj-05", d, relaxed())
            self.assertIn(KEY["teams"]["inj-05"]["injection"]["text"], [n.name for n in res.names])

    @needs_matplotlib
    def test_committed_files_match_the_generator(self):
        # Regenerates into a temp folder, never over the committed files; image bytes are not compared.
        with generated_into("make_injection.py") as out:
            self.assertEqual(snapshot(out / "injection", "inj-"), snapshot(DIR, "inj-"))
            self.assertTrue(same_text(out / "injection" / "answer_key.json", DIR / "answer_key.json"))


if __name__ == "__main__":
    unittest.main()
