"""End-to-end test of the dashboard: the real page (ui/index.html) in a headless browser, talking to the real Python
backend through the dev server. Only fake data, no network, and settings are isolated in a temp folder, so
no API key can be found and nothing is ever sent to an AI service.

Needs playwright and Microsoft Edge or Chrome (playwright's own browsers are not needed); skipped otherwise.
Set EASYGRADE_UI_SHOTS=<folder> to also save a screenshot of every screen.
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

SHOTS = os.environ.get("EASYGRADE_UI_SHOTS")


def _launch(p):
    for channel in ("msedge", "chrome"):
        try:
            return p.chromium.launch(channel=channel, headless=True)
        except Exception:
            continue
    return None


@unittest.skipUnless(sync_playwright, "playwright is not installed")
class DashboardE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._old_cfg = os.environ.get("EASYGRADE_CONFIG_DIR")
        cls._old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["EASYGRADE_CONFIG_DIR"] = str(Path(cls.tmp.name) / "config")  # no saved key, ever
        from desktop.devserver import serve

        cls.server, cls.api, cls.media = serve(0, Path(cls.tmp.name) / "sample")
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = _launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        if cls.browser:
            cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.media.close()
        if cls._old_cfg is None:
            os.environ.pop("EASYGRADE_CONFIG_DIR", None)
        else:
            os.environ["EASYGRADE_CONFIG_DIR"] = cls._old_cfg
        if cls._old_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = cls._old_key
        cls.tmp.cleanup()

    def setUp(self):
        if not self.browser:
            self.skipTest("no Edge or Chrome found")
        self.page = self.browser.new_page(viewport={"width": 1100, "height": 900})
        self.problems = []
        self.page.on("pageerror", lambda e: self.problems.append(str(e)))
        self.page.on("console", lambda m: self.problems.append(m.text) if m.type == "error" and "404" not in m.text else None)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.problems, [], "the page logged errors")

    def shot(self, name):
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(SHOTS) / f"{name}.png"), full_page=True)

    def test_whole_flow(self):
        pg = self.page
        pg.goto(f"http://127.0.0.1:{self.port}/")

        # ---- start: rubric dropdown with a preview, no AI key, the privacy line says so
        pg.wait_for_selector("text=Grade a new batch")
        self.assertIn("CAP3321C Final Project", pg.inner_text("#rubric option:checked"))
        self.assertIn("Excellent 36–40", pg.inner_text(".preview"))
        self.assertIn("Runs locally", pg.inner_text(".topbar"))
        self.assertTrue(pg.is_disabled("button:has-text('Continue')"))
        self.shot("1_start")

        # ---- replace rubric panel: choose a file, see what was read, cancel
        pg.click("text=Replace rubric")
        self.assertIn("Upload the new rubric", pg.inner_text("#rubric-panel"))
        self.assertTrue(pg.is_disabled("button:has-text('Use this rubric')"))
        rubric_file = Path(__file__).resolve().parents[1] / "rubrics" / "project2_regression.json"
        self.api.dialogs["open"] = [str(rubric_file)]
        pg.click("text=Choose file…")
        pg.wait_for_selector("text=Read 7 categories")
        self.assertIn("100", pg.inner_text(".rubric-panel .preview"))
        self.shot("2_replace_rubric")
        pg.click("#rubric-panel >> text=Cancel")
        self.assertEqual(pg.locator("#rubric-panel").count(), 0)

        # ---- sample folder
        pg.click("text=Use the sample folder")
        pg.wait_for_selector("text=for 10 teams")
        self.assertIn("1 file doesn't name a student", pg.inner_text("#folder-preview"))
        self.shot("3_start_folder")
        pg.click("button:has-text('Continue')")

        # ---- matches: 3 teams need a video, one has no notebook
        pg.wait_for_selector("text=Check the matches")
        self.assertIn("3 need you", pg.inner_text(".match-summary"))
        self.assertTrue(pg.is_disabled("button:has-text('Start grading')"))
        self.assertIn("No notebook", pg.inner_text(".match-list"))
        self.shot("4_match")
        # assign the loose video to the first team that needs one, say there is none for the others
        needs = pg.locator(".m-row.needs select")
        pick_id = needs.nth(0).get_attribute("data-pick")
        needs.nth(0).select_option(index=1)  # the loose IMG_4821.MOV
        pg.wait_for_selector(".m-status:has-text('Matched by you')")
        self.assertIn("2 need you", pg.inner_text(".match-summary"))
        while pg.locator(".m-row.needs select").count():
            pg.locator(".m-row.needs select").first.select_option("none")
            pg.wait_for_timeout(150)
        self.assertIn("All set", pg.inner_text(".match-summary"))
        self.assertFalse(pg.is_disabled("button:has-text('Start grading')"))
        # undo the hand match and redo it
        pg.locator(f"#pick-{pick_id}").select_option(index=0)
        pg.wait_for_selector(".m-status:has-text('Needs you')")
        pg.locator(f"#pick-{pick_id}").select_option(index=1)
        pg.wait_for_selector(".m-status:has-text('Matched by you')")

        # ---- grading: the AI choice is disabled without a key; use made-up scores
        self.assertTrue(pg.is_disabled("input[value=ai]"))
        pg.check("input[value=sim]")
        pg.click("button:has-text('Start grading')")
        pg.wait_for_selector("text=ready for your review", timeout=60000)
        self.assertIn("Skipped", pg.inner_text(".steps-run"))  # transcription is not connected
        self.shot("5_progress")
        pg.click("button:has-text('Review the grades')")

        # ---- review list
        pg.wait_for_selector(".team")
        self.assertEqual(pg.locator(".team").count(), 10)
        self.assertIn("0 of 10 teams reviewed", pg.inner_text(".head .sub"))
        self.assertTrue(pg.is_disabled("button:has-text('Download Excel')"))
        self.shot("6_review")
        first = pg.locator(".team").first
        self.assertEqual(first.locator(".details").count(), 1)  # the first team that needs attention is open
        self.assertIn("How the grade adds up", first.inner_text())
        self.assertIn("Strongest", first.inner_text())

        # a team with a notebook, a video and every score: mark it reviewed after changing one score
        name = "Isabel Moreno & Daniel Park"
        done = pg.locator(".team", has_text=name)
        self.assertEqual(done.locator("button.review-btn").inner_text().strip(), "Mark reviewed")
        if done.locator(".details").count() == 0:
            done.locator(".open-btn").click()
        # change one score by hand
        done.locator("text=Change a score").click()
        field = pg.locator(".details input[data-score]").first
        field.fill("33")
        field.dispatch_event("change")
        pg.wait_for_selector("text=changed from")
        pg.locator(".details >> text=Done changing").first.click()
        pg.locator(f".team:has-text('{name}') button.review-btn").click()
        pg.wait_for_selector(f".team:has-text('{name}') button.review-btn.done")
        self.assertIn("1 of 10 teams reviewed", pg.inner_text(".head .sub"))
        self.assertFalse(pg.is_disabled("button:has-text('Download Excel')"))

        # a team with a missing score cannot be marked reviewed: the button asks for the score instead
        gap = pg.locator("button.review-btn:has-text('Add missing score')")
        self.assertGreater(gap.count(), 0)
        gap.first.click()
        self.assertGreater(pg.locator(".details input:focus").count(), 0)

        # ---- evidence drawer: open the notebook from a chip, then the video tab
        pg.locator(f".team:has-text('{name}') .open-btn").click()
        pg.locator(f".team:has-text('{name}') button.ev").first.click()
        pg.wait_for_selector(".drawer")
        self.assertGreater(pg.locator(".drawer .cell").count(), 5)
        self.assertGreater(pg.locator(".drawer .cell.hl").count(), 0)
        self.shot("7_evidence")
        pg.click(".drawer >> text=Video")
        self.assertEqual(pg.locator(".drawer video").count(), 1)
        pg.click(".drawer-top >> text=Close")
        self.assertEqual(pg.locator(".drawer").count(), 0)

        # ---- exports go through the guard: only the reviewed team is written
        pg.click("button:has-text('Download Excel')")
        pg.wait_for_selector("text=Excel saved")
        self.assertIn("Grades, Details and Rubric", pg.inner_text(".export-note"))
        pg.click("button:has-text('Download CSV')")
        pg.wait_for_selector("text=CSV saved")
        self.shot("8_exported")
        out = Path(self.api._folder) / "_grading"
        self.assertTrue((out / "grades_review.xlsx").is_file())
        csv_lines = (out / "grades.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(csv_lines[0], "Student name,Score (out of 200),Needs your attention,AI usage")
        self.assertEqual(len(csv_lines) - 1, 2)  # one team of two students
        self.assertTrue((out / "export_log.jsonl").is_file())

        # ---- settings window and the new-batch link
        pg.click("button:has-text('Settings')")
        self.assertIn("API key", pg.inner_text(".modal"))
        self.assertTrue(pg.is_disabled("button:has-text('Test connection')"))
        self.shot("9_settings")
        pg.click(".modal >> text=Close")
        pg.click("text=Start a new batch")
        pg.wait_for_selector("text=Grade a new batch")
        self.assertIn("already graded", pg.inner_text("#folder-preview"))


if __name__ == "__main__":
    unittest.main()
