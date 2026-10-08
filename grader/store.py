"""Local SQLite store for assignments, submissions and per-criterion scores.

Every result is written as soon as it exists, so a crash at student 63 loses
nothing. AI scores and the professor's final scores are kept in separate
columns so overrides are always visible.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .rubric import Rubric

SCHEMA = """
CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    rubric_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
    id             INTEGER PRIMARY KEY,
    assignment_id  INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id     TEXT NOT NULL,
    student_name   TEXT NOT NULL DEFAULT '',
    email          TEXT NOT NULL DEFAULT '',
    notebook_path  TEXT,
    video_path     TEXT,
    late           INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending | graded | approved | error
    flags          TEXT NOT NULL DEFAULT '[]',        -- JSON list of strings
    ai_feedback    TEXT,
    final_feedback TEXT,
    updated_at     TEXT NOT NULL,
    UNIQUE (assignment_id, student_id)
);
CREATE TABLE IF NOT EXISTS scores (
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    criterion_id  TEXT NOT NULL,
    ai_score      REAL,
    ai_level      TEXT,
    ai_reason     TEXT,
    evidence      TEXT NOT NULL DEFAULT '[]',         -- JSON list, e.g. ["cell 14", "video 03:42"]
    confidence    REAL,
    final_score   REAL,
    comment       TEXT,
    overridden    INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (submission_id, criterion_id)
);
"""

STATUSES = ("pending", "graded", "approved", "error")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StoreError(RuntimeError):
    pass


@dataclass
class Submission:
    id: int
    assignment_id: int
    student_id: str
    student_name: str
    email: str
    notebook_path: str | None
    video_path: str | None
    late: bool
    status: str
    flags: list[str]
    ai_feedback: str | None
    final_feedback: str | None

    @property
    def feedback(self) -> str:
        return self.final_feedback if self.final_feedback is not None else (self.ai_feedback or "")


class GradeStore:
    def __init__(self, path: str | Path = "grades.db"):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------- assignments ----------
    def save_assignment(self, rubric: Rubric, replace: bool = False) -> int:
        """Register an assignment with its rubric. Returns the assignment id.

        Changing the rubric of an assignment that already has scores requires
        replace=True, because criteria may no longer line up.
        """
        rubric.validate()
        row = self.db.execute("SELECT id, rubric_json FROM assignments WHERE name = ?", (rubric.assignment,)).fetchone()
        if row is None:
            cur = self.db.execute(
                "INSERT INTO assignments (name, rubric_json, created_at) VALUES (?, ?, ?)",
                (rubric.assignment, rubric.to_json(), _now()),
            )
            self.db.commit()
            return cur.lastrowid
        if row["rubric_json"] != rubric.to_json():
            has_scores = self.db.execute(
                "SELECT 1 FROM scores s JOIN submissions u ON u.id = s.submission_id WHERE u.assignment_id = ? LIMIT 1",
                (row["id"],),
            ).fetchone()
            if has_scores and not replace:
                raise StoreError(
                    f"'{rubric.assignment}' already has scores under a different rubric. "
                    "Use replace=True (CLI: --replace) to update it anyway."
                )
            self.db.execute("UPDATE assignments SET rubric_json = ? WHERE id = ?", (rubric.to_json(), row["id"]))
            self.db.commit()
        return row["id"]

    def get_assignment(self, name: str) -> tuple[int, Rubric]:
        row = self.db.execute("SELECT id, rubric_json FROM assignments WHERE name = ?", (name,)).fetchone()
        if row is None:
            known = [r["name"] for r in self.db.execute("SELECT name FROM assignments ORDER BY name")]
            raise StoreError(f"No assignment named '{name}'. Known: {', '.join(known) or 'none'}.")
        return row["id"], Rubric.from_dict(json.loads(row["rubric_json"]))

    def list_assignments(self) -> list[str]:
        return [r["name"] for r in self.db.execute("SELECT name FROM assignments ORDER BY created_at")]

    # ---------- submissions ----------
    def upsert_submission(
        self,
        assignment_id: int,
        student_id: str,
        student_name: str = "",
        email: str = "",
        notebook_path: str | None = None,
        video_path: str | None = None,
        late: bool = False,
        flags: list[str] | None = None,
    ) -> int:
        self.db.execute(
            """INSERT INTO submissions
                 (assignment_id, student_id, student_name, email, notebook_path, video_path, late, flags, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (assignment_id, student_id) DO UPDATE SET
                 student_name = COALESCE(NULLIF(excluded.student_name, ''), student_name),
                 email        = COALESCE(NULLIF(excluded.email, ''), email),
                 notebook_path = excluded.notebook_path,
                 video_path    = excluded.video_path,
                 late          = excluded.late,
                 flags         = excluded.flags,
                 updated_at    = excluded.updated_at""",
            (assignment_id, student_id, student_name, email, notebook_path, video_path, int(late),
             json.dumps(flags or []), _now()),
        )
        self.db.commit()
        return self.db.execute(
            "SELECT id FROM submissions WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id)
        ).fetchone()["id"]

    def _to_submission(self, r: sqlite3.Row) -> Submission:
        return Submission(
            id=r["id"], assignment_id=r["assignment_id"], student_id=r["student_id"],
            student_name=r["student_name"], email=r["email"], notebook_path=r["notebook_path"],
            video_path=r["video_path"], late=bool(r["late"]), status=r["status"],
            flags=json.loads(r["flags"]), ai_feedback=r["ai_feedback"], final_feedback=r["final_feedback"],
        )

    def submissions(self, assignment_id: int, status: str | None = None) -> list[Submission]:
        sql = "SELECT * FROM submissions WHERE assignment_id = ?"
        args: list = [assignment_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY student_name COLLATE NOCASE, student_id"
        return [self._to_submission(r) for r in self.db.execute(sql, args)]

    def submission(self, assignment_id: int, student_id: str) -> Submission:
        r = self.db.execute(
            "SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id)
        ).fetchone()
        if r is None:
            raise StoreError(f"No submission for student '{student_id}'.")
        return self._to_submission(r)

    def add_flag(self, submission_id: int, flag: str) -> None:
        r = self.db.execute("SELECT flags FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        flags = json.loads(r["flags"])
        if flag not in flags:
            flags.append(flag)
            self.db.execute("UPDATE submissions SET flags = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(flags), _now(), submission_id))
            self.db.commit()

    def set_status(self, submission_id: int, status: str) -> None:
        if status not in STATUSES:
            raise StoreError(f"Unknown status '{status}'.")
        self.db.execute("UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), submission_id))
        self.db.commit()

    # ---------- scores ----------
    def record_ai_results(self, submission_id: int, rubric: Rubric, results, overall_feedback: str | None = None) -> None:
        """Save the grader's results for one submission.

        `results` is a list of scoring.CriterionResult. The final score starts
        equal to the AI score unless the professor has already overridden it.
        """
        ts = _now()
        for res in results:
            crit = rubric.criterion(res.criterion_id)
            level = crit.level_for(res.score)
            self.db.execute(
                """INSERT INTO scores (submission_id, criterion_id, ai_score, ai_level, ai_reason, evidence,
                                       confidence, final_score, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (submission_id, criterion_id) DO UPDATE SET
                     ai_score = excluded.ai_score, ai_level = excluded.ai_level, ai_reason = excluded.ai_reason,
                     evidence = excluded.evidence, confidence = excluded.confidence,
                     final_score = CASE WHEN overridden = 1 THEN final_score ELSE excluded.final_score END,
                     updated_at = excluded.updated_at""",
                (submission_id, res.criterion_id, res.score, level.label if level else None, res.reason,
                 json.dumps(res.evidence), res.confidence, res.score, ts),
            )
        self.db.execute(
            "UPDATE submissions SET ai_feedback = ?, status = CASE WHEN status = 'approved' THEN status ELSE 'graded' END, "
            "updated_at = ? WHERE id = ?",
            (overall_feedback, ts, submission_id),
        )
        self.db.commit()

    def override_score(self, submission_id: int, rubric: Rubric, criterion_id: str, score: float, comment: str | None = None) -> None:
        crit = rubric.criterion(criterion_id)
        if not 0 <= score <= crit.points:
            raise StoreError(f"Score {score:g} for '{crit.name}' must be between 0 and {crit.points:g}.")
        self.db.execute(
            """INSERT INTO scores (submission_id, criterion_id, final_score, comment, overridden, updated_at)
               VALUES (?, ?, ?, ?, 1, ?)
               ON CONFLICT (submission_id, criterion_id) DO UPDATE SET
                 final_score = excluded.final_score,
                 comment = COALESCE(excluded.comment, comment),
                 overridden = CASE WHEN ai_score IS NOT NULL AND ai_score = excluded.final_score THEN 0 ELSE 1 END,
                 updated_at = excluded.updated_at""",
            (submission_id, criterion_id, score, comment, _now()),
        )
        # Editing an approved grade sends it back to review.
        self.db.execute(
            "UPDATE submissions SET status = 'graded', updated_at = ? WHERE id = ? AND status IN ('approved', 'pending')",
            (_now(), submission_id),
        )
        self.db.commit()

    def set_feedback(self, submission_id: int, text: str) -> None:
        self.db.execute("UPDATE submissions SET final_feedback = ?, updated_at = ? WHERE id = ?", (text, _now(), submission_id))
        self.db.commit()

    def scores(self, submission_id: int) -> dict[str, sqlite3.Row]:
        return {r["criterion_id"]: r for r in self.db.execute("SELECT * FROM scores WHERE submission_id = ?", (submission_id,))}

    def approve(self, submission_id: int, rubric: Rubric) -> None:
        scores = self.scores(submission_id)
        missing = [c.name for c in rubric.criteria if c.id not in scores or scores[c.id]["final_score"] is None]
        if missing:
            raise StoreError(f"Can't approve: no score yet for {', '.join(missing)}.")
        self.set_status(submission_id, "approved")

    def total(self, submission_id: int, rubric: Rubric) -> float | None:
        scores = self.scores(submission_id)
        vals = [scores[c.id]["final_score"] if c.id in scores else None for c in rubric.criteria]
        if any(v is None for v in vals):
            return None
        return float(sum(vals))
