"""Generate batch B, the HOLD-OUT set (task 2.8): 10 FAKE finals with a different mix than batch A.

Run from the repo root:   python easygrade/fixtures/make_batch_b.py
Needs: nbformat, matplotlib (through make_batch_a.py, which holds the shared notebook builder).

HOLD-OUT: never use these to tune prompts. They exist to measure the grader on work it was not tuned on.

What differs from batch A
- Non-native-English writing style in 5 teams (group "non_native_english" in the key). The style is a
  synthetic approximation made by rule (dropped articles, verb-form and preposition slips); it is not based on any
  real student. Grammar slips must NOT lower a level and must NOT raise an AI-usage review.
- Partner-contribution cases: one partner credited with all the work and/or one speaker in the video.
- A different spread of quality, with some sections only partly checkable.

Writes easygrade/fixtures/batch_b/team-011 .. team-020 and easygrade/fixtures/batch_b/answer_key.json.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import nbformat

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_batch_a as base  # noqa: E402

OUT = Path(__file__).resolve().parent / "batch_b"
E, G, N = base.E, base.G, base.N

TEAMS = [
    dict(id="team-011", names=("Anika Rao", "Sebastian Wolfe"),
         levels=dict(data_cleaning=E, analysis_viz=E, interpretation=E, code_quality=G, presentation=E, collaboration=E),
         quirks=[]),
    dict(id="team-012", names=("Thiago Almeida", "Fatima Zahra"),
         levels=dict(data_cleaning=E, analysis_viz=G, interpretation=G, code_quality=E, presentation=G, collaboration=E),
         quirks=[], group="non_native_english"),
    dict(id="team-013", names=("Hiroshi Mori", "Elena Marquez"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=G, code_quality=G, presentation=G, collaboration=G),
         quirks=["leftover_cell"], group="non_native_english"),
    dict(id="team-014", names=("Brandon Cole", "Rosa Delgado"),
         levels=dict(data_cleaning=G, analysis_viz=E, interpretation=G, code_quality=G, presentation=N, collaboration=N),
         quirks=["lopsided", "one_speaker"],
         seeded=[dict(problem="one partner credited with all the work and the only speaker",
                      flag="PARTNER_CONTRIBUTION_UNCHECKABLE")]),
    dict(id="team-015", names=("Ewa Kowalski", "Mateo Fuentes"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=N, code_quality=G, presentation=G, collaboration=G),
         quirks=["no_summaries"], group="non_native_english"),
    dict(id="team-016", names=("Darnell Price", "Amira Nasser"),
         levels=dict(data_cleaning=E, analysis_viz=N, interpretation=N, code_quality=N, presentation=G, collaboration=G),
         quirks=["no_q3_q4", "out_of_order"],
         seeded=[dict(problem="cells run out of order", flag="EXEC_ORDER")]),
    dict(id="team-017", names=("Linh Tran", "Gustavo Pires"),
         levels=dict(data_cleaning=N, analysis_viz=N, interpretation=N, code_quality=N, presentation=N, collaboration=G),
         quirks=["error_cell", "one_speaker", "no_q3_q4"], group="non_native_english",
         seeded=[dict(problem="a cell stops with an error", flag="ERROR_OUTPUT")]),
    dict(id="team-018", names=("Camille Roy", "Kofi Asante"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=E, code_quality=E, presentation=E, collaboration=G),
         quirks=[]),
    dict(id="team-019", names=("Ivana Petrovic", "Noel Fraser"),
         levels=dict(data_cleaning=G, analysis_viz=G, interpretation=G, code_quality=N, presentation=G, collaboration=G),
         quirks=["out_of_order"], group="non_native_english",
         seeded=[dict(problem="cells run out of order", flag="EXEC_ORDER")]),
    dict(id="team-020", names=("Ravi Menon", "Julia Hartmann"),
         levels=dict(data_cleaning=E, analysis_viz=E, interpretation=G, code_quality=G, presentation=G, collaboration=N),
         quirks=["lopsided"],
         seeded=[dict(problem="responsibilities credit only one partner", flag="PARTNER_CONTRIBUTION_UNCHECKABLE")]),
]

# Rule-based approximation of non-native writing: (pattern, replacement, probability).
SLIPS = [
    (r"(?<=[a-z,] )the ", "", 0.45),
    (r"\bwe dropped\b", "we drop", 0.6),
    (r"\bWe dropped\b", "We drop", 0.6),
    (r"\bwere stored as\b", "was stored like", 0.7),
    (r"\bwe converted\b", "we did convert", 0.6),
    (r"\bhas the highest\b", "have the most high", 0.6),
    (r"\bremain\b", "are remaining", 0.7),
    (r"\bon average\b", "in average", 0.8),
    (r"\bin the\b", "on the", 0.25),
    (r"\bis only\b", "are only", 0.4),
    (r"\bwhich suggests\b", "this is suggesting", 0.8),
    (r"\bAverage scores\b", "Average of scores", 0.7),
    (r"\bThe chart shows\b", "The chart is showing", 0.8),
]


def non_native(text: str, rng: random.Random) -> str:
    for pattern, repl, prob in SLIPS:
        text = re.sub(pattern, lambda m: repl if rng.random() < prob else m.group(0), text)
    return text


def apply_style(book, transcript, rng):
    """Roughen the prose only: the header, headings and code are left alone, so every fact stays checkable."""
    for i, cell in enumerate(book.cells):
        if cell.cell_type == "markdown" and i > 0 and not cell.source.startswith("#"):
            cell.source = non_native(cell.source, rng)
    for seg in transcript["segments"]:
        seg["text"] = non_native(seg["text"], rng)


def main():
    key = {
        "description": "FAKE answer key for batch B (synthetic data, invented students). HOLD-OUT: never tune prompts on "
                       "this set. Used only by evals; never given to the model.",
        "holdout": True,
        "level_keys": base.LEVELS,
        "writing_style_note": "Teams in group non_native_english have synthetic grammar slips. Slips must not lower a "
                              "level and must not raise an AI-usage review.",
        "teams": {},
    }
    for idx, team in enumerate(TEAMS):
        rng = random.Random(9000 + idx)
        folder = OUT / team["id"]
        folder.mkdir(parents=True, exist_ok=True)
        book, _ = base.build_notebook(team, rng)
        transcript = base.build_transcript(team, rng)
        if team.get("group") == "non_native_english":
            apply_style(book, transcript, rng)
        book.number("out_of_order" in team["quirks"], rng)
        nb = nbformat.v4.new_notebook(cells=book.cells)
        nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
        nbformat.validate(nb)
        (folder / "final.ipynb").write_bytes(nbformat.writes(nb).encode("utf-8") + b"\n")
        (folder / "transcript.json").write_bytes((json.dumps(transcript, indent=2) + "\n").encode("utf-8"))
        entry = {"students": list(team["names"]), "planned_levels": team["levels"],
                 "seeded_problems": team.get("seeded", [])}
        if team.get("group"):
            entry["group"] = team["group"]
        key["teams"][team["id"]] = entry
    (OUT / "answer_key.json").write_bytes((json.dumps(key, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {len(TEAMS)} teams to {OUT}")


if __name__ == "__main__":
    main()
