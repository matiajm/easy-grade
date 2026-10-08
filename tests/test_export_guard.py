"""Export guard and CSV export (task 1.9). Zero unreviewed or mismatched rows may reach the CSV."""
import copy
import csv
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from easygrade.pipeline.export.csv_export import PRD_COLUMNS, PROFESSOR_COLUMNS, export_csv, safe_cell
from easygrade.pipeline.export.guard import can_export, refusal_reasons

RUBRIC = json.loads((Path(__file__).resolve().parents[1] / "easygrade" / "fixtures" / "rubric_cap3321c.json")
                    .read_text(encoding="utf-8"))
SPEC = {s["section_id"]: s for s in RUBRIC["sections"]}


def make_review(team="team-001", names=("Isabel Moreno", "Daniel Park"), level="good", status="reviewed"):
    sections = []
    for sid, spec in SPEC.items():
        lv = next(x for x in spec["levels"] if x["level"] == level)
        score = (lv["min_points"] + lv["max_points"]) // 2
        sections.append({"section_id": sid, "suggested_level": level, "suggested_score": score, "final_level": level,
                         "final_score": score, "edited": False, "comment_draft": "d", "comment_final": f"ok {sid}"})
    return {"schema_version": "1", "team_id": team, "students": [{"name": n, "source": "notebook"} for n in names],
            "notebook_name": "final.ipynb", "sections": sections,
            "total": sum(s["final_score"] for s in sections), "grade_reason": "Good overall.",
            "ai_usage": {"suggested": "no_concern", "professor_agrees_useful": None},
            "flags_acknowledged": [], "flags": ["Cells were run out of order"], "status": status,
            "opened_at": "2026-10-08T10:00:00Z", "reviewed_at": "2026-10-08T10:05:00Z", "reviewed_by": "professor"}


def edited(**changes):
    review = make_review()
    review.update(changes)
    return review


def section(review, sid):
    return next(s for s in review["sections"] if s["section_id"] == sid)


class GuardTests(unittest.TestCase):
    def refused(self, review):
        reasons = refusal_reasons(review, RUBRIC)
        self.assertFalse(can_export(review, RUBRIC))
        self.assertTrue(reasons)
        return " ".join(reasons)

    def test_a_reviewed_team_passes(self):
        self.assertEqual(refusal_reasons(make_review(), RUBRIC), [])

    def test_every_level_passes_at_its_edges(self):
        for level in ("excellent", "good", "needs_work"):
            for edge in ("min_points", "max_points"):
                review = make_review(level=level)
                for sec in review["sections"]:
                    lv = next(x for x in SPEC[sec["section_id"]]["levels"] if x["level"] == level)
                    sec["final_score"] = lv[edge]
                review["total"] = sum(s["final_score"] for s in review["sections"])
                self.assertEqual(refusal_reasons(review, RUBRIC), [], (level, edge))

    def test_needs_review_is_refused(self):
        self.assertIn("reviewed", self.refused(make_review(status="needs_review")))

    def test_any_other_status_is_refused(self):
        for status in (None, "", "Reviewed", "approved", True, 1, ["reviewed"]):
            self.refused(edited(status=status))
        review = make_review()
        del review["status"]
        self.refused(review)

    def test_wrong_total_is_refused(self):
        review = make_review()
        review["total"] += 1
        self.assertIn("does not match", self.refused(review))

    def test_total_may_differ_by_rounding_only(self):
        review = make_review()
        review["total"] += 1e-9
        self.assertTrue(can_export(review, RUBRIC))

    def test_score_outside_its_level_is_refused(self):
        review = make_review(level="good")
        section(review, "data_cleaning")["final_score"] = 40  # excellent range, level still good
        review["total"] = sum(s["final_score"] for s in review["sections"])
        self.assertIn("outside the good range", self.refused(review))

    def test_score_above_max_or_negative_is_refused(self):
        for bad in (41, 1000, -1):
            review = make_review(level="excellent")
            section(review, "data_cleaning")["final_score"] = bad
            review["total"] = sum(s["final_score"] for s in review["sections"])
            self.refused(review)

    def test_unknown_level_is_refused(self):
        review = make_review()
        section(review, "data_cleaning")["final_level"] = "superb"
        self.assertIn("not a rubric level", self.refused(review))

    def test_missing_or_duplicate_or_unknown_sections_are_refused(self):
        review = make_review()
        review["sections"].pop()
        self.assertIn("no score", self.refused(review))
        review = make_review()
        review["sections"].append(copy.deepcopy(review["sections"][0]))
        self.assertIn("more than once", self.refused(review))
        review = make_review()
        review["sections"][0]["section_id"] = "made_up"
        self.assertIn("not in the rubric", self.refused(review))

    def test_non_numbers_are_refused(self):
        for bad in (None, "36", True, False, math.nan, math.inf, -math.inf, [], {}):
            with self.subTest(bad=bad):
                review = make_review()
                section(review, "data_cleaning")["final_score"] = bad
                self.refused(review)
        for bad in (None, "166", math.nan, math.inf, True):
            with self.subTest(total=bad):
                self.refused(edited(total=bad))

    def test_team_without_students_is_refused(self):
        for students in ([], None, [{"name": ""}], [{"name": "  "}], [{}], ["Ana"], "Ana"):
            with self.subTest(students=students):
                self.refused(edited(students=students))

    def test_malformed_input_is_a_refusal_not_a_crash(self):
        for review in (None, [], "reviewed", 7, {}, {"status": "reviewed"}, {"status": "reviewed", "sections": "x"},
                       {"status": "reviewed", "sections": [None, 3, "a"], "students": [{"name": "A"}], "total": 1}):
            with self.subTest(review=review):
                self.assertTrue(refusal_reasons(review, RUBRIC))
        for rubric in (None, {}, {"sections": []}, "rubric", {"sections": [{"nope": 1}]}):
            with self.subTest(rubric=rubric):
                self.assertTrue(refusal_reasons(make_review(), rubric))

    def test_fuzz_never_crashes_and_never_passes_a_broken_review(self):
        rng = random.Random(7)
        junk = [None, "x", -5, 10**9, math.nan, [], {}, True, "reviewed", 3.5]
        for _ in range(500):
            review = make_review()
            for _ in range(rng.randint(1, 3)):
                target = rng.choice(["status", "total", "students", "sections", "section_field"])
                if target == "section_field":
                    if isinstance(review["sections"], list) and review["sections"] and isinstance(review["sections"][0], dict):
                        sec = rng.choice(review["sections"])
                        sec[rng.choice(["section_id", "final_level", "final_score"])] = rng.choice(junk)
                else:
                    review[target] = rng.choice(junk)
            reasons = refusal_reasons(review, RUBRIC)  # must not raise
            if not reasons:  # if it passes, it must truly satisfy the three rules
                self.assertEqual(review["status"], "reviewed")
                scores = [s["final_score"] for s in review["sections"]]
                self.assertAlmostEqual(review["total"], sum(scores))
                for s in review["sections"]:
                    rng_ = next(lv for lv in SPEC[s["section_id"]]["levels"] if lv["level"] == s["final_level"])
                    self.assertTrue(rng_["min_points"] <= s["final_score"] <= rng_["max_points"])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def rows(self, path=None):
        with (path or self.dir / "grades.csv").open(encoding="utf-8", newline="") as f:
            return list(csv.reader(f))

    def test_one_row_per_student_with_the_shared_grade(self):
        review = make_review(names=("Isabel Moreno", "Daniel Park", "Tess Hale"))
        res = export_csv([("team-001", review)], RUBRIC, self.dir / "grades.csv")
        rows = self.rows()
        self.assertEqual(rows[0], PROFESSOR_COLUMNS)
        self.assertEqual([r[0] for r in rows[1:]], ["Isabel Moreno", "Daniel Park", "Tess Hale"])
        self.assertEqual({r[1] for r in rows[1:]}, {str(review["total"])})
        self.assertEqual((res.rows_written, res.exported, res.refused), (3, ["team-001"], {}))

    def test_prd_columns_are_available(self):
        export_csv([("team-001", make_review())], RUBRIC, self.dir / "grades.csv", columns="prd")
        rows = self.rows()
        self.assertEqual(rows[0], PRD_COLUMNS)
        self.assertEqual(rows[1][1], "final.ipynb")
        self.assertEqual(rows[1][-1], "reviewed")
        self.assertIn("ok data_cleaning", rows[1][5])
        with self.assertRaises(ValueError):
            export_csv([], RUBRIC, self.dir / "x.csv", columns="nope")

    def test_refused_teams_are_left_out_and_listed_with_reasons(self):
        bad_total = make_review(team="team-002", names=("Bad Total",))
        bad_total["total"] += 5
        reviews = [("team-001", make_review()),
                   ("team-002", bad_total),
                   ("team-003", make_review(team="team-003", names=("Not Reviewed",), status="needs_review"))]
        res = export_csv(reviews, RUBRIC, self.dir / "grades.csv")
        names = [r[0] for r in self.rows()[1:]]
        self.assertEqual(names, ["Isabel Moreno", "Daniel Park"])
        self.assertEqual(sorted(res.refused), ["team-002", "team-003"])
        self.assertIn("does not match", " ".join(res.refused["team-002"]))
        self.assertEqual(res.rows_written, 2)

    def test_zero_unreviewed_rows_reach_the_csv(self):
        rng = random.Random(11)
        reviews, reviewed_ok = [], set()
        for i in range(60):
            name = f"Student{i} Test"
            review = make_review(team=f"team-{i:03d}", names=(name,), level=rng.choice(["excellent", "good", "needs_work"]),
                                 status=rng.choice(["reviewed", "needs_review"]))
            if rng.random() < 0.3:
                review["total"] += rng.choice([1, -1, 0.5])
            if rng.random() < 0.2:
                section(review, "presentation")["final_score"] = 999
            if not refusal_reasons(review, RUBRIC):
                reviewed_ok.add(name)
            reviews.append((review["team_id"], review))
        export_csv(reviews, RUBRIC, self.dir / "grades.csv")
        written = {r[0] for r in self.rows()[1:]}
        self.assertEqual(written, reviewed_ok)
        statuses = {r["status"] for _, r in reviews if r["students"][0]["name"] in written}
        self.assertEqual(statuses, {"reviewed"})

    def test_export_log_lists_teams_and_counts_but_no_names(self):
        bad = make_review(team="team-002", names=("Secret Name",), status="needs_review")
        log = self.dir / "logs" / "export_log.jsonl"
        export_csv([("team-001", make_review()), ("team-002", bad)], RUBRIC, self.dir / "grades.csv", log)
        export_csv([("team-001", make_review())], RUBRIC, self.dir / "grades2.csv", log)
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)  # appended, not overwritten
        self.assertEqual((lines[0]["teams_exported"], lines[0]["rows_written"]), (["team-001"], 2))
        self.assertEqual(lines[0]["teams_refused"][0]["team_id"], "team-002")
        self.assertNotIn("Secret Name", log.read_text(encoding="utf-8"))
        self.assertNotIn("Isabel", log.read_text(encoding="utf-8"))

    def test_formula_injection_is_neutralised(self):
        review = make_review(names=("=HYPERLINK(\"http://x\",\"y\")", "+cmd|' /C calc'!A0", "@SUM(1)", "Normal Name"))
        review["flags"] = ["=1+1"]
        export_csv([("team-001", review)], RUBRIC, self.dir / "grades.csv")
        rows = self.rows()[1:]
        for row in rows:
            for cell in row:
                self.assertFalse(cell.lstrip().startswith(("=", "+", "-", "@")), cell)
        self.assertEqual(rows[3][0], "Normal Name")
        self.assertEqual(safe_cell("=1+1"), "'=1+1")
        self.assertEqual(safe_cell("Ana\nRivera"), "Ana Rivera")

    def test_commas_quotes_and_unicode_round_trip(self):
        review = make_review(names=("García, María \"Mari\"", "Zoë O'Neil"))
        export_csv([("team-001", review)], RUBRIC, self.dir / "grades.csv")
        self.assertEqual([r[0] for r in self.rows()[1:]], ["García, María \"Mari\"", "Zoë O'Neil"])

    def test_empty_input_writes_only_the_header(self):
        res = export_csv([], RUBRIC, self.dir / "grades.csv")
        self.assertEqual(self.rows(), [PROFESSOR_COLUMNS])
        self.assertEqual(res.rows_written, 0)


if __name__ == "__main__":
    unittest.main()
