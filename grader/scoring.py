"""The contract between the grader (AI or human) and the rest of the app.

Step 1 ships three ways to produce scores:
  * `output_schema(rubric)` + `parse_grader_output(...)`: the JSON contract an
    AI model must follow. The model can only choose one of the rubric's levels,
    which keeps scores consistent and the export clean. Steps 2 and 3 (notebook
    and video grading) plug in here.
  * `load_manual_scores(...)`: scores the professor typed into a spreadsheet.
  * `SimulatedGrader`: fake, deterministic results for demos and tests.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from .rubric import Rubric


class GraderOutputError(ValueError):
    pass


@dataclass
class CriterionResult:
    criterion_id: str
    score: float
    reason: str = ""
    evidence: list[str] = field(default_factory=list)  # e.g. ["cell 14", "video 03:42"]
    confidence: float | None = None                     # 0–1, how sure the grader is


# ---------- AI output contract ----------
def output_schema(rubric: Rubric) -> dict:
    """JSON Schema the AI model's reply must match (use with structured outputs)."""
    crit_props = {}
    for c in rubric.criteria:
        crit_props[c.id] = {
            "type": "object",
            "description": f"{c.name} ({c.points:g} pts, graded from {c.source})",
            "properties": {
                "score": {"type": "number", "enum": [l.score for l in c.levels]},
                "reason": {"type": "string", "description": "1–3 sentences tied to the level description."},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Where to look: 'cell 7', 'video 02:15', etc.",
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["score", "reason", "evidence", "confidence"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "object",
                "properties": crit_props,
                "required": rubric.criterion_ids,
                "additionalProperties": False,
            },
            "feedback": {"type": "string", "description": "Short, encouraging feedback addressed to the student."},
            "flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["criteria", "feedback", "flags"],
        "additionalProperties": False,
    }


def parse_grader_output(rubric: Rubric, data: dict) -> tuple[list[CriterionResult], str, list[str]]:
    """Validate a grader reply against the rubric. Returns (results, feedback, flags)."""
    problems = []
    crit_data = data.get("criteria") or {}
    results: list[CriterionResult] = []
    for c in rubric.criteria:
        d = crit_data.get(c.id)
        if d is None:
            problems.append(f"missing criterion '{c.id}'")
            continue
        try:
            score = float(d["score"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"'{c.id}': score is missing or not a number")
            continue
        if c.level_for(score) is None:
            allowed = ", ".join(f"{l.score:g}" for l in c.levels)
            problems.append(f"'{c.id}': score {score:g} is not a rubric level ({allowed})")
            continue
        conf = d.get("confidence")
        results.append(
            CriterionResult(
                criterion_id=c.id,
                score=score,
                reason=str(d.get("reason", "")).strip(),
                evidence=[str(e) for e in d.get("evidence", [])],
                confidence=float(conf) if conf is not None else None,
            )
        )
    extra = set(crit_data) - set(rubric.criterion_ids)
    if extra:
        problems.append(f"unknown criteria: {', '.join(sorted(extra))}")
    if problems:
        raise GraderOutputError("Grader output rejected: " + "; ".join(problems))
    return results, str(data.get("feedback", "")).strip(), [str(f) for f in data.get("flags", [])]


# ---------- manual scores ----------
def load_manual_scores(path: str | Path, rubric: Rubric) -> dict[str, tuple[dict[str, float], str]]:
    """Read a CSV with columns: student_id, <criterion ids...>, feedback (optional).

    Returns {student_id: ({criterion_id: score}, feedback)}. Blank cells are skipped.
    """
    out: dict[str, tuple[dict[str, float], str]] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = {h.strip(): h for h in reader.fieldnames or []}
        if "student_id" not in cols:
            raise ValueError("Scores CSV needs a 'student_id' column.")
        unknown = [h for h in cols if h not in ("student_id", "student_name", "feedback") and h not in rubric.criterion_ids]
        if unknown:
            raise ValueError(f"Columns not in the rubric: {', '.join(unknown)}")
        for i, row in enumerate(reader, start=2):
            sid = (row[cols["student_id"]] or "").strip()
            if not sid:
                continue
            scores = {}
            for cid in rubric.criterion_ids:
                if cid in cols and (row[cols[cid]] or "").strip():
                    try:
                        scores[cid] = float(row[cols[cid]])
                    except ValueError:
                        raise ValueError(f"Row {i}, column '{cid}': '{row[cols[cid]]}' is not a number.")
            fb = (row.get(cols.get("feedback", ""), "") or "").strip() if "feedback" in cols else ""
            out[sid] = (scores, fb)
    return out


def write_scores_template(path: str | Path, rubric: Rubric, student_ids: list[tuple[str, str]]) -> None:
    """CSV template for manual scoring: one row per student, one column per criterion."""
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "student_name", *rubric.criterion_ids, "feedback"])
        for sid, name in student_ids:
            w.writerow([sid, name, *[""] * len(rubric.criteria), ""])


# ---------- simulated grader (demo only) ----------
_REASONS = {
    0: "Meets every point in the top-level description.",
    1: "Solid work; a few points from the top level are missing or thin.",
    2: "Partly there; key steps are missing or not justified.",
    3: "Little or no evidence for this criterion.",
}


class SimulatedGrader:
    """Produces plausible, repeatable fake results. Replace with the real
    notebook/video graders in steps 2 and 3."""

    def __init__(self, seed: int = 7):
        self.seed = seed

    def grade(self, rubric: Rubric, student_id: str, has_video: bool = True) -> dict:
        rng = random.Random(f"{self.seed}:{student_id}")
        skill = rng.choice([0, 0, 1, 1, 1, 2])  # most students do fine
        crit = {}
        for c in rubric.criteria:
            if not has_video and c.source in ("video", "both"):
                crit[c.id] = {"score": c.levels[-1].score, "reason": "No video was available to grade.",
                              "evidence": [], "confidence": 0.99}
                continue
            idx = min(len(c.levels) - 1, max(0, skill + rng.choice([-1, 0, 0, 0, 1])))
            lvl = c.levels[idx]
            # Evidence fits the sample notebook (9 cells) and sample video (45 s).
            if c.source == "video":
                ev = [f"video 00:{rng.randint(0, 44):02d}"]
            elif c.source == "both":
                ev = [f"cell {rng.randint(2, 8)}", f"video 00:{rng.randint(0, 44):02d}"]
            else:
                ev = [f"cell {rng.randint(2, 8)}"]
            crit[c.id] = {
                "score": lvl.score,
                "reason": _REASONS.get(idx, _REASONS[3]),
                "evidence": ev,
                "confidence": round(rng.uniform(0.55, 0.97), 2),
            }
        return {
            "criteria": crit,
            "feedback": "Good structure overall. See the per-criterion notes for where to push further.",
            "flags": [],
        }
