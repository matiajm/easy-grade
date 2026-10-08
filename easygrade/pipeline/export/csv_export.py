"""CSV export behind the guard (task 1.9): one row per student, the team's shared grade, plus an export log.

Only teams that pass guard.refusal_reasons reach the file. Refused teams are listed (by team id, never by
name) in the export log and in the returned result, with their reasons.

Columns: the professor asked for four ("professor": student name, score, needs your attention, AI usage; the
rubric breakdown goes on a second tab of the Excel file). The plan lists eight ("prd"). Which one is final is
an open decision (docs/DECISIONS.md, 1.9-a), so both are supported and "professor" is the default.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .guard import refusal_reasons

PROFESSOR_COLUMNS = ["Student name", "Score (out of 200)", "Needs your attention", "AI usage"]
PRD_COLUMNS = ["student_name", "notebook_name", "grade", "grade_reason", "flags", "comments", "ai_usage", "status"]

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> str:
    """Text for a CSV cell. Names and comments come from student files, so a value starting with = + - @
    would run as a formula in Excel. A leading apostrophe makes spreadsheets show it as plain text."""
    text = " ".join(("" if value is None else str(value)).splitlines())
    return "'" + text if text.lstrip().startswith(_FORMULA_STARTS) else text


def _flags_text(review: dict) -> str:
    return "; ".join(f for f in (review.get("flags_text") or review.get("flags") or []) if isinstance(f, str))


def _ai_text(review: dict) -> str:
    ai = review.get("ai_usage") or {}
    suggested = ai.get("suggested") if isinstance(ai, dict) else None
    return {"review": "Worth a look", "no_concern": "No concern"}.get(suggested, str(suggested or ""))


def _comments(review: dict) -> str:
    parts = []
    for sec in review.get("sections", []):
        text = sec.get("comment_final") or ""
        if text:
            parts.append(f"{sec.get('section_id')}: {text}")
    return " | ".join(parts)


def _grade(total: Any) -> Any:
    """83.0 -> 83, 83.5 stays 83.5."""
    return f"{total:g}" if isinstance(total, float) else total


def rows_for(review: dict, columns: str) -> list[list[str]]:
    """One row per student; every member gets the same grade (decision D-003)."""
    rows = []
    for student in review["students"]:
        if columns == "prd":
            values = [student["name"], review.get("notebook_name", ""), _grade(review["total"]), review.get("grade_reason", ""),
                      _flags_text(review), _comments(review), _ai_text(review), review["status"]]
        else:
            values = [student["name"], _grade(review["total"]), _flags_text(review), _ai_text(review)]
        rows.append([safe_cell(v) for v in values])
    return rows


@dataclass
class ExportResult:
    exported: list[str] = field(default_factory=list)  # team ids
    refused: dict[str, list[str]] = field(default_factory=dict)  # team id -> reasons
    rows_written: int = 0


def export_csv(reviews: Iterable[tuple[str, Any]], rubric: Any, out_csv: Path, log_path: Path | None = None,
               columns: str = "professor") -> ExportResult:
    """reviews: (team_id, review dict) pairs. Writes out_csv (only passing teams) and appends to log_path."""
    if columns not in ("professor", "prd"):
        raise ValueError("columns must be 'professor' or 'prd'")
    result = ExportResult()
    header = PROFESSOR_COLUMNS if columns == "professor" else PRD_COLUMNS
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        for team_id, review in reviews:
            reasons = refusal_reasons(review, rubric)
            if reasons:
                result.refused[team_id] = reasons
                continue
            for row in rows_for(review, columns):
                writer.writerow(row)
                result.rows_written += 1
            result.exported.append(team_id)
    if log_path is not None:
        entry = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "file": out_csv.name,
                 "columns": columns, "teams_exported": result.exported, "rows_written": result.rows_written,
                 "teams_refused": [{"team_id": t, "reasons": r} for t, r in result.refused.items()]}
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return result
