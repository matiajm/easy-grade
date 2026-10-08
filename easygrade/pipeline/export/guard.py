"""Export guard (task 1.9): decides whether a team's review may reach the CSV.

A team is exported only if ALL of these hold (team plan, "CSV export rule"):
  1. status == "reviewed"
  2. total == sum of the final scores
  3. every final score is within the range of its final level
Anything else is refused with a plain reason. The guard never raises: a malformed review is a refusal.

It works on the review.json dict and the rubric dict, so the same rules can be ported line for line to the
TypeScript UI (ui/lib/export*). The rubric shape is the one the grader reads (rubric_example.json):
    {"sections": [{"section_id", "max_points", "levels": [{"level", "min_points", "max_points"}]}]}
"""
from __future__ import annotations

import math
from typing import Any

TOLERANCE = 1e-6  # scores may be fractional; compare totals to this, not with ==


def _is_number(value: Any) -> bool:
    """A real, finite number. bool is rejected on purpose (True would pass as 1)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def refusal_reasons(review: Any, rubric: Any) -> list[str]:
    """Every reason this review must not be exported. An empty list means it may be exported."""
    try:
        return _reasons(review, rubric)
    except Exception as exc:  # a guard that crashes is a guard that fails open
        return [f"The review could not be checked ({type(exc).__name__}), so it was not exported."]


def can_export(review: Any, rubric: Any) -> bool:
    return not refusal_reasons(review, rubric)


def _reasons(review: Any, rubric: Any) -> list[str]:
    if not isinstance(review, dict):
        return ["The review is not a valid review file."]
    reasons: list[str] = []

    if review.get("status") != "reviewed":
        reasons.append("Not marked reviewed: only a reviewed team can be exported.")

    students = review.get("students")
    if not isinstance(students, list) or not students or not all(
            isinstance(s, dict) and isinstance(s.get("name"), str) and s["name"].strip() for s in students):
        reasons.append("The team has no student names, so there is no row to write.")

    spec = {s["section_id"]: s for s in (rubric or {}).get("sections", [])} if isinstance(rubric, dict) else {}
    if not spec:
        return reasons + ["No rubric to check the scores against."]

    sections = review.get("sections")
    if not isinstance(sections, list):
        return reasons + ["The review has no section scores."]

    seen: set[str] = set()
    final_scores: list[float] = []
    for sec in sections:
        sid = sec.get("section_id") if isinstance(sec, dict) else None
        if sid not in spec:
            reasons.append(f"Section {sid!r} is not in the rubric.")
            continue
        if sid in seen:
            reasons.append(f"Section {sid} appears more than once.")
            continue
        seen.add(sid)
        score, level = sec.get("final_score"), sec.get("final_level")
        if not _is_number(score):
            reasons.append(f"{sid}: the final score is missing or not a number.")
            continue
        final_scores.append(float(score))
        rng = next((lv for lv in spec[sid]["levels"] if lv["level"] == level), None)
        if rng is None:
            reasons.append(f"{sid}: final level {level!r} is not a rubric level.")
        elif not rng["min_points"] <= score <= rng["max_points"]:
            reasons.append(f"{sid}: score {score} is outside the {level} range "
                           f"{rng['min_points']} to {rng['max_points']}.")
        if score > spec[sid]["max_points"] or score < 0:
            reasons.append(f"{sid}: score {score} is outside 0 to {spec[sid]['max_points']}.")
    for sid in sorted(spec.keys() - seen):
        reasons.append(f"{sid}: no score. Every rubric section needs a score before export.")

    total = review.get("total")
    if not _is_number(total):
        reasons.append("The total is missing or not a number.")
    elif len(final_scores) == len(spec) and abs(total - sum(final_scores)) > TOLERANCE:
        reasons.append(f"The total {total} does not match the sum of the final scores {sum(final_scores)}.")
    return reasons
