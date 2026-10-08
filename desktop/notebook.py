"""Turn an .ipynb file into simple cell data the UI can display.

Only plain text and PNG/JPEG images are passed through. HTML outputs (like
pandas tables) fall back to their text version, so nothing from a student's
notebook is ever injected into the page as HTML.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MAX_TEXT = 6000


def _text(v) -> str:
    return "".join(v) if isinstance(v, list) else str(v or "")


def _clip(s: str) -> str:
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + f"\n… ({len(s) - MAX_TEXT:,} more characters)"


def _outputs(cell: dict) -> list[dict]:
    out = []
    for o in cell.get("outputs", []):
        kind = o.get("output_type")
        if kind == "stream":
            out.append({"kind": "text", "text": _clip(_text(o.get("text")))})
        elif kind in ("execute_result", "display_data"):
            data = o.get("data", {})
            for mime in ("image/png", "image/jpeg"):
                if mime in data:
                    b64 = _text(data[mime]).replace("\n", "").strip()
                    out.append({"kind": "image", "src": f"data:{mime};base64,{b64}"})
                    break
            else:
                if "text/plain" in data:
                    out.append({"kind": "text", "text": _clip(_text(data["text/plain"]))})
        elif kind == "error":
            tb = "\n".join(o.get("traceback", [])) or f"{o.get('ename')}: {o.get('evalue')}"
            out.append({"kind": "error", "text": _clip(ANSI.sub("", tb))})
    return out


def read_notebook(path: str | Path) -> dict:
    """Return {"cells": [...], "error": None} or {"cells": [], "error": "..."}.

    Each cell: {"n": position (1-based), "type": "code"|"markdown", "count": execution count,
    "source": str, "outputs": [{"kind": "text"|"image"|"error", ...}]}
    "cell 7" in grader evidence means position 7 in this list.
    """
    try:
        nb = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cells": [], "error": "The notebook file is missing."}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"cells": [], "error": "This file isn't a readable notebook."}
    cells = []
    for i, c in enumerate(nb.get("cells", []), start=1):
        ctype = c.get("cell_type", "code")
        cells.append({
            "n": i,
            "type": "markdown" if ctype == "markdown" else ("code" if ctype == "code" else "raw"),
            "count": c.get("execution_count"),
            "source": _clip(_text(c.get("source"))),
            "outputs": _outputs(c) if ctype == "code" else [],
        })
    return {"cells": cells, "error": None}
