"""Everything the app window can ask Python to do.

pywebview exposes each public method of `Api` to JavaScript as
`window.pywebview.api.<method>(...)`. Every method returns a plain dict:
    {"ok": True, ...data}   or   {"ok": False, "error": "message for the user"}

The class has no dependency on pywebview except in the three dialog methods,
so it can be tested without opening a window (see tests/test_desktop_api.py).

One folder = one assignment. The app writes only inside <folder>/_grading/:
    grades.db      progress (safe to stop and resume)
    rubric.json    the rubric in use
    grades.xlsx, gradebook.csv, feedback/   exports
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from grader import export as ex
from grader.ingest import load_roster, scan_submissions
from grader.rubric import Rubric, RubricError, load_rubric, write_rubric_template
from grader.scoring import GraderOutputError, SimulatedGrader, parse_grader_output
from grader.store import GradeStore, StoreError

from .media import MediaServer
from .notebook import read_notebook

GRADING_DIR = "_grading"
SAMPLE_RUBRIC = Path(__file__).resolve().parent.parent / "rubrics" / "project2_regression.json"
STATUS_LABEL = {"pending": "Not graded", "graded": "Needs review", "approved": "Approved", "error": "Error"}


def _safe(fn):
    """Turn expected errors into {"ok": False, "error": ...} so the UI can show them."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (RubricError, StoreError, GraderOutputError, ValueError, FileNotFoundError, KeyError) as e:
            return {"ok": False, "error": str(e).strip("'\"")}
        except PermissionError as e:
            return {"ok": False, "error": f"Can't write {Path(e.filename or '').name or 'the file'}. "
                                          "If it's open in Excel, close it and try again."}
        except Exception as e:  # unexpected: log for the developer, short message for the user
            traceback.print_exc()
            return {"ok": False, "error": f"Something went wrong: {e}"}
    return wrapper


class Api:
    def __init__(self, media: MediaServer | None = None):
        self._window = None
        self._folder: Path | None = None
        self._rubric: Rubric | None = None
        self._media = media

    # ---------- internals (underscore = not exposed to JavaScript) ----------
    def _attach(self, window) -> None:
        self._window = window

    @property
    def _gdir(self) -> Path:
        return self._folder / GRADING_DIR

    def _store(self) -> GradeStore:
        # A new connection per call: pywebview runs calls on different threads,
        # and SQLite connections can't be shared across threads.
        return GradeStore(self._gdir / "grades.db")

    def _need_folder(self) -> None:
        if self._folder is None:
            raise ValueError("Open a submissions folder first.")

    def _need_rubric(self) -> Rubric:
        self._need_folder()
        if self._rubric is None:
            raise ValueError("Choose a rubric first.")
        return self._rubric

    def _roster_path(self) -> Path | None:
        for p in (self._folder / "roster.csv", self._gdir / "roster.csv"):
            if p.is_file():
                return p
        return None

    def _sub(self, st: GradeStore, student_id: str):
        aid, _ = st.get_assignment(self._rubric.assignment)
        return aid, st.submission(aid, student_id)

    def _dialog(self, kind: str, **kw):
        import webview  # only needed when a real window exists
        if self._window is None:
            raise ValueError("No app window.")
        fd = getattr(webview, "FileDialog", None)
        const = {
            "folder": getattr(fd, "FOLDER", None) if fd else None,
            "open": getattr(fd, "OPEN", None) if fd else None,
            "save": getattr(fd, "SAVE", None) if fd else None,
        }[kind]
        if const is None:  # older pywebview
            const = {"folder": webview.FOLDER_DIALOG, "open": webview.OPEN_DIALOG, "save": webview.SAVE_DIALOG}[kind]
        result = self._window.create_file_dialog(const, **kw)
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    # ---------- folder ----------
    @_safe
    def choose_folder(self):
        path = self._dialog("folder")
        if not path:
            return {"ok": False, "cancelled": True}
        return self.open_folder(path)

    @_safe
    def open_folder(self, path: str):
        folder = Path(path).expanduser().resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder}")
        if folder.name == GRADING_DIR:
            folder = folder.parent
        self._folder = folder
        self._rubric = None
        self._gdir.mkdir(exist_ok=True)
        saved = self._gdir / "rubric.json"
        if saved.is_file():
            self._rubric = load_rubric(saved)
            with self._store() as st:
                st.save_assignment(self._rubric)
            self._scan()
        return self.get_state()

    # ---------- rubric ----------
    @_safe
    def choose_rubric(self, replace: bool = False):
        self._need_folder()
        path = self._dialog("open", file_types=("Rubric files (*.json;*.xlsx;*.csv)", "All files (*.*)"))
        if not path:
            return {"ok": False, "cancelled": True}
        return self.use_rubric(path, replace)

    @_safe
    def use_rubric(self, path: str, replace: bool = False):
        self._need_folder()
        rubric = load_rubric(path)
        with self._store() as st:
            st.save_assignment(rubric, replace=replace)
        rubric.save(self._gdir / "rubric.json")
        self._rubric = rubric
        self._scan()
        return self.get_state()

    @_safe
    def use_sample_rubric(self):
        return self.use_rubric(str(SAMPLE_RUBRIC))

    @_safe
    def save_rubric_template(self):
        path = self._dialog("save", save_filename="rubric_template.xlsx")
        if not path:
            return {"ok": False, "cancelled": True}
        write_rubric_template(path, load_rubric(SAMPLE_RUBRIC))
        return {"ok": True, "path": str(path)}

    # ---------- submissions ----------
    def _scan(self) -> int:
        roster_file = self._roster_path()
        found = scan_submissions(self._folder, load_roster(roster_file) if roster_file else None)
        with self._store() as st:
            aid, _ = st.get_assignment(self._rubric.assignment)
            for s in found:
                st.upsert_submission(aid, s.student_id, s.student_name, s.email,
                                     str(s.notebook) if s.notebook else None,
                                     str(s.video) if s.video else None, s.late, s.flags)
        return len(found)

    @_safe
    def scan(self):
        self._need_rubric()
        self._scan()
        return self.get_state()

    # ---------- state ----------
    @_safe
    def get_state(self):
        if self._folder is None:
            return {"ok": True, "folder": None}
        state = {
            "ok": True,
            "folder": str(self._folder),
            "folder_name": self._folder.name,
            "grading_dir": str(self._gdir),
            "roster": str(self._roster_path()) if self._roster_path() else None,
            "rubric": self._rubric.to_dict() if self._rubric else None,
            "ai_ready": False,  # becomes True when the real graders (steps 2–3) are connected
            "students": [],
            "counts": {"approved": 0, "graded": 0, "pending": 0, "error": 0, "flagged": 0},
        }
        if self._rubric is None:
            # Show what's in the folder even before a rubric is chosen.
            roster_file = self._roster_path()
            for s in scan_submissions(self._folder, load_roster(roster_file) if roster_file else None):
                state["students"].append({
                    "id": s.student_id, "name": s.student_name, "status": "pending", "status_label": "Not graded",
                    "flags": s.flags, "has_notebook": s.notebook is not None, "has_video": s.video is not None,
                    "late": s.late, "total": None, "scores": {},
                })
                if s.flags:
                    state["counts"]["flagged"] += 1
            return state
        with self._store() as st:
            aid, rubric = st.get_assignment(self._rubric.assignment)
            for s in st.submissions(aid):
                sc = st.scores(s.id)
                state["students"].append({
                    "id": s.student_id, "name": s.student_name, "email": s.email,
                    "status": s.status, "status_label": STATUS_LABEL[s.status],
                    "flags": s.flags, "late": s.late,
                    "has_notebook": bool(s.notebook_path), "has_video": bool(s.video_path),
                    "total": st.total(s.id, rubric),
                    "scores": {cid: {"final": r["final_score"], "ai": r["ai_score"],
                                     "changed": bool(r["overridden"]) and r["ai_score"] is not None}
                               for cid, r in sc.items()},
                })
                state["counts"][s.status] = state["counts"].get(s.status, 0) + 1
                if s.flags:
                    state["counts"]["flagged"] += 1
        return state

    @_safe
    def get_student(self, student_id: str):
        rubric = self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            sc = st.scores(s.id)
            criteria = []
            for c in rubric.criteria:
                r = sc.get(c.id)
                criteria.append({
                    "id": c.id, "name": c.name, "source": c.source, "points": c.points,
                    "levels": [[l.score, l.label, l.description] for l in c.levels],
                    "ai_score": r["ai_score"] if r else None,
                    "ai_level": r["ai_level"] if r else None,
                    "reason": (r["ai_reason"] or "") if r else "",
                    "evidence": json.loads(r["evidence"] or "[]") if r else [],
                    "confidence": r["confidence"] if r else None,
                    "final": r["final_score"] if r else None,
                    "changed": bool(r and r["overridden"] and r["ai_score"] is not None),
                    "comment": (r["comment"] or "") if r else "",
                })
            total = st.total(s.id, rubric)
        notebook = read_notebook(s.notebook_path) if s.notebook_path else {"cells": [], "error": None}
        video_url = None
        if s.video_path and self._media and Path(s.video_path).is_file():
            video_url = self._media.url_for(s.video_path)
        return {
            "ok": True, "id": s.student_id, "name": s.student_name, "email": s.email,
            "status": s.status, "status_label": STATUS_LABEL[s.status], "flags": s.flags, "late": s.late,
            "notebook_name": Path(s.notebook_path).name if s.notebook_path else None,
            "video_name": Path(s.video_path).name if s.video_path else None,
            "notebook": notebook, "video_url": video_url,
            "criteria": criteria, "total": total, "points": rubric.total_points,
            "feedback": s.feedback,
        }

    # ---------- review ----------
    @_safe
    def set_score(self, student_id: str, criterion_id: str, score: float):
        rubric = self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            st.override_score(s.id, rubric, criterion_id, float(score))
        return {"ok": True}

    @_safe
    def set_comment(self, student_id: str, criterion_id: str, text: str):
        self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            st.set_comment(s.id, criterion_id, text)
        return {"ok": True}

    @_safe
    def set_feedback(self, student_id: str, text: str):
        self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            st.set_feedback(s.id, text)
        return {"ok": True}

    @_safe
    def approve(self, student_id: str):
        rubric = self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            st.approve(s.id, rubric)
        return {"ok": True}

    @_safe
    def reopen(self, student_id: str):
        self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            st.set_status(s.id, "graded")
        return {"ok": True}

    # ---------- grading ----------
    @_safe
    def grade_simulated(self, student_id: str):
        """Fake AI scores for testing the workflow. Replaced by the real graders in steps 2–3."""
        rubric = self._need_rubric()
        with self._store() as st:
            _, s = self._sub(st, student_id)
            if not s.notebook_path and not s.video_path:
                return {"ok": True, "skipped": True, "reason": "Nothing submitted"}
            raw = SimulatedGrader().grade(rubric, s.student_id, has_video=bool(s.video_path))
            results, feedback, flags = parse_grader_output(rubric, raw)
            st.record_ai_results(s.id, rubric, results, feedback)
            for f in flags:
                st.add_flag(s.id, f)
        return {"ok": True}

    # ---------- export ----------
    @_safe
    def export_all(self, include_unapproved: bool = False):
        rubric = self._need_rubric()
        out = self._gdir
        lines = []
        with self._store() as st:
            summary = ex.export_excel(st, rubric.assignment, out / "grades.xlsx")
            lines.append(f"grades.xlsx: {summary.students} students, {summary.approved} approved, "
                         f"{summary.needs_review} need review, {summary.not_graded} not graded")
            msg = ex.export_gradebook_csv(st, rubric.assignment, out / "gradebook.csv",
                                          approved_only=not include_unapproved)
            lines.append("gradebook.csv: " + msg.split(": ", 1)[1])
            lms = out / "lms_gradebook.csv"
            if lms.is_file():
                msg = ex.export_gradebook_csv(st, rubric.assignment, out / "gradebook_for_lms.csv",
                                              lms_template=lms, approved_only=not include_unapproved)
                lines.append("gradebook_for_lms.csv: " + msg.split(": ", 1)[1])
            n = ex.export_feedback_files(st, rubric.assignment, out / "feedback")
            lines.append(f"feedback/: {n} files")
        return {"ok": True, "folder": str(out), "lines": lines}

    @_safe
    def show_exports(self):
        self._need_folder()
        path = str(self._gdir)
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True}
