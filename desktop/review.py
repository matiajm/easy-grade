"""The review dashboard's extra API: rubric choice and preview, file matching, notebook checks, the review list
and the guarded exports. Mixed into desktop.api.Api, so every public method here is also a pywebview API call and
returns {"ok": True, ...} or {"ok": False, "error": ...}.

Matching choices (a file assigned to a student by hand, "no video for this team") are saved in
<folder>/_grading/matching.json so they survive a rescan and a restart.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from grader.ingest import FLAT_RE, NOTEBOOK_EXT, VIDEO_EXT
from grader.rubric import load_rubric

from . import review_export as rx

RUBRICS_DIR = Path(__file__).resolve().parent.parent / "rubrics"
MEMBER_SPLIT = re.compile(r"\s*(?:&|;|\band\b)\s*", re.I)
LOW_CONFIDENCE = 0.7


def split_members(name: str, fallback: str = "") -> list[str]:
    """'Isabel Moreno & Daniel Park' -> two names. Names with a comma are left whole ('Last, First')."""
    parts = [p.strip() for p in MEMBER_SPLIT.split(name or "") if p.strip()]
    return parts or ([fallback] if fallback else [])


def original_name(file_name: str) -> str:
    """The name the student gave the file, without the LMS prefix <name>_<userid>_<submissionid>_."""
    m = FLAT_RE.match(file_name)
    return m.group("orig") if m else file_name


def rubric_summary(rubric) -> dict:
    return {
        "assignment": rubric.assignment, "total_points": rubric.total_points,
        "criteria": [{
            "id": c.id, "name": c.name, "points": c.points, "source": c.source,
            "levels": [{"label": l.label, "score": l.score, "min": l.floor} for l in c.levels],
        } for c in rubric.criteria],
    }


def friendly_flags(result, orig_name: str, config) -> list[str]:
    """Plain sentences for what the notebook parser found. Cell numbers are 1-based, like the evidence chips."""
    out, checks = [], result.checks
    for flag in result.flags:
        code = flag.code
        if code == "NOTEBOOK_UNREADABLE":
            out.append("The notebook could not be read")
        elif code == "NOTEBOOK_EMPTY":
            out.append("The notebook is empty")
        elif code == "NAME_NOT_FOUND":
            out.append("No student names found in the notebook header")
        elif code == "HEADER_RULES":
            out.append(flag.message.replace("Header is missing required fields", "The header is missing").rstrip("."))
        elif code == "FILENAME_RULES":
            out.append(f"The file name \"{orig_name}\" doesn't follow Lastname1_Lastname2_FinalProject.ipynb")
        elif code == "EXEC_ORDER":
            eo = checks.execution_order
            cells = sorted({i + 1 for i in eo.out_of_order_cells} | {i + 1 for i in eo.skipped})
            out.append("Cells were run out of order" + (f" (cells {', '.join(map(str, cells[:6]))})" if cells else ""))
        elif code == "ERROR_OUTPUT":
            cells = ", ".join(str(i + 1) for i in checks.error_cells[:6])
            out.append(f"The notebook stops with an error (cell {cells})" if len(checks.error_cells) == 1
                       else f"Cells with errors: {cells}")
    return out


class ReviewMixin:
    """Needs self._folder, self._rubric, self._gdir, self._store() from Api."""

    # ------------------------------------------------------------ rubric choice
    def list_rubrics(self):
        """Rubrics shipped with the app (the rubrics/ folder), for the start screen's dropdown."""
        out = []
        for p in sorted(RUBRICS_DIR.glob("*.json")):
            try:
                r = load_rubric(p)
            except Exception:
                continue
            out.append({"file": p.name, "assignment": r.assignment, "points": r.total_points,
                        "criteria": len(r.criteria)})
        current = self._rubric.assignment if self._rubric else None
        return {"ok": True, "rubrics": out, "current": current}

    def preview_rubric(self, path: str):
        """Read a rubric file (.json, .xlsx, .csv) and describe it, without using it."""
        try:
            r = load_rubric(path)
        except Exception as e:  # RubricError carries a readable list of problems
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(path), "name": Path(path).name, **rubric_summary(r)}

    def preview_builtin_rubric(self, file: str):
        p = (RUBRICS_DIR / Path(file).name)
        if not p.is_file():
            return {"ok": False, "error": "That rubric isn't in the app's rubrics folder."}
        return self.preview_rubric(str(p))

    def use_builtin_rubric(self, file: str, replace: bool = False):
        p = RUBRICS_DIR / Path(file).name  # basename only: no path tricks
        if not p.is_file():
            return {"ok": False, "error": "That rubric isn't in the app's rubrics folder."}
        return self.use_rubric(str(p), replace)

    def choose_rubric_preview(self):
        """Open the file dialog and preview the chosen rubric. The window then calls use_rubric(path)."""
        try:
            path = self._dialog("open", file_types=("Rubric files (*.json;*.xlsx;*.csv)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if not path:
            return {"ok": False, "cancelled": True}
        return self.preview_rubric(path)

    # ------------------------------------------------------------ sample data
    def create_sample_folder(self):
        from .sample import create_sample_folder
        base = getattr(self, "sample_root", None) or Path.home() / "EasyGrade sample"
        folder = create_sample_folder(base)
        return self.open_folder(str(folder))

    # ------------------------------------------------------------ matching
    def _matching_path(self) -> Path:
        return self._gdir / "matching.json"

    def _load_matching(self) -> dict:
        try:
            data = json.loads(self._matching_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"assigned": dict(data.get("assigned", {})), "no_video": list(data.get("no_video", []))}

    def _save_matching(self, m: dict) -> None:
        self._gdir.mkdir(exist_ok=True)
        self._matching_path().write_text(json.dumps(m, indent=2), encoding="utf-8")

    def _apply_matching(self, found: list) -> None:
        """Called by Api._scan: put hand-assigned files on their student and honour 'no video'."""
        m = self._load_matching()
        by_id = {s.student_id: s for s in found}
        for path_str, sid in m["assigned"].items():
            p, s = Path(path_str), by_id.get(sid)
            if s is None or not p.is_file():
                continue
            if p.suffix.lower() in VIDEO_EXT:
                s.video = p
                s.flags = [f for f in s.flags if not f.startswith(("No video found", "Video submitted as a link"))]
            elif p.suffix.lower() in NOTEBOOK_EXT:
                s.notebook = p
                s.flags = [f for f in s.flags if not f.startswith(("No notebook", "Nothing submitted"))]
        for sid in m["no_video"]:
            s = by_id.get(sid)
            if s is not None and s.video is None:
                s.flags = [f for f in s.flags if not f.startswith("No video found")]

    def _loose_files(self) -> list[dict]:
        """Top-level files whose names don't name a student, so ingest skipped them."""
        assigned = set(self._load_matching()["assigned"])
        loose = []
        for p in sorted(self._folder.iterdir()):
            if p.name.startswith((".", "_")) or not p.is_file() or FLAT_RE.match(p.name):
                continue
            ext = p.suffix.lower()
            kind = "video" if ext in VIDEO_EXT else "notebook" if ext in NOTEBOOK_EXT else None
            if kind:
                loose.append({"path": str(p), "name": p.name, "kind": kind, "assigned_to": None})
        for f in loose:
            f["assigned_to"] = self._load_matching()["assigned"].get(f["path"])
        # files assigned by hand that are no longer loose (e.g. already on a student) are not listed twice
        return [f for f in loose if f["path"] not in assigned or f["assigned_to"]]

    def get_matches(self):
        self._need_folder()
        from grader.ingest import load_roster, scan_submissions  # local: keeps api import order simple
        roster = self._roster_path()
        found = scan_submissions(self._folder, load_roster(roster) if roster else None)
        self._apply_matching(found)
        m = self._load_matching()
        assigned_by_id: dict[str, list[str]] = {}
        for path_str, sid in m["assigned"].items():
            assigned_by_id.setdefault(sid, []).append(Path(path_str).name)
        teams = []
        for s in found:
            by_you = [n for n in assigned_by_id.get(s.student_id, []) if s.video and n == s.video.name]
            if s.notebook is None:
                status = "no_notebook"
            elif s.video is not None:
                status = "by_you" if by_you else "ok"
            elif s.student_id in m["no_video"]:
                status = "no_video"
            else:
                status = "needs"
            teams.append({
                "id": s.student_id, "name": s.student_name or s.student_id,
                "members": split_members(s.student_name, s.student_id),
                "notebook": s.notebook.name if s.notebook else None,
                "video": s.video.name if s.video else None,
                "status": status, "late": s.late,
                "flags": [f for f in s.flags if not f.startswith(("No video found",))],
            })
        needs = sum(t["status"] == "needs" for t in teams)
        return {"ok": True, "teams": teams, "unmatched": self._loose_files(), "needs": needs,
                "matched": sum(t["status"] in ("ok", "by_you") for t in teams)}

    def assign_file(self, path: str, student_id: str):
        """Give a loose file to a student ('' un-assigns it)."""
        self._need_folder()
        p = Path(path)
        if not p.is_file() or p.parent.resolve() != self._folder.resolve():
            return {"ok": False, "error": "That file isn't in the submissions folder."}
        m = self._load_matching()
        if student_id:
            m["assigned"][str(p)] = student_id
            if p.suffix.lower() in VIDEO_EXT and student_id in m["no_video"]:
                m["no_video"].remove(student_id)
        else:
            m["assigned"].pop(str(p), None)
        self._save_matching(m)
        if self._rubric is not None:
            self._scan()
        return self.get_matches()

    def set_no_video(self, student_id: str, value: bool = True):
        self._need_folder()
        m = self._load_matching()
        if value and student_id not in m["no_video"]:
            m["no_video"].append(student_id)
        if not value and student_id in m["no_video"]:
            m["no_video"].remove(student_id)
        self._save_matching(m)
        if self._rubric is not None:
            self._scan()
        return self.get_matches()

    # ------------------------------------------------------------ notebook checks
    def analyze_notebook(self, student_id: str):
        """Run the notebook parser on one submission and save what it found as 'needs your attention' flags."""
        rubric = self._need_rubric()
        from easygrade.pipeline.notebook.config import load_config
        from easygrade.pipeline.notebook.models import make_flag
        from easygrade.pipeline.notebook.names import filename_ok
        from easygrade.pipeline.notebook.parse import parse_notebook
        with self._store() as st:
            _, s = self._sub(st, student_id)
        if not s.notebook_path:
            return {"ok": True, "skipped": True, "flags": []}
        config = load_config()
        orig = original_name(Path(s.notebook_path).name)
        with tempfile.TemporaryDirectory() as tmp:  # chart images the parser extracts are not needed here
            result = parse_notebook(s.notebook_path, "team-" + re.sub(r"[^A-Za-z0-9_-]", "", student_id)[:20], tmp, config)
        # The header and file-name rules are the CAP3321C submission rules: only apply them to that rubric.
        # The parser saw the on-disk name (with the LMS prefix), so judge the student's own file name instead.
        cap = "CAP3321C" in rubric.assignment.upper()
        result.flags = [f for f in result.flags
                        if f.code != "FILENAME_RULES" and (cap or f.code not in ("HEADER_RULES", "NAME_NOT_FOUND"))]
        if cap and not filename_ok(orig, config):
            result.flags.append(make_flag("FILENAME_RULES"))
        flags = friendly_flags(result, orig, config)
        with self._store() as st:
            for f in flags:
                st.add_flag(s.id, f)
        return {"ok": True, "flags": flags, "names": [n.name for n in result.names]}

    # ------------------------------------------------------------ review list
    def review_rows(self) -> list[dict]:
        """One dict per student/team with everything the review list and the exports need."""
        rubric = self._need_rubric()
        rows = []
        with self._store() as st:
            aid, _ = st.get_assignment(rubric.assignment)
            for s in st.submissions(aid):
                sc = st.scores(s.id)
                criteria = []
                for c in rubric.criteria:
                    r = sc.get(c.id)
                    final = r["final_score"] if r else None
                    lvl = c.label_for(final)
                    criteria.append({
                        "id": c.id, "name": c.name, "source": c.source, "points": c.points,
                        "final": final, "ai_score": r["ai_score"] if r else None,
                        "level": lvl.label if lvl else None,
                        "reason": (r["ai_reason"] or "") if r else "",
                        "evidence": json.loads(r["evidence"] or "[]") if r else [],
                        "confidence": r["confidence"] if r else None,
                        "changed": bool(r and r["overridden"] and r["ai_score"] is not None),
                        "comment": (r["comment"] or "") if r else "",
                        "levels": [{"label": l.label, "score": l.score, "min": l.floor,
                                    "description": l.description} for l in c.levels],
                    })
                rows.append(self._row(s, criteria, rubric, st.total(s.id, rubric)))
        return rows

    def _row(self, s, criteria: list[dict], rubric, total) -> dict:
        scored = [c for c in criteria if c["final"] is not None]
        missing = [c for c in criteria if c["final"] is None]
        # The store's total is None until every criterion has a score; the list shows the points so far.
        total = total if total is not None else (sum(c["final"] for c in scored) if scored else None)
        check = []
        for c in missing:
            why = " (no video)" if c["source"] in ("video", "both") and not s.video_path else ""
            check.append(f"{c['name']} ({c['points']:g} pts) needs your score{why}")
        check += list(s.flags)
        for c in scored:
            if c["confidence"] is not None and c["confidence"] < LOW_CONFIDENCE and not c["changed"]:
                check.append(f"{c['name']}: the AI was only {round(c['confidence'] * 100)}% sure")
        ranked = sorted(scored, key=lambda c: c["final"] / c["points"], reverse=True)
        strongest = ranked[0] if ranked else None
        weakest = ranked[-1] if ranked else None
        changed_by = sum((c["final"] - c["ai_score"]) for c in scored if c["ai_score"] is not None and c["changed"])
        members = split_members(s.student_name, s.student_id)
        name = " & ".join(members) if members else s.student_id
        if not scored:
            overall = "Not graded yet."
        else:
            part = f"{name} scored {total:g} of {rubric.total_points:g}" if not missing else \
                f"{name} has {total:g} points so far, out of {rubric.total_points:g}"
            overall = part + f". Strongest: {strongest['name']}; weakest: {weakest['name']}."
            if missing:
                overall += f" {len(missing)} categor{'y' if len(missing) == 1 else 'ies'} still need{'s' if len(missing) == 1 else ''} your score."
        return {
            "id": s.student_id, "name": name, "members": members, "email": s.email,
            "status": s.status, "total": total, "points": rubric.total_points,
            "complete": not missing, "has_notebook": bool(s.notebook_path), "has_video": bool(s.video_path),
            "late": s.late, "flags": list(s.flags), "check": check,
            "ai": {"status": "not_checked", "signals": []},
            "overall": overall, "feedback": s.feedback or "",
            "strongest": {"name": strongest["name"], "score": strongest["final"], "max": strongest["points"]} if strongest else None,
            "weakest": {"name": weakest["name"], "score": weakest["final"], "max": weakest["points"]} if weakest else None,
            "changed_by": changed_by, "criteria": criteria,
        }

    def get_review(self):
        rubric = self._need_rubric()
        rows = self.review_rows()
        counts = {"approved": sum(r["status"] == "approved" for r in rows), "total": len(rows)}
        return {"ok": True, "rubric": rubric_summary(rubric), "rows": rows, "counts": counts,
                "ai_ready": bool(__import__("desktop.settings", fromlist=["load_settings"]).load_settings()["api_key"])}

    # ------------------------------------------------------------ guarded exports
    def export_review(self, kind: str = "excel"):
        """Write grades_review.xlsx (Grades, Details, Rubric) or grades.csv for the reviewed students only."""
        rubric = self._need_rubric()
        everyone = self.review_rows()
        rows = [r for r in everyone if r["status"] == "approved"]
        out = self._gdir
        left_out = len(everyone) - len(rows)
        if kind == "csv":
            res = rx.export_review_csv(rows, rubric, out / "grades.csv", out / "export_log.jsonl")
            return {"ok": True, "file": str(out / "grades.csv"), "folder": str(out), "teams": len(res["exported"]),
                    "rows": res["rows_written"], "refused": res["refused"], "left_out": left_out}
        res = rx.export_review_excel(rows, rubric, out / "grades_review.xlsx")
        return {"ok": True, "file": str(out / "grades_review.xlsx"), "folder": str(out), "teams": len(res["written"]),
                "rows": res["students"], "refused": res["refused"], "left_out": left_out}
