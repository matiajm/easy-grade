"""Tests for the desktop app's Python side. No window needed.

Run with:  python -m unittest discover tests
"""
import tempfile
import unittest
import urllib.request
from pathlib import Path

from desktop.api import SAMPLE_RUBRIC, Api
from desktop.media import MediaServer
from desktop.notebook import read_notebook
from grader.cli import SAMPLES, build_demo_submissions


class DesktopApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = build_demo_submissions(Path(self.tmp.name))
        self.media = MediaServer()
        self.api = Api(self.media)

    def tearDown(self):
        self.media.close()
        self.tmp.cleanup()

    def test_full_loop(self):
        api = self.api
        # Open folder: no rubric yet, but students are listed from the folder.
        st = api.open_folder(str(self.folder))
        self.assertTrue(st["ok"], st)
        self.assertIsNone(st["rubric"])
        self.assertEqual(len(st["students"]), 10)
        self.assertTrue((self.folder / "_grading").is_dir())

        # Rubric
        st = api.use_rubric(str(SAMPLE_RUBRIC))
        self.assertTrue(st["ok"], st)
        self.assertEqual(st["rubric"]["total_points"], 100)
        self.assertTrue((self.folder / "_grading" / "rubric.json").is_file())
        names = {s["id"]: s["name"] for s in st["students"]}
        self.assertEqual(names["1002"], "Marcus Bell")  # from roster.csv in the folder
        self.assertNotIn("_grading", names)

        # Grade everyone (simulated)
        for s in st["students"]:
            self.assertTrue(api.grade_simulated(s["id"])["ok"])
        st = api.get_state()
        self.assertEqual(st["counts"]["graded"], 9)
        self.assertEqual(st["counts"]["pending"], 1)

        # Review one student
        d = api.get_student("1002")
        self.assertTrue(d["ok"], d)
        self.assertEqual(len(d["criteria"]), 7)
        self.assertGreater(len(d["notebook"]["cells"]), 5)
        self.assertTrue(d["video_url"].startswith("http://127.0.0.1:"))
        crit = d["criteria"][0]
        new = next(l[0] for l in crit["levels"] if l[0] != crit["final"])
        self.assertTrue(api.set_score("1002", crit["id"], new)["ok"])
        self.assertTrue(api.set_comment("1002", crit["id"], "checked by hand")["ok"])
        self.assertTrue(api.set_feedback("1002", "Nice work")["ok"])
        d = api.get_student("1002")
        self.assertTrue(d["criteria"][0]["changed"])
        self.assertEqual(d["criteria"][0]["comment"], "checked by hand")
        self.assertEqual(d["feedback"], "Nice work")
        self.assertTrue(api.approve("1002")["ok"])

        # Bad input comes back as a message, not a crash
        r = api.set_score("1002", crit["id"], 999)
        self.assertFalse(r["ok"])
        self.assertIn("between 0", r["error"])
        r = api.approve("1010")
        self.assertFalse(r["ok"])

        # Export
        r = api.export_all()
        self.assertTrue(r["ok"], r)
        g = self.folder / "_grading"
        for name in ("grades.xlsx", "gradebook.csv"):
            self.assertTrue((g / name).is_file(), name)
        self.assertEqual(len(list((g / "feedback").glob("*.txt"))), 9)

        # Re-opening the folder resumes where we left off
        api2 = Api(self.media)
        st = api2.open_folder(str(self.folder))
        self.assertEqual(st["rubric"]["assignment"], "Project 2 - Housing Price Regression")
        self.assertEqual(st["counts"]["approved"], 1)

    def test_errors_before_setup(self):
        self.assertFalse(self.api.scan()["ok"])
        self.assertFalse(self.api.open_folder("/definitely/not/here")["ok"])
        self.api.open_folder(str(self.folder))
        r = self.api.get_student("1001")
        self.assertFalse(r["ok"])
        self.assertIn("rubric", r["error"])


class MediaServerTests(unittest.TestCase):
    def test_range_requests(self):
        media = MediaServer()
        try:
            path = SAMPLES / "sample_walkthrough.mp4"
            url = media.url_for(path)
            size = path.stat().st_size
            req = urllib.request.Request(url, headers={"Range": "bytes=100-199"})
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 206)
                self.assertEqual(r.headers["Content-Range"], f"bytes 100-199/{size}")
                self.assertEqual(r.read(), path.read_bytes()[100:200])
            with urllib.request.urlopen(url) as r:
                self.assertEqual(len(r.read()), size)
            bad = url.rsplit("/", 1)[0] + "/not-a-token"
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(bad)
        finally:
            media.close()


class NotebookTests(unittest.TestCase):
    def test_sample_notebook(self):
        nb = read_notebook(SAMPLES / "sample_project.ipynb")
        self.assertIsNone(nb["error"])
        kinds = {o["kind"] for c in nb["cells"] for o in c["outputs"]}
        self.assertIn("image", kinds)
        self.assertIn("text", kinds)

    def test_bad_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".ipynb", delete=False) as f:
            f.write("not json")
        self.assertIsNotNone(read_notebook(f.name)["error"])


if __name__ == "__main__":
    unittest.main()
