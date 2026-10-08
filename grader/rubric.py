"""Rubric model: load, validate, save, and import from Excel/CSV.

A rubric is a list of criteria. Each criterion has a point value, a source
(what evidence the grader looks at), and a set of performance levels.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

SOURCES = ("notebook", "video", "both")

# Column names for spreadsheet import (one row per level).
TABLE_COLUMNS = [
    "criterion_id",
    "criterion_name",
    "source",
    "points",
    "level_score",
    "level_label",
    "level_description",
]


class RubricError(ValueError):
    """Raised when a rubric is invalid. `problems` lists every issue found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Rubric is invalid:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class Level:
    score: float
    label: str
    description: str = ""


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    source: str
    points: float
    levels: tuple[Level, ...]
    description: str = ""

    def level_for(self, score: float) -> Level | None:
        for lvl in self.levels:
            if lvl.score == score:
                return lvl
        return None


@dataclass(frozen=True)
class Rubric:
    assignment: str
    criteria: tuple[Criterion, ...]
    version: int = 1
    notes: str = ""

    @property
    def total_points(self) -> float:
        return sum(c.points for c in self.criteria)

    def criterion(self, criterion_id: str) -> Criterion:
        for c in self.criteria:
            if c.id == criterion_id:
                return c
        raise KeyError(f"No criterion with id '{criterion_id}'")

    @property
    def criterion_ids(self) -> list[str]:
        return [c.id for c in self.criteria]

    # ---------- validation ----------
    def validate(self) -> "Rubric":
        problems: list[str] = []
        if not self.assignment.strip():
            problems.append("Assignment name is empty.")
        if not self.criteria:
            problems.append("Rubric has no criteria.")
        seen: set[str] = set()
        for c in self.criteria:
            where = f"Criterion '{c.id or c.name}'"
            if not c.id or not c.id.replace("_", "").isalnum():
                problems.append(f"{where}: id must be letters, digits or underscores.")
            if c.id in seen:
                problems.append(f"{where}: duplicate id.")
            seen.add(c.id)
            if c.source not in SOURCES:
                problems.append(f"{where}: source must be one of {', '.join(SOURCES)} (got '{c.source}').")
            if c.points <= 0:
                problems.append(f"{where}: points must be greater than 0.")
            if not c.levels:
                problems.append(f"{where}: needs at least one level.")
                continue
            scores = [l.score for l in c.levels]
            if len(set(scores)) != len(scores):
                problems.append(f"{where}: two levels share the same score.")
            if max(scores) != c.points:
                problems.append(
                    f"{where}: top level scores {max(scores):g} but the criterion is worth {c.points:g}."
                )
            for l in c.levels:
                if l.score < 0 or l.score > c.points:
                    problems.append(f"{where}: level '{l.label}' score {l.score:g} is outside 0–{c.points:g}.")
        if problems:
            raise RubricError(problems)
        return self

    # ---------- (de)serialization ----------
    @classmethod
    def from_dict(cls, data: dict) -> "Rubric":
        try:
            criteria = tuple(
                Criterion(
                    id=str(c["id"]).strip(),
                    name=str(c["name"]).strip(),
                    source=str(c.get("source", "notebook")).strip().lower(),
                    points=float(c["points"]),
                    description=str(c.get("description", "")),
                    levels=tuple(
                        sorted(
                            (
                                Level(float(l["score"]), str(l["label"]), str(l.get("description", "")))
                                for l in c.get("levels", [])
                            ),
                            key=lambda l: -l.score,
                        )
                    ),
                )
                for c in data.get("criteria", [])
            )
        except (KeyError, TypeError, ValueError) as e:
            raise RubricError([f"Malformed rubric data: {e!r}"]) from e
        return cls(
            assignment=str(data.get("assignment", "")).strip(),
            criteria=criteria,
            version=int(data.get("version", 1)),
            notes=str(data.get("notes", "")),
        ).validate()

    def to_dict(self) -> dict:
        return {
            "assignment": self.assignment,
            "version": self.version,
            "notes": self.notes,
            "total_points": self.total_points,
            "criteria": [
                {
                    "id": c.id,
                    "name": c.name,
                    "source": c.source,
                    "points": c.points,
                    "description": c.description,
                    "levels": [
                        {"score": l.score, "label": l.label, "description": l.description} for l in c.levels
                    ],
                }
                for c in self.criteria
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


# ---------- loading ----------
def load_rubric(path: str | Path, assignment: str | None = None) -> Rubric:
    """Load a rubric from .json, .xlsx or .csv."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if assignment:
            data["assignment"] = assignment
        return Rubric.from_dict(data)
    if suffix in (".xlsx", ".xlsm"):
        rows, sheet_title = _read_xlsx_rows(path)
        return _rubric_from_rows(rows, assignment or sheet_title or path.stem)
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return _rubric_from_rows(rows, assignment or path.stem)
    raise RubricError([f"Unsupported rubric file type '{suffix}'. Use .json, .xlsx or .csv."])


def _norm(key: str) -> str:
    return str(key or "").strip().lower().replace(" ", "_")


def _read_xlsx_rows(path: Path) -> tuple[list[dict], str | None]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb["Rubric"] if "Rubric" in wb.sheetnames else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [_norm(h) for h in next(it, [])]
        rows = []
        for values in it:
            if values is None or all(v in (None, "") for v in values):
                continue
            rows.append({header[i]: values[i] for i in range(min(len(header), len(values)))})
        # Optional assignment name in a sheet called "Info", cell B1.
        title = None
        if "Info" in wb.sheetnames:
            title = wb["Info"]["B1"].value
    finally:
<<<<<<< HEAD
        # Read-only workbooks keep the file open until closed (locks it on Windows).
        wb.close()
=======
        wb.close()  # read-only workbooks keep the file open (locks it on Windows)
>>>>>>> 5ab76773b3480fae89b5b3b64c2cb3d600d8b4b7
    return rows, (str(title).strip() if title else None)


def _rubric_from_rows(rows: list[dict], assignment: str) -> Rubric:
    rows = [{_norm(k): v for k, v in r.items()} for r in rows]
    missing = [c for c in TABLE_COLUMNS if rows and c not in rows[0]]
    if missing:
        raise RubricError([f"Spreadsheet is missing column(s): {', '.join(missing)}. Expected: {', '.join(TABLE_COLUMNS)}."])
    criteria: dict[str, dict] = {}
    problems = []
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        cid = str(r.get("criterion_id") or "").strip()
        if not cid:
            problems.append(f"Row {i}: criterion_id is empty.")
            continue
        c = criteria.setdefault(
            cid,
            {
                "id": cid,
                "name": r.get("criterion_name") or cid,
                "source": r.get("source") or "notebook",
                "points": r.get("points"),
                "levels": [],
            },
        )
        # Fill blanks on continuation rows from the first row of the criterion.
        if r.get("points") not in (None, "") and c["points"] in (None, ""):
            c["points"] = r["points"]
        try:
            c["levels"].append(
                {
                    "score": float(r.get("level_score")),
                    "label": str(r.get("level_label") or "").strip(),
                    "description": str(r.get("level_description") or "").strip(),
                }
            )
        except (TypeError, ValueError):
            problems.append(f"Row {i}: level_score '{r.get('level_score')}' is not a number.")
    if problems:
        raise RubricError(problems)
    return Rubric.from_dict({"assignment": assignment, "criteria": list(criteria.values())})


def write_rubric_template(path: str | Path, example: Rubric | None = None) -> None:
    """Write an Excel rubric template the professor can fill in."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Rubric"
    ws.append(TABLE_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
    if example:
        for c in example.criteria:
            for l in c.levels:
                ws.append([c.id, c.name, c.source, c.points, l.score, l.label, l.description])
    widths = [18, 28, 11, 8, 12, 16, 70]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    for row in ws.iter_rows(min_row=2):
        row[6].alignment = Alignment(wrap_text=True, vertical="top")
    dv = DataValidation(type="list", formula1='"notebook,video,both"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("C2:C500")
    ws.freeze_panes = "A2"

    info = wb.create_sheet("Info")
    info["A1"], info["B1"] = "Assignment name", (example.assignment if example else "")
    info["A3"] = "How to fill in the Rubric sheet"
    info["A3"].font = Font(bold=True)
    tips = [
        "One row per performance level. Repeat criterion_id, name, source and points on each level row.",
        "source: notebook = graded from the .ipynb, video = from the walkthrough, both = compare the two.",
        "The highest level_score of a criterion must equal its points.",
        "criterion_id: short, no spaces (e.g. data_cleaning). It becomes the column name in the export.",
    ]
    for i, t in enumerate(tips, start=4):
        info[f"A{i}"] = "• " + t
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 50
    wb.save(path)
