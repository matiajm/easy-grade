"""Step 4: check Claude's grading files and build the spreadsheet.

Claude proposes a level, a score and evidence for each category in results/<team>.json.
This script (plain code, not AI) checks every score is inside its level's point range,
adds up the total out of 200, merges in the rule-check flags, and writes one row per student.

Usage:
  .venv/bin/python scripts/build_csv.py            # draft spreadsheet + review queue
  .venv/bin/python scripts/build_csv.py --final    # final spreadsheet, refused while any team still needs review
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from common import LEVEL_NAMES, ROOT, load_rubric, read_json

COLUMNS = ["student_name", "notebook_name", "grade", "grade_reason", "flags", "comments", "ai_usage", "status"]


def validate(result: dict, rubric: dict) -> list[str]:
    """Return a list of problems. An empty list means the grading file is usable."""
    problems = []
    cats = result.get("categories", {})
    for cat in rubric["categories"]:
        entry = cats.get(cat["key"])
        if not isinstance(entry, dict):
            problems.append(f"{cat['name']}: missing")
            continue
        level = entry.get("level")
        score = entry.get("score")
        if level not in cat["levels"]:
            problems.append(f"{cat['name']}: unknown level '{level}'")
            continue
        if not isinstance(score, int) or isinstance(score, bool):
            problems.append(f"{cat['name']}: score must be a whole number")
            continue
        lo, hi = cat["levels"][level]["min"], cat["levels"][level]["max"]
        if not lo <= score <= hi:
            problems.append(f"{cat['name']}: score {score} is outside the {LEVEL_NAMES[level]} range {lo}-{hi}")
        if not entry.get("evidence"):
            problems.append(f"{cat['name']}: no evidence given")
    ai = result.get("ai_usage", {})
    if ai.get("status") not in ("no concern", "review"):
        problems.append("ai_usage.status must be 'no concern' or 'review'")
    elif ai.get("status") == "review" and not all(s.get("evidence") for s in ai.get("signals", [])):
        problems.append("ai_usage is 'review' but a signal has no evidence")
    elif ai.get("status") == "review" and not ai.get("signals"):
        problems.append("ai_usage is 'review' but lists no signals")
    return problems


def summarize(team: str, result: dict | None, facts: dict, names: dict, rubric: dict) -> dict:
    flags = list(facts.get("rule_flags", []))
    if result is None:
        return {"team": team, "total": None, "flags": flags + ["Not graded yet: no results file"],
                "reason": "", "comments": "", "ai": "not checked", "status": "needs review", "names": names, "cats": {}}

    problems = validate(result, rubric)
    flags += [f"Grading file problem: {p}" for p in problems]
    flags += result.get("flags", [])

    cats = result.get("categories", {})
    total = None if problems else sum(cats[c["key"]]["score"] for c in rubric["categories"])
    reasons, comments = [], []
    for cat in rubric["categories"]:
        entry = cats.get(cat["key"])
        if not isinstance(entry, dict):
            continue
        if entry.get("confidence") == "low":
            flags.append(f"Low confidence on {cat['name']}")
        evidence = " | ".join(entry.get("evidence", [])[:3])
        reasons.append(f"{cat['name']}: {LEVEL_NAMES.get(entry.get('level'), entry.get('level'))} "
                       f"{entry.get('score')}/{cat['points']}. {entry.get('reason', '')} [Evidence: {evidence}]")
        if entry.get("comment"):
            comments.append(f"{cat['name']}: {entry['comment']}")

    ai = result.get("ai_usage", {})
    if ai.get("status") == "review":
        signals = ai.get("signals", [])
        if len(signals) < 2:
            flags.append("AI-usage review rests on a single signal: check it carefully")
        ai_text = "review: " + "; ".join(f"{s.get('signal')} ({s.get('evidence')})" for s in signals)
    else:
        ai_text = ai.get("status", "not checked")

    return {"team": team, "total": total, "flags": flags, "reason": "\n".join(reasons),
            "comments": "\n".join(comments), "ai": ai_text, "status": result.get("status", "needs review"),
            "names": names, "cats": cats}


def write_queue(rows: list[dict], rubric: dict, path: Path) -> None:
    """Teams that need the professor's attention first: AI-usage review, then most flags."""
    order = sorted(rows, key=lambda r: (r["status"] == "reviewed", not r["ai"].startswith("review"), -len(r["flags"])))
    lines = ["# Review queue", "", "Teams that need your attention come first. Nothing is final until you mark it reviewed.", ""]
    for r in order:
        total = f"{r['total']}/200" if r["total"] is not None else "not computed"
        lines.append(f"## {r['team']}: {total} ({r['status']})")
        for cat in rubric["categories"]:
            e = r["cats"].get(cat["key"])
            if isinstance(e, dict):
                lines.append(f"- {cat['name']}: {LEVEL_NAMES.get(e.get('level'), e.get('level'))} {e.get('score')}/{cat['points']}"
                             + (" (low confidence)" if e.get("confidence") == "low" else ""))
        lines.append(f"- AI usage: {r['ai']}")
        lines.extend(f"- FLAG: {f}" for f in r["flags"])
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate grading files and build the spreadsheet.")
    parser.add_argument("--results", default=str(ROOT / "results"))
    parser.add_argument("--work", default=str(ROOT / "work"))
    parser.add_argument("--out", default=str(ROOT / "output"))
    parser.add_argument("--final", action="store_true", help="write grades_final.csv; refused while any team needs review")
    args = parser.parse_args()

    rubric = load_rubric()
    work, results, out = Path(args.work), Path(args.results), Path(args.out)
    teams = sorted(p.name for p in work.iterdir() if p.is_dir()) if work.exists() else []
    if not teams:
        raise SystemExit("Nothing in work/. Run transcribe.py and extract_notebook.py first.")

    rows = []
    for team in teams:
        facts = read_json(work / team / "facts.json", default={})
        names = read_json(work / team / "private_names.json", default={"students": [], "notebook_file": None})
        rows.append(summarize(team, read_json(results / f"{team}.json"), facts, names, rubric))

    pending = [r["team"] for r in rows if r["status"] != "reviewed"]
    if args.final and pending:
        raise SystemExit(f"Not exported. Still needs review: {', '.join(pending)}. "
                         "Mark each one reviewed with scripts/review.py first.")

    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / ("grades_final.csv" if args.final else "grades_draft.csv")
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            students = r["names"].get("students") or ["NAME NOT FOUND"]
            for name in students:
                writer.writerow({
                    "student_name": name,
                    "notebook_name": r["names"].get("notebook_file") or "",
                    "grade": r["total"] if r["total"] is not None else "",
                    "grade_reason": r["reason"],
                    "flags": "\n".join(r["flags"]),
                    "comments": r["comments"],
                    "ai_usage": r["ai"],
                    "status": r["status"],
                })
    write_queue(rows, rubric, out / "review_queue.md")

    shown = csv_path.relative_to(ROOT) if ROOT in csv_path.resolve().parents else csv_path
    print(f"Wrote {shown} ({sum(len(r['names'].get('students') or [1]) for r in rows)} rows) "
          f"and {shown.parent / 'review_queue.md'}")
    for r in rows:
        total = f"{r['total']}/200" if r["total"] is not None else "no total"
        print(f"  {r['team']}: {total}, {len(r['flags'])} flags, AI usage: {r['ai'].split(':')[0]}, {r['status']}")
    if pending and not args.final:
        print(f"Draft only: {len(pending)} team(s) still need the professor's review.")


if __name__ == "__main__":
    main()
