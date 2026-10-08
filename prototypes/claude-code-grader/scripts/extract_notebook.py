"""Step 2: turn each notebook into text Claude can read, and run the plain-code checks.

Notebooks are read as data only. Student code is never executed.

Usage:  .venv/bin/python scripts/extract_notebook.py submissions/
Writes, per team, into work/<team>/:
  notebook.md          cells, outputs and errors as text (names replaced with Student A, B, ...)
  images/              chart images saved from the notebook outputs
  transcript.md        the transcript with names replaced (if transcribe.py ran first)
  facts.json           results of the code checks: file name, header, execution order, errors, recording length
  private_names.json   real names for the spreadsheet. Claude must never read this file.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

from common import ROOT, load_config, read_json, team_dirs, write_json

MAX_OUTPUT_CHARS = 1500
HEADER_LINE = re.compile(r"^\s*\*\*\s*([A-Za-z ]+?)\s*:?\s*\*\*\s*:?\s*(.*)$")


def text_of(value) -> str:
    return "".join(value) if isinstance(value, list) else (value or "")


def parse_header(cells: list[dict], wanted: list[str]) -> dict:
    """Header = the first Markdown cell, with lines like **Students:** Ana Rivera, Marcus Chen."""
    first_md = next((c for c in cells if c.get("cell_type") == "markdown"), None)
    found = {}
    if first_md:
        for line in text_of(first_md.get("source")).splitlines():
            m = HEADER_LINE.match(line)
            if not m:
                continue
            key = m.group(1).strip().lower()
            for field in wanted:
                if key == field.lower() and m.group(2).strip():
                    found[field] = m.group(2).strip()
    return found


def split_names(students: str) -> list[str]:
    parts = re.split(r",|&|\band\b", students)
    return [p.strip() for p in parts if p.strip()]


def build_redactor(names: list[str]):
    """Replace full names, then first and last names, with Student A, Student B, ..."""
    labels = {}
    patterns = []
    for i, full in enumerate(names):
        label = f"Student {chr(ord('A') + i)}"
        labels[label] = full
        patterns.append((full, label))
    for i, full in enumerate(names):
        label = f"Student {chr(ord('A') + i)}"
        for part in full.split():
            if len(part) >= 3:
                patterns.append((part, label))

    def redact(text: str) -> str:
        for name, label in patterns:
            text = re.sub(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", label, text, flags=re.IGNORECASE)
        return text

    return redact, labels


def render_outputs(cell: dict, cell_no: int, images_dir: Path, team_dir: Path) -> tuple[list[str], list[dict], list[str]]:
    lines, errors, images = [], [], []
    for k, out in enumerate(cell.get("outputs", []), start=1):
        kind = out.get("output_type")
        if kind == "stream":
            lines.append("Output:\n````\n" + text_of(out.get("text"))[:MAX_OUTPUT_CHARS] + "\n````")
        elif kind in ("execute_result", "display_data"):
            data = out.get("data", {})
            if "image/png" in data:
                images_dir.mkdir(parents=True, exist_ok=True)
                path = images_dir / f"cell{cell_no}_{k}.png"
                path.write_bytes(base64.b64decode(text_of(data["image/png"])))
                rel = path.relative_to(team_dir).as_posix()
                images.append(rel)
                lines.append(f"[Chart image saved: {rel}]")
            elif "text/plain" in data:
                lines.append("Output:\n````\n" + text_of(data["text/plain"])[:MAX_OUTPUT_CHARS] + "\n````")
        elif kind == "error":
            errors.append({"cell": cell_no, "ename": out.get("ename", ""), "evalue": out.get("evalue", "")})
            lines.append(f"ERROR in cell {cell_no}: {out.get('ename', '')}: {out.get('evalue', '')}")
    return lines, errors, images


def execution_issues(code_cells: list[tuple[int, dict]]) -> list[str]:
    issues, run_counts = [], []
    for cell_no, cell in code_cells:
        count = cell.get("execution_count")
        has_output = bool(cell.get("outputs"))
        if count is None and has_output:
            issues.append(f"Cell {cell_no} has output but no execution count (output may be pasted, or the kernel was restarted)")
        elif count is None and text_of(cell.get("source")).strip():
            issues.append(f"Cell {cell_no} was never run")
        if count is not None:
            run_counts.append(count)
    if any(b <= a for a, b in zip(run_counts, run_counts[1:])):
        issues.append(f"Cells were run out of order (execution counts in notebook order: {run_counts})")
    return issues


def process_team(team: Path, work: Path, config: dict) -> None:
    out = work / team.name
    out.mkdir(parents=True, exist_ok=True)
    notebooks = sorted(team.glob("*.ipynb"))
    media = read_json(out / "media.json", default=None)
    rule_flags = []

    if not notebooks:
        rule_flags.append("No notebook found")
        write_json(out / "facts.json", {"team": team.name, "notebook_found": False, "rule_flags": rule_flags, "media": media})
        write_json(out / "private_names.json", {"notebook_file": None, "students": [], "labels": {}})
        print(f"{team.name}: no notebook")
        return
    if len(notebooks) > 1:
        rule_flags.append(f"{len(notebooks)} notebooks in the folder; graded {notebooks[0].name}")
    nb_path = notebooks[0]

    try:
        nb = json.loads(nb_path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rule_flags.append(f"Notebook could not be read: {e}")
        write_json(out / "facts.json", {"team": team.name, "notebook_found": True, "notebook_readable": False, "rule_flags": rule_flags, "media": media})
        write_json(out / "private_names.json", {"notebook_file": nb_path.name, "students": [], "labels": {}})
        print(f"{team.name}: unreadable notebook")
        return

    cells = nb.get("cells", [])
    header = parse_header(cells, config["header_fields"])
    students = split_names(header.get("Students", ""))
    if config.get("redact_names", True) and students:
        redact, labels = build_redactor(students)
    else:
        redact, labels = (lambda t: t), {}

    filename_ok = bool(re.match(config["filename_pattern"], nb_path.name))
    missing = [f for f in config["header_fields"] if f not in header]
    if not filename_ok:
        rule_flags.append("File name does not follow the convention Lastname1_Lastname2_FinalProject.ipynb")
    if missing:
        rule_flags.append("Header missing: " + ", ".join(missing))
    if not students:
        rule_flags.append("No student names found in the header")

    images_dir = out / "images"
    md, all_errors, all_images, code_cells = [], [], [], []
    md_count = 0
    for i, cell in enumerate(cells, start=1):
        kind = cell.get("cell_type")
        source = redact(text_of(cell.get("source")))
        if kind == "markdown":
            md_count += 1
            md.append(f"## Cell {i} · markdown\n\n{source}\n")
        elif kind == "code":
            code_cells.append((i, cell))
            count = cell.get("execution_count")
            md.append(f"## Cell {i} · code · execution count {count if count is not None else 'none'}\n\n````python\n{source}\n````")
            lines, errors, images = render_outputs(cell, i, images_dir, out)
            md.extend(redact(line) for line in lines)
            all_errors.extend(errors)
            all_images.extend(images)
            md.append("")

    issues = execution_issues(code_cells)
    if not code_cells:
        rule_flags.append("Notebook has no code cells")
    if all_errors:
        rule_flags.append(f"{len(all_errors)} error output(s) in the notebook: "
                          + "; ".join(f"cell {e['cell']} {e['ename']}" for e in all_errors))
    rule_flags.extend(issues)

    if media is None:
        rule_flags.append("No transcript: transcribe.py has not run for this team")
    elif media.get("media_file") is None:
        rule_flags.append("No video or audio file found")
    else:
        if media.get("over_time_limit"):
            rule_flags.append(f"Presentation is {media['duration_seconds']} s, over the {media['time_limit_minutes']}-minute limit")
        if media.get("low_confidence_at"):
            rule_flags.append("Low-confidence audio at " + ", ".join(media["low_confidence_at"]) + " (check the recording)")

    title = (f"# Notebook for {team.name}\n\n"
             f"{len(code_cells)} code cells, {md_count} Markdown cells, {len(all_images)} chart images. "
             "Student code was not run; outputs are as saved by the students.\n\n")
    (out / "notebook.md").write_text(title + "\n".join(md) + "\n")

    raw_transcript = out / "transcript_raw.md"
    if raw_transcript.exists():
        (out / "transcript.md").write_text(redact(raw_transcript.read_text()))

    write_json(out / "facts.json", {
        "team": team.name,
        "notebook_found": True,
        "notebook_readable": True,
        "notebook_file_redacted": redact(nb_path.name),
        "filename_ok": filename_ok,
        "header_fields_found": sorted(header),
        "header_missing": missing,
        "students_count": len(students),
        "student_labels": sorted(labels),
        "responsibilities": redact(header.get("Responsibilities", "")),
        "section": header.get("Section", ""),
        "code_cells": len(code_cells),
        "markdown_cells": md_count,
        "execution_counts": [c.get("execution_count") for _, c in code_cells],
        "execution_issues": issues,
        "errors": all_errors,
        "images": all_images,
        "media": media,
        "transcript_found": raw_transcript.exists(),
        "rule_flags": rule_flags,
    })
    write_json(out / "private_names.json", {"notebook_file": nb_path.name, "students": students, "labels": labels})
    print(f"{team.name}: {len(code_cells)} code cells, {len(all_images)} charts, {len(rule_flags)} rule flags")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract notebooks to text and run the plain-code checks.")
    parser.add_argument("submissions", help="folder with one subfolder per team")
    parser.add_argument("--work", default=str(ROOT / "work"))
    args = parser.parse_args()
    config = load_config()
    for team in team_dirs(args.submissions):
        process_team(team, Path(args.work), config)


if __name__ == "__main__":
    main()
