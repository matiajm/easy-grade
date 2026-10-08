"""Measure the tool: agreement with known-right grades, and consistency between two runs.

Agreement (Jessica's question: how do we know the "right" grade?):
  .venv/bin/python scripts/evaluate.py agreement --key samples/answer_key.json
  The key holds the planned level per category for each fake final. Later, the professor's own
  grades on a few finals become the key.

Consistency (does the tool give the same answer twice?):
  .venv/bin/python scripts/evaluate.py consistency results results_run2
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import LEVEL_NAMES, ROOT, load_rubric, read_json

RANK = {"needs_work": 0, "good": 1, "excellent": 2}


def find_levels(entry: dict, keys: set[str]) -> dict:
    """Find the {category: level} map in an answer-key entry, whatever it is called."""
    if keys & set(entry):
        return {k: v for k, v in entry.items() if k in keys}
    for value in entry.values():
        if isinstance(value, dict):
            found = find_levels(value, keys)
            if found:
                return found
    return {}


def find_ai(entry: dict):
    for k, v in entry.items():
        if "ai" in k.lower():
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                for kk in ("status", "planned", "expected", "value"):
                    if isinstance(v.get(kk), str):
                        return v[kk]
    return None


def normalize(level) -> str:
    return str(level).strip().lower().replace(" ", "_").replace("-", "_")


def agreement(key_path: Path, results_dir: Path) -> None:
    rubric = load_rubric()
    keys = {c["key"] for c in rubric["categories"]}
    names = {c["key"]: c["name"] for c in rubric["categories"]}
    key = read_json(key_path)
    teams = key.get("teams", key) if isinstance(key, dict) else {}

    exact = within = total = ai_match = ai_total = 0
    print(f"{'team':<10} {'category':<36} {'planned':<11} {'tool':<11} result")
    for team, entry in teams.items():
        if not isinstance(entry, dict):
            continue
        result = read_json(results_dir / f"{team}.json")
        if result is None:
            print(f"{team:<10} not graded yet")
            continue
        planned = find_levels(entry, keys)
        for cat, level in planned.items():
            tool_entry = result.get("categories", {}).get(cat, {})
            tool_level = tool_entry.get("suggested_level", tool_entry.get("level"))
            p, t = normalize(level), normalize(tool_level)
            if p not in RANK or t not in RANK:
                continue
            gap = abs(RANK[p] - RANK[t])
            total += 1
            exact += gap == 0
            within += gap <= 1
            mark = "match" if gap == 0 else ("off by one level" if gap == 1 else "OFF BY TWO LEVELS")
            print(f"{team:<10} {names[cat]:<36} {LEVEL_NAMES[p]:<11} {LEVEL_NAMES[t]:<11} {mark}")
        planned_ai = find_ai(entry)
        tool_ai = result.get("ai_usage", {}).get("suggested_status", result.get("ai_usage", {}).get("status"))
        if planned_ai:
            ai_total += 1
            ai_match += planned_ai.strip().lower() == str(tool_ai).strip().lower()
            print(f"{team:<10} {'AI usage':<36} {planned_ai:<11} {str(tool_ai):<11} "
                  f"{'match' if planned_ai.strip().lower() == str(tool_ai).strip().lower() else 'MISMATCH'}")

    if total:
        print(f"\nExact level match: {exact}/{total} ({100 * exact / total:.0f}%)")
        print(f"Within one level:  {within}/{total} ({100 * within / total:.0f}%)   PRD target: at least [80]%")
    if ai_total:
        print(f"AI-usage flag match: {ai_match}/{ai_total}")


def consistency(run_a: Path, run_b: Path) -> None:
    rubric = load_rubric()
    same = total = 0
    diffs = []
    for path in sorted(run_a.glob("*.json")):
        a, b = read_json(path), read_json(run_b / path.name)
        if b is None:
            print(f"{path.stem}: missing in {run_b}")
            continue
        for cat in rubric["categories"]:
            ea, eb = a["categories"].get(cat["key"], {}), b["categories"].get(cat["key"], {})
            la = ea.get("suggested_level", ea.get("level"))
            lb = eb.get("suggested_level", eb.get("level"))
            sa = ea.get("suggested_score", ea.get("score"))
            sb = eb.get("suggested_score", eb.get("score"))
            total += 1
            same += la == lb
            if isinstance(sa, int) and isinstance(sb, int):
                diffs.append(abs(sa - sb))
            if la != lb:
                print(f"{path.stem} {cat['name']}: {la} vs {lb}")
        if a.get("ai_usage", {}).get("status") != b.get("ai_usage", {}).get("status"):
            print(f"{path.stem} AI usage: {a['ai_usage'].get('status')} vs {b['ai_usage'].get('status')}")
    if total:
        print(f"\nSame level in both runs: {same}/{total} ({100 * same / total:.0f}%)")
    if diffs:
        print(f"Average score difference: {sum(diffs) / len(diffs):.1f} points, largest {max(diffs)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure agreement and consistency.")
    sub = parser.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("agreement")
    a.add_argument("--key", default=str(ROOT / "samples" / "answer_key.json"))
    a.add_argument("--results", default=str(ROOT / "results"))
    c = sub.add_parser("consistency")
    c.add_argument("run_a")
    c.add_argument("run_b")
    args = parser.parse_args()
    if args.mode == "agreement":
        agreement(Path(args.key), Path(args.results))
    else:
        consistency(Path(args.run_a), Path(args.run_b))


if __name__ == "__main__":
    main()
