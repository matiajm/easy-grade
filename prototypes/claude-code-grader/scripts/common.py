"""Shared helpers for the EasyGrade scripts. Standard library only."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEVEL_NAMES = {"excellent": "Excellent", "good": "Good", "needs_work": "Needs Work"}


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text())


def load_rubric(config: dict | None = None) -> dict:
    config = config or load_config()
    return json.loads((ROOT / config["rubric"]).read_text())


def team_dirs(submissions_dir: str) -> list[Path]:
    """One folder per team submission. Matching a video to its notebook = same folder."""
    base = Path(submissions_dir)
    if not base.is_dir():
        raise SystemExit(f"Not a folder: {base}")
    dirs = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not dirs:
        raise SystemExit(f"No team folders in {base}. Put each team's notebook and video in its own folder.")
    return dirs


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
