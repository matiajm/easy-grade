"""Chart-reading test set (task 2.4): 5 chart images taken from batch A through the parser."""
import csv
import unittest
from pathlib import Path

CHARTS = Path(__file__).resolve().parents[1] / "easygrade" / "fixtures" / "charts"
CHECKS = ["has_title", "x_axis_labeled", "y_axis_labeled", "legend_ok"]
PNG = b"\x89PNG\r\n\x1a\n"


class ChartSetTests(unittest.TestCase):
    def setUp(self):
        with (CHARTS / "charts_truth.csv").open(encoding="utf-8") as f:
            self.rows = list(csv.DictReader(f))

    def test_five_real_pngs(self):
        self.assertEqual(len(self.rows), 5)
        for row in self.rows:
            data = (CHARTS / row["image"]).read_bytes()
            self.assertTrue(data.startswith(PNG), row["image"])

    def test_columns_match_chart_check(self):
        # Same columns chart_check.py writes, so `compare` reads this file as is.
        self.assertEqual(list(self.rows[0]), ["image", *CHECKS, "title_text", "notes", *(f"human_{c}" for c in CHECKS)])
        for row in self.rows:
            for c in CHECKS:
                self.assertEqual(row[c], "")  # the model's answers are filled in by `judge`
                self.assertIn(row[f"human_{c}"], ("true", "false"))

    def test_truth_follows_the_quality_ladder(self):
        by_name = {r["image"]: [r[f"human_{c}"] == "true" for c in CHECKS[:3]] for r in self.rows}
        self.assertEqual(by_name["team-001_excellent_bar.png"], [True, True, True])
        self.assertEqual(by_name["team-006_poor_bar.png"], [False, False, False])
        self.assertLess(sum(by_name["team-003_good_bar.png"]), 3)
        self.assertGreater(sum(by_name["team-003_good_bar.png"]), sum(by_name["team-006_poor_bar.png"]))


if __name__ == "__main__":
    unittest.main()
