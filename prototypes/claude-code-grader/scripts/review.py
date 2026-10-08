"""Step 5: the professor reviews a team, optionally changes scores, and marks it reviewed.

Records how long each review took (output/review_log.csv), which is the PRD's main time measure.
Keeps Claude's original suggestion next to the professor's final score, so agreement can be measured.

Usage:
  .venv/bin/python scripts/review.py start team01
  .venv/bin/python scripts/review.py done team01 --set data_cleaning=33 --set presentation=30 --ai "no concern"
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from common import ROOT, load_rubric, now, read_json, write_json

LOG = ROOT / "output" / "review_log.csv"


def level_for(cat: dict, score: int) -> str:
    for level, rng in cat["levels"].items():
        if rng["min"] <= score <= rng["max"]:
            return level
    raise SystemExit(f"{cat['name']}: {score} is outside 0-{cat['points']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the professor's review of one team.")
    parser.add_argument("action", choices=["start", "done"])
    parser.add_argument("team")
    parser.add_argument("--set", action="append", default=[], metavar="CATEGORY=SCORE")
    parser.add_argument("--ai", choices=["no concern", "review"], help="professor's decision on the AI-usage flag")
    parser.add_argument("--results", default=str(ROOT / "results"))
    args = parser.parse_args()

    path = Path(args.results) / f"{args.team}.json"
    result = read_json(path)
    if result is None:
        raise SystemExit(f"No grading file for {args.team}: {path}")

    if args.action == "start":
        result["review_started_at"] = now()
        write_json(path, result)
        print(f"Review of {args.team} started at {result['review_started_at']}")
        return

    rubric = {c["key"]: c for c in load_rubric()["categories"]}
    changed = 0
    for item in args.set:
        key, _, value = item.partition("=")
        if key not in rubric:
            raise SystemExit(f"Unknown category '{key}'. Use one of: {', '.join(rubric)}")
        score = int(value)
        entry = result["categories"][key]
        entry.setdefault("suggested_level", entry["level"])
        entry.setdefault("suggested_score", entry["score"])
        entry["score"], entry["level"] = score, level_for(rubric[key], score)
        entry["changed_by_professor"] = True
        changed += 1
    if args.ai:
        result["ai_usage"].setdefault("suggested_status", result["ai_usage"].get("status"))
        result["ai_usage"]["status"] = args.ai
        if args.ai == "no concern":
            result["ai_usage"]["signals"] = []

    result["status"] = "reviewed"
    result["reviewed_at"] = now()
    write_json(path, result)

    started = result.get("review_started_at")
    minutes = ""
    if started:
        minutes = round((datetime.fromisoformat(result["reviewed_at"]) - datetime.fromisoformat(started)).total_seconds() / 60, 1)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG.exists()
    with LOG.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["team", "started_at", "reviewed_at", "minutes", "categories_changed", "ai_decision"])
        writer.writerow([args.team, started or "", result["reviewed_at"], minutes, changed, result["ai_usage"].get("status")])
    print(f"{args.team} marked reviewed" + (f" after {minutes} min" if minutes != "" else "") + f", {changed} score(s) changed")


if __name__ == "__main__":
    main()
