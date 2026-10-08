"""Command line for the grading loop.

    python -m grader rubric-template my_rubric.xlsx
    python -m grader add-rubric rubrics/project2_regression.json
    python -m grader ingest "Project 2 - Housing Price Regression" submissions/ --roster roster.csv
    python -m grader scores-template "Project 2 - ..." scores.csv
    python -m grader load-scores "Project 2 - ..." scores.csv
    python -m grader status "Project 2 - ..."
    python -m grader approve "Project 2 - ..." --all
    python -m grader export "Project 2 - ..." --xlsx out/grades.xlsx --csv out/gradebook.csv
    python -m grader demo demo_output/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import export as ex
from .ingest import load_roster, scan_submissions
from .rubric import RubricError, load_rubric, write_rubric_template
from .scoring import SimulatedGrader, load_manual_scores, parse_grader_output, write_scores_template, output_schema
from .store import GradeStore, StoreError

SAMPLE_RUBRIC = Path(__file__).resolve().parent.parent / "rubrics" / "project2_regression.json"


def cmd_rubric_template(a):
    example = load_rubric(SAMPLE_RUBRIC) if a.with_example else None
    write_rubric_template(a.path, example)
    print(f"Wrote rubric template to {a.path}")


def cmd_add_rubric(a):
    rubric = load_rubric(a.path, assignment=a.name)
    with GradeStore(a.db) as st:
        st.save_assignment(rubric, replace=a.replace)
    print(f"Saved '{rubric.assignment}': {len(rubric.criteria)} criteria, {rubric.total_points:g} points")
    for c in rubric.criteria:
        print(f"  {c.id:<22} {c.points:>5g} pts  [{c.source}]  {c.name}")


def cmd_schema(a):
    with GradeStore(a.db) as st:
        _, rubric = st.get_assignment(a.assignment)
    print(json.dumps(output_schema(rubric), indent=2))


def cmd_ingest(a):
    roster = load_roster(a.roster) if a.roster else None
    found = scan_submissions(a.folder, roster)
    with GradeStore(a.db) as st:
        aid, _ = st.get_assignment(a.assignment)
        for s in found:
            st.upsert_submission(aid, s.student_id, s.student_name, s.email,
                                 str(s.notebook) if s.notebook else None,
                                 str(s.video) if s.video else None, s.late, s.flags)
    flagged = [s for s in found if s.flags]
    print(f"Found {len(found)} students; {len(flagged)} with issues to check:")
    for s in flagged:
        print(f"  {s.student_id:<10} {s.student_name:<22} " + "; ".join(s.flags))


def cmd_scores_template(a):
    with GradeStore(a.db) as st:
        aid, rubric = st.get_assignment(a.assignment)
        students = [(s.student_id, s.student_name) for s in st.submissions(aid)]
    write_scores_template(a.path, rubric, students)
    print(f"Wrote scoring sheet for {len(students)} students to {a.path}")


def cmd_load_scores(a):
    with GradeStore(a.db) as st:
        aid, rubric = st.get_assignment(a.assignment)
        data = load_manual_scores(a.path, rubric)
        n = 0
        for sid, (scores, fb) in data.items():
            sub = st.submission(aid, sid)
            for cid, val in scores.items():
                st.override_score(sub.id, rubric, cid, val)
            if fb:
                st.set_feedback(sub.id, fb)
            n += 1
    print(f"Loaded scores for {n} students")


def cmd_status(a):
    with GradeStore(a.db) as st:
        aid, rubric = st.get_assignment(a.assignment)
        subs = st.submissions(aid)
        print(f"{rubric.assignment} — {len(subs)} students, {rubric.total_points:g} points")
        for s in subs:
            total = st.total(s.id, rubric)
            t = "—" if total is None else f"{total:g}"
            print(f"  {s.student_id:<10} {s.student_name:<22} {s.status:<9} {t:>5}  {'⚑ ' + str(len(s.flags)) if s.flags else ''}")


def cmd_approve(a):
    with GradeStore(a.db) as st:
        aid, rubric = st.get_assignment(a.assignment)
        targets = st.submissions(aid, status="graded") if a.all else [st.submission(aid, sid) for sid in a.student]
        ok, failed = 0, []
        for s in targets:
            try:
                st.approve(s.id, rubric)
                ok += 1
            except StoreError as e:
                failed.append(f"{s.student_id}: {e}")
    print(f"Approved {ok}")
    for f in failed:
        print("  skipped " + f)


def cmd_export(a):
    if not (a.xlsx or a.csv or a.feedback_dir):
        sys.exit("Choose at least one of --xlsx, --csv, --feedback-dir")
    with GradeStore(a.db) as st:
        if a.xlsx:
            print(ex.export_excel(st, a.assignment, a.xlsx))
        if a.csv:
            print(ex.export_gradebook_csv(st, a.assignment, a.csv, lms_template=a.lms_template,
                                          column=a.column, approved_only=not a.include_unapproved))
        if a.feedback_dir:
            n = ex.export_feedback_files(st, a.assignment, a.feedback_dir)
            print(f"{a.feedback_dir}: {n} feedback files")


# ---------------- demo ----------------
DEMO_STUDENTS = [  # fictional
    ("1001", "Ana Ruiz", "ana.ruiz@example.edu"),
    ("1002", "Marcus Bell", "marcus.bell@example.edu"),
    ("1003", "Priya Nair", "priya.nair@example.edu"),
    ("1004", "Diego Santos", "diego.santos@example.edu"),
    ("1005", "Hannah Cole", "hannah.cole@example.edu"),
    ("1006", "Jamal Price", "jamal.price@example.edu"),
    ("1007", "Sofia Moreno", "sofia.moreno@example.edu"),
    ("1008", "Kevin Tran", "kevin.tran@example.edu"),
    ("1009", "Lucia Ferreira", "lucia.ferreira@example.edu"),
    ("1010", "Owen Park", "owen.park@example.edu"),
]


def _fake_notebook(ran: bool = True) -> str:
    def code(src, out):
        return {"cell_type": "code", "execution_count": 1 if ran else None, "metadata": {},
                "source": [src], "outputs": ([{"output_type": "stream", "name": "stdout", "text": [out]}] if ran else [])}
    return json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Housing price regression"]},
            code("import pandas as pd\ndf = pd.read_csv('housing.csv')\nprint(df.shape)", "(545, 13)\n"),
            code("print(df.isna().sum().sum())", "0\n"),
        ],
    })


SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _sample_notebook(ran: bool = True) -> str:
    """The sample notebook from samples/ (real outputs and charts), or a tiny stand-in."""
    path = SAMPLES / "sample_project.ipynb"
    if not path.is_file():
        return _fake_notebook(ran)
    nb = json.loads(path.read_text(encoding="utf-8"))
    if not ran:
        for c in nb["cells"]:
            if c.get("cell_type") == "code":
                c["outputs"], c["execution_count"] = [], None
    return json.dumps(nb, indent=1)


def _write_video(path: Path) -> None:
    sample = SAMPLES / "sample_walkthrough.mp4"
    path.write_bytes(sample.read_bytes() if sample.is_file() else b"\x00" * 2048)


def build_demo_submissions(root: Path) -> Path:
    """Fake submissions folder mixing both layouts and common problems."""
    import shutil

    sub = root / "submissions"
    if sub.exists():
        shutil.rmtree(sub)  # start clean, including any _grading/ from the app
    sub.mkdir(parents=True)
    for i, (sid, name, _) in enumerate(DEMO_STUDENTS):
        slug = name.lower().replace(" ", "")
        if sid == "1010":
            continue  # submitted nothing
        if i % 2 == 0:  # per-student folder layout
            d = sub / sid
            d.mkdir(exist_ok=True)
            (d / "project2.ipynb").write_text(_sample_notebook(ran=sid != "1005"), encoding="utf-8")
            if sid == "1003":
                (d / "video_link.txt").write_text("https://drive.google.com/file/d/EXAMPLE/view", encoding="utf-8")
            else:
                _write_video(d / "walkthrough.mp4")
        else:  # flat LMS bulk-download layout
            late = "late_" if sid == "1004" else ""
            (sub / f"{slug}_{late}{sid}_88{sid}_Project2.ipynb").write_text(_sample_notebook(), encoding="utf-8")
            if sid != "1008":
                _write_video(sub / f"{slug}_{late}{sid}_88{sid}_walkthrough.mp4")
    roster_text = "student_id,student_name,email\n" + "\n".join(f"{s},{n},{e}" for s, n, e in DEMO_STUDENTS) + "\n"
    (root / "roster.csv").write_text(roster_text, encoding="utf-8")
    (sub / "roster.csv").write_text(roster_text, encoding="utf-8")  # the desktop app looks for it here
    # A fake LMS gradebook export to show filling the assignment column in place.
    lms = root / "lms_gradebook_export.csv"
    lines = ["Student,ID,SIS User ID,Section,Project 1 (4410),Project 2 - Housing Price Regression (4411)",
             "    Points Possible,,,,100,100"]
    lines += [f"\"{n}\",{30000 + int(s)},{s},DATA-2100,{80 + int(s) % 15}," for s, n, _ in DEMO_STUDENTS]
    lms.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sub


def cmd_sample_folder(a):
    sub = build_demo_submissions(Path(a.folder))
    print(f"Sample submissions written to {sub}")
    print(f"Open it in the app:  python app.py --folder \"{sub}\"")


def cmd_demo(a):
    out = Path(a.folder)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "grades.db"
    if db.exists():
        db.unlink()
    rubric = load_rubric(SAMPLE_RUBRIC)
    sub_dir = build_demo_submissions(out)
    write_rubric_template(out / "rubric_template.xlsx", rubric)

    with GradeStore(db) as st:
        aid = st.save_assignment(rubric)
        print(f"1. Rubric loaded: {rubric.assignment} ({rubric.total_points:g} pts, {len(rubric.criteria)} criteria)")

        found = scan_submissions(sub_dir, load_roster(out / "roster.csv"))
        for s in found:
            st.upsert_submission(aid, s.student_id, s.student_name, s.email,
                                 str(s.notebook) if s.notebook else None, str(s.video) if s.video else None,
                                 s.late, s.flags)
        print(f"2. Ingested {len(found)} students ({sum(bool(s.flags) for s in found)} with issues)")

        grader = SimulatedGrader()
        graded = 0
        for s in st.submissions(aid):
            if "Nothing submitted" in s.flags:
                continue
            raw = grader.grade(rubric, s.student_id, has_video=s.video_path is not None)
            results, feedback, flags = parse_grader_output(rubric, raw)
            st.record_ai_results(s.id, rubric, results, feedback)
            for f in flags:
                st.add_flag(s.id, f)
            graded += 1
        print(f"3. Graded {graded} submissions (simulated AI)")

        # Professor review: a few overrides, then approve everyone except two left for later.
        priya = st.submission(aid, "1003")
        st.set_feedback(priya.id, "Your notebook is graded. The video was a Drive link I couldn't open; "
                                  "upload the file itself and I'll grade the video criteria.")
        hannah = st.submission(aid, "1005")
        st.override_score(hannah.id, rubric, "code_quality", 3,
                          "Notebook was saved without outputs, so it was never run top to bottom.")
        marcus = st.submission(aid, "1002")
        st.override_score(marcus.id, rubric, "modeling", 20, "Residual plot in cell 8 covers this; full marks.")
        st.set_feedback(marcus.id, "Strong project, Marcus. Your residual analysis was the best in the class.")
        hold = {"1005", "1008"}
        for s in st.submissions(aid, status="graded"):
            if s.student_id not in hold:
                st.approve(s.id, rubric)
        print("4. Professor reviewed: 2 scores changed, 7 approved, 2 left for review")

        print("5. Export:")
        print("   " + str(ex.export_excel(st, rubric.assignment, out / "grades.xlsx")))
        print("   " + ex.export_gradebook_csv(st, rubric.assignment, out / "gradebook_simple.csv"))
        print("   " + ex.export_gradebook_csv(st, rubric.assignment, out / "gradebook_for_lms.csv",
                                             lms_template=out / "lms_gradebook_export.csv"))
        n = ex.export_feedback_files(st, rubric.assignment, out / "feedback")
        print(f"   {out / 'feedback'}: {n} feedback files")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="grader", description="Rubric-based grading for notebook + video projects.")
    p.add_argument("--db", default="grades.db", help="SQLite file that holds all grading data (default: grades.db)")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("rubric-template", help="Write an Excel rubric template to fill in")
    s.add_argument("path")
    s.add_argument("--with-example", action="store_true", help="Pre-fill with the sample rubric")
    s.set_defaults(fn=cmd_rubric_template)

    s = sp.add_parser("add-rubric", help="Load a rubric (.json/.xlsx/.csv) and create the assignment")
    s.add_argument("path")
    s.add_argument("--name", help="Assignment name (overrides the one in the file)")
    s.add_argument("--replace", action="store_true", help="Allow changing a rubric that already has scores")
    s.set_defaults(fn=cmd_add_rubric)

    s = sp.add_parser("schema", help="Print the JSON schema the AI grader must return")
    s.add_argument("assignment")
    s.set_defaults(fn=cmd_schema)

    s = sp.add_parser("ingest", help="Scan a submissions folder")
    s.add_argument("assignment")
    s.add_argument("folder")
    s.add_argument("--roster", help="CSV with student_id, student_name, email")
    s.set_defaults(fn=cmd_ingest)

    s = sp.add_parser("scores-template", help="Write a CSV for typing scores by hand")
    s.add_argument("assignment")
    s.add_argument("path")
    s.set_defaults(fn=cmd_scores_template)

    s = sp.add_parser("load-scores", help="Load hand-entered scores from CSV")
    s.add_argument("assignment")
    s.add_argument("path")
    s.set_defaults(fn=cmd_load_scores)

    s = sp.add_parser("status", help="Show grading progress")
    s.add_argument("assignment")
    s.set_defaults(fn=cmd_status)

    s = sp.add_parser("approve", help="Approve reviewed grades")
    s.add_argument("assignment")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Approve every graded submission")
    g.add_argument("--student", nargs="+", help="Student IDs to approve")
    s.set_defaults(fn=cmd_approve)

    s = sp.add_parser("export", help="Export grades")
    s.add_argument("assignment")
    s.add_argument("--xlsx", help="Excel workbook path")
    s.add_argument("--csv", help="Gradebook CSV path")
    s.add_argument("--lms-template", help="Gradebook CSV exported from the LMS; its assignment column is filled in")
    s.add_argument("--column", help="Exact assignment column header in the LMS file")
    s.add_argument("--include-unapproved", action="store_true", help="Put unapproved grades in the CSV too")
    s.add_argument("--feedback-dir", help="Folder for one feedback .txt per student")
    s.set_defaults(fn=cmd_export)

    s = sp.add_parser("sample-folder", help="Create a fake submissions folder to try the desktop app")
    s.add_argument("folder", nargs="?", default="sample_data")
    s.set_defaults(fn=cmd_sample_folder)

    s = sp.add_parser("demo", help="Run the whole loop on fake data")
    s.add_argument("folder", nargs="?", default="demo_output")
    s.set_defaults(fn=cmd_demo)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except (RubricError, StoreError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
