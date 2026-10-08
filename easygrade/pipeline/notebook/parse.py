"""Notebook parser, core (task 1.5): .ipynb -> notebook_cells.json.

The notebook is read as data with nbformat and is NEVER executed. Nothing here
imports, evals or runs notebook code; syntax is checked with ast.parse only.

This module builds cells, outputs, images and syntax_ok, then runs the checks
(checks.py) and the header/name/file-name rules (names.py) and raises flags.
"""
from __future__ import annotations

import ast
import base64
import binascii
import json
import re
from pathlib import Path
from typing import Optional, Union

import nbformat

from .checks import compute_checks
from .config import AssignmentConfig, load_config
from .models import (
    SCHEMA_VERSION,
    Cell,
    Checks,
    ExecutionOrder,
    Header,
    ImageRef,
    NotebookCells,
    Output,
    make_flag,
)
from .names import filename_ok, missing_header_fields, read_header

PRODUCED_BY = "parser@0.1.0"
IMAGE_MIMES = {"image/png": "png", "image/jpeg": "jpg"}
_TEAM_ID_OK = re.compile(r"^[A-Za-z0-9_\-]+$")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def _text(value) -> str:
    # nbformat normally gives str, but multiline MIME values can be lists.
    return "".join(value) if isinstance(value, list) else str(value)


def syntax_ok(source: str) -> Optional[bool]:
    """ast.parse the cell. IPython lines (!cmd, %magic) are neutralised first.

    Returns None for cells that are not Python (%%cell magics) or empty.
    """
    if not source.strip():
        return None
    lines = source.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    if first.lstrip().startswith("%%"):
        return None  # whole-cell magic (%%bash, %%writefile...): not Python
    cleaned = []
    for ln in lines:
        stripped = ln.lstrip()
        if stripped.startswith(("!", "%")):
            cleaned.append(ln[: len(ln) - len(stripped)] + "pass")
        else:
            cleaned.append(ln)
    try:
        ast.parse("\n".join(cleaned))
        return True
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False


def _save_image(data, ext: str, out_dir: Path, cell_index: int, n: int) -> Optional[str]:
    try:
        raw = base64.b64decode(_text(data), validate=False)
    except (binascii.Error, ValueError):
        return None
    if not raw:
        return None
    rel = f"images/cell_{cell_index:03d}_{n}.{ext}"
    path = out_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return rel


def _convert_output(out, cell_index: int, out_dir: Path, limit: int, image_count: list[int],
                    images: list[ImageRef]) -> list[Output]:
    """One nbformat output -> zero or more parser outputs (kind text/table/error/image)."""
    kind = out.get("output_type")
    if kind == "stream":
        return [Output(kind="text", text=_truncate(_text(out.get("text", "")), limit))]
    if kind == "error":
        msg = f"{out.get('ename', 'Error')}: {out.get('evalue', '')}"
        return [Output(kind="error", text=_truncate(msg, limit))]
    if kind not in ("display_data", "execute_result"):
        return []

    data = out.get("data", {})
    result: list[Output] = []
    for mime, ext in IMAGE_MIMES.items():
        if mime in data:
            ref = _save_image(data[mime], ext, out_dir, cell_index, image_count[0])
            if ref:
                image_count[0] += 1
                images.append(ImageRef(cell_index=cell_index, path=ref, mime=mime))
                result.append(Output(kind="image", image_ref=ref))
    if result:
        return result
    # Colab's intrinsic+json and other vendor types are ignored on purpose.
    html = _text(data["text/html"]) if "text/html" in data else ""
    plain = _text(data["text/plain"]) if "text/plain" in data else ""
    if "<table" in html.lower() and plain:
        return [Output(kind="table", text=_truncate(plain, limit))]
    if plain:
        return [Output(kind="text", text=_truncate(plain, limit))]
    return []


def read_notebook(path: Union[str, Path]):
    """Read as nbformat v4 data. Raises on unreadable files; never executes anything."""
    return nbformat.read(str(path), as_version=4)


def parse_notebook(path: Union[str, Path], team_id: str, out_dir: Union[str, Path],
                   config: Optional[AssignmentConfig] = None) -> NotebookCells:
    """Parse one notebook. Image files go under out_dir/images/. Never raises on bad input."""
    if not _TEAM_ID_OK.match(team_id):
        raise ValueError("team_id must be opaque ([A-Za-z0-9_-]+), never a student name")
    config = config or load_config()
    out_dir = Path(out_dir)

    # Neutral values for the unreadable case, where nothing could be checked.
    header = Header(found=False, fields={}, rules_ok=True)
    checks = Checks(
        empty=False,
        execution_order=ExecutionOrder(strictly_increasing=True),
    )

    try:
        nb = read_notebook(path)
    except Exception:  # bad JSON, wrong format, missing file: report, do not crash
        return NotebookCells(
            schema_version=SCHEMA_VERSION, team_id=team_id, produced_by=PRODUCED_BY,
            header=header, filename_ok=True, checks=checks,
            flags=[make_flag("NOTEBOOK_UNREADABLE")],
        )

    cells: list[Cell] = []
    images: list[ImageRef] = []
    image_count = [0]
    for index, c in enumerate(nb.cells):
        source = _text(c.get("source", ""))
        is_code = c.cell_type == "code"
        outputs: list[Output] = []
        if is_code:
            for out in c.get("outputs", []):
                outputs.extend(_convert_output(out, index, out_dir, config.max_output_chars,
                                               image_count, images))
        cells.append(Cell(
            index=index,
            cell_type=c.cell_type if c.cell_type in ("code", "markdown", "raw") else "raw",
            source=source,
            execution_count=c.get("execution_count") if is_code else None,
            outputs=outputs,
            has_error=any(o.kind == "error" for o in outputs),
            syntax_ok=syntax_ok(source) if is_code else None,
        ))

    checks = compute_checks(cells)
    header, names = read_header(cells, config)
    fname_ok = filename_ok(Path(path).name, config)

    flags = []
    if checks.empty:
        flags.append(make_flag("NOTEBOOK_EMPTY"))
    if not names:
        flags.append(make_flag("NAME_NOT_FOUND"))
    if not header.rules_ok:
        missing = ", ".join(missing_header_fields(header, config))
        flags.append(make_flag("HEADER_RULES", f"Header is missing required fields: {missing}."))
    if not fname_ok:
        flags.append(make_flag("FILENAME_RULES"))
    if not checks.execution_order.strictly_increasing or checks.execution_order.skipped:
        flags.append(make_flag("EXEC_ORDER"))
    if checks.error_cells:
        flags.append(make_flag("ERROR_OUTPUT"))

    # Colab/Jupyter notebook metadata is deliberately not copied: it can identify people.
    return NotebookCells(
        schema_version=SCHEMA_VERSION, team_id=team_id, produced_by=PRODUCED_BY,
        names=names, header=header, filename_ok=fname_ok, cells=cells, images=images,
        checks=checks, flags=flags,
    )


def write_notebook_cells(result: NotebookCells, out_dir: Union[str, Path]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "notebook_cells.json"
    p.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Parse a notebook into notebook_cells.json (no code is run)")
    ap.add_argument("notebook")
    ap.add_argument("out_dir")
    ap.add_argument("--team-id", default="team-000")
    a = ap.parse_args(argv)
    res = parse_notebook(a.notebook, a.team_id, a.out_dir)
    print(write_notebook_cells(res, a.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
