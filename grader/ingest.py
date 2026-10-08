"""Find each student's notebook and video in a submissions folder.

Supported layouts:
  1. One subfolder per student:      submissions/<student_id>/project.ipynb, walkthrough.mp4
  2. Flat LMS bulk download:         submissions/<name>_<userid>_<subid>_<original file>
     (Canvas-style naming; a 'late' segment marks late work)

An optional roster CSV (student_id, student_name, email) fills in names and
reports students who submitted nothing.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

NOTEBOOK_EXT = {".ipynb"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
LINK_EXT = {".url", ".webloc", ".txt"}
LINK_RE = re.compile(r"https?://\S+", re.I)
# name_userid_submissionid_original  or  name_LATE_userid_submissionid_original
FLAT_RE = re.compile(r"^(?P<name>[a-z0-9\-]+)_(?P<late>late_)?(?P<uid>\d+)_(?P<sid>\d+)_(?P<orig>.+)$", re.I)


@dataclass
class FoundSubmission:
    student_id: str
    student_name: str = ""
    email: str = ""
    notebook: Path | None = None
    video: Path | None = None
    late: bool = False
    flags: list[str] = field(default_factory=list)
    _notebooks: list[Path] = field(default_factory=list, repr=False)
    _videos: list[Path] = field(default_factory=list, repr=False)
    _links: list[str] = field(default_factory=list, repr=False)

    def finalize(self) -> "FoundSubmission":
        nbs = sorted(self._notebooks)
        vids = sorted(self._videos, key=lambda p: p.stat().st_size, reverse=True)
        if not nbs and not vids and not self._links:
            self.flags.append("Nothing submitted")
            return self
        if not nbs:
            self.flags.append("No notebook (.ipynb) found")
        else:
            self.notebook = nbs[0]
            if len(nbs) > 1:
                self.flags.append(f"{len(nbs)} notebooks submitted; using {nbs[0].name}")
            problem = check_notebook(self.notebook)
            if problem:
                self.flags.append(problem)
        if vids:
            self.video = vids[0]
            if self.video.stat().st_size == 0:
                self.flags.append("Video file is empty")
            if len(vids) > 1:
                self.flags.append(f"{len(vids)} videos submitted; using the largest ({vids[0].name})")
        elif self._links:
            self.flags.append("Video submitted as a link — download it before video grading: " + self._links[0])
        else:
            self.flags.append("No video found")
        if self.late:
            self.flags.append("Submitted late")
        return self


def check_notebook(path: Path) -> str | None:
    """Return a problem description, or None if the notebook looks usable."""
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"{path.name} is not a valid notebook file"
    cells = nb.get("cells", [])
    code = [c for c in cells if c.get("cell_type") == "code" and "".join(c.get("source", [])).strip()]
    if not code:
        return f"{path.name} has no code cells"
    if not any(c.get("outputs") for c in code):
        return f"{path.name} was saved without outputs (cells were never run)"
    return None


def _links_in(path: Path) -> list[str]:
    try:
        return LINK_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []


def _add_file(sub: FoundSubmission, f: Path) -> None:
    ext = f.suffix.lower()
    if ext in NOTEBOOK_EXT:
        sub._notebooks.append(f)
    elif ext in VIDEO_EXT:
        sub._videos.append(f)
    elif ext in LINK_EXT:
        sub._links.extend(_links_in(f))


def load_roster(path: str | Path) -> dict[str, dict]:
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    roster = {}
    for r in rows:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
        sid = r.get("student_id") or r.get("id")
        if sid:
            roster[sid] = {"student_name": r.get("student_name") or r.get("name", ""), "email": r.get("email", "")}
    return roster


def scan_submissions(folder: str | Path, roster: dict[str, dict] | None = None) -> list[FoundSubmission]:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Submissions folder not found: {folder}")
    found: dict[str, FoundSubmission] = {}

    for entry in sorted(folder.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            sub = found.setdefault(entry.name, FoundSubmission(student_id=entry.name))
            for f in sorted(entry.rglob("*")):
                if f.is_file() and not f.name.startswith("."):
                    _add_file(sub, f)
        elif entry.is_file():
            m = FLAT_RE.match(entry.name)
            if not m:
                continue
            uid = m.group("uid")
            sub = found.setdefault(uid, FoundSubmission(student_id=uid, student_name=m.group("name")))
            sub.late = sub.late or bool(m.group("late"))
            _add_file(sub, entry)

    roster = roster or {}
    for sid, info in roster.items():
        if sid in found:
            found[sid].student_name = info["student_name"] or found[sid].student_name
            found[sid].email = info["email"]
        else:
            s = FoundSubmission(student_id=sid, student_name=info["student_name"], email=info["email"])
            found[sid] = s
    for sid, s in found.items():
        if roster and sid not in roster:
            s.flags.append("Not on the roster")
    return sorted((s.finalize() for s in found.values()), key=lambda s: (s.student_name.lower(), s.student_id))
