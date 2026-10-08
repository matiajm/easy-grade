"""Eval harness v1: level agreement and hard-failure recall for one batch.

Run: python -m easygrade.eval.run_eval BATCH [--key answer_key.json]

BATCH is a folder with one sub-folder per team (bundle files, including
suggestion.json). The answer key defaults to BATCH/answer_key.json, then
easygrade/eval/answer_key.json. Expected answer-key shape (compatible with the
prototype key):

    {
      "level_keys": ["excellent", "good", "needs_work"],   # best to worst
      "teams": {
        "team-001": {
          "planned_levels": {"data_cleaning": "excellent", ...},   # null = no grade expected
          "seeded_problems": [{"problem": "empty notebook", "flag": "NOTEBOOK_EMPTY"}]
        }
      }
    }
"""
import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_KEY = Path(__file__).resolve().parent / "answer_key.json"


@dataclass
class EvalResult:
    sections_total: int = 0
    sections_agree: int = 0
    sections_ungraded: int = 0  # key expects a level, suggestion has none (failed, missing)
    seeded_total: int = 0
    seeded_caught: int = 0
    prompt_versions: set = field(default_factory=set)
    misses: list = field(default_factory=list)

    @property
    def level_agreement(self) -> float | None:
        return self.sections_agree / self.sections_total if self.sections_total else None

    @property
    def hard_failure_recall(self) -> float | None:
        return self.seeded_caught / self.seeded_total if self.seeded_total else None


def _flag_codes(node) -> set[str]:
    """All flag codes anywhere in a bundle file (top level and per section)."""
    codes = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "flags" and isinstance(v, list):
                codes |= {f["code"] for f in v if isinstance(f, dict) and "code" in f}
            else:
                codes |= _flag_codes(v)
    elif isinstance(node, list):
        for v in node:
            codes |= _flag_codes(v)
    return codes


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def evaluate(batch: Path, key: dict) -> EvalResult:
    order = key["level_keys"]
    r = EvalResult()
    for team_id, expected in key["teams"].items():
        team_dir = batch / team_id
        suggestion = _load(team_dir / "suggestion.json") or {}
        if suggestion.get("prompt_version"):
            r.prompt_versions.add(suggestion["prompt_version"])
        suggested = {s["section_id"]: s.get("level") for s in suggestion.get("sections", [])}

        for section_id, want in expected.get("planned_levels", {}).items():
            if want is None:
                continue
            r.sections_total += 1
            got = suggested.get(section_id)
            if got in order and abs(order.index(got) - order.index(want)) <= 1:
                r.sections_agree += 1
            else:
                if got is None:
                    r.sections_ungraded += 1
                r.misses.append(f"{team_id}/{section_id}: key {want}, suggested {got}")

        codes = set()
        for f in team_dir.glob("*.json"):
            codes |= _flag_codes(_load(f))
        for p in expected.get("seeded_problems", []):
            r.seeded_total += 1
            if p["flag"] in codes:
                r.seeded_caught += 1
            else:
                r.misses.append(f"{team_id}: seeded '{p['problem']}' missing flag {p['flag']}")
    return r


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def report(r: EvalResult) -> str:
    versions = ", ".join(sorted(r.prompt_versions)) or "none found"
    lines = [
        f"Prompt version: {versions}" + ("  (WARNING: mixed versions)" if len(r.prompt_versions) > 1 else ""),
        f"Level agreement: {_pct(r.level_agreement)} ({r.sections_agree}/{r.sections_total} sections within one level; "
        f"{r.sections_ungraded} ungraded)",
        f"Hard-failure recall: {_pct(r.hard_failure_recall)} ({r.seeded_caught}/{r.seeded_total} seeded problems flagged)",
    ]
    if r.misses:
        lines.append("Misses:")
        lines += [f"  {m}" for m in r.misses]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("batch", type=Path)
    p.add_argument("--key", type=Path)
    a = p.parse_args()
    key_path = a.key or next((k for k in (a.batch / "answer_key.json", DEFAULT_KEY) if k.exists()), None)
    if key_path is None:
        raise SystemExit("No answer key found. Pass --key.")
    print(report(evaluate(a.batch, json.loads(key_path.read_text(encoding="utf-8")))))


if __name__ == "__main__":
    main()
