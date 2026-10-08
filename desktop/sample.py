"""Build a sample submissions folder from the fake batch A fixtures, in the layout Canvas produces.

Used by "Use the sample folder" on the start screen and by `python -m grader cap-sample-folder`.
Everything is invented (students, notebooks, transcripts). The only video is the app's own
samples/sample_walkthrough.mp4, copied under several names so video playback can be tried.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH_A = ROOT / "easygrade" / "fixtures" / "batch_a"
KEY = ROOT / "easygrade" / "eval" / "answer_key.json"
SAMPLE_VIDEO = ROOT / "samples" / "sample_walkthrough.mp4"

# Teams that did not send a video. team-006 also gets its notebook under the wrong file name.
NO_VIDEO = {"team-005", "team-007", "team-010"}
WRONG_NAME = {"team-004": "tomas-grace final.ipynb"}
# A video whose file name names no student: the match screen asks who it belongs to.
LOOSE_VIDEO = "IMG_4821.MOV"
LOOSE_FOR = "team-005"


def _slug(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch == "-")


def create_sample_folder(dest: str | Path) -> Path:
    """Write <dest>/submissions (flat Canvas names) and <dest>/submissions/roster.csv. Returns the folder."""
    dest = Path(dest)
    folder = dest / "submissions"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    teams = json.loads(KEY.read_text(encoding="utf-8"))["teams"]
    roster = []
    for i, (team, entry) in enumerate(sorted(teams.items()), start=1):
        uid, sid = 1100 + i, 88100 + i
        first, second = entry["students"]
        last1, last2 = first.split()[-1], second.split()[-1]
        prefix = f"{_slug(last1)}_{uid}_{sid}_"
        roster.append({"student_id": str(uid), "student_name": f"{first} & {second}", "email": ""})
        notebook = BATCH_A / team / "final.ipynb"
        if notebook.exists():
            orig = WRONG_NAME.get(team, f"{last1}_{last2}_FinalProject.ipynb")
            shutil.copyfile(notebook, folder / (prefix + orig))
        if team not in NO_VIDEO and SAMPLE_VIDEO.exists():
            shutil.copyfile(SAMPLE_VIDEO, folder / (prefix + "presentation.mp4"))
    if SAMPLE_VIDEO.exists():
        shutil.copyfile(SAMPLE_VIDEO, folder / LOOSE_VIDEO)
    with (folder / "roster.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "student_name", "email"], lineterminator="\n")
        w.writeheader()
        w.writerows(roster)
    return folder
