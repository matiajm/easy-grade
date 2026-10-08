"""Throwaway nbformat spike (task 0.5). Reads notebooks as data only; never executes code.

Usage: python easygrade/spike/nbformat_spike.py OUT_DIR NOTEBOOK [NOTEBOOK ...]
Images are saved to OUT_DIR (do not commit).
"""
import base64
import ast
import re
import sys
from pathlib import Path

import nbformat

NAME_RE = re.compile(r"(?i)(?:names?|students?|team members?|by)\s*:?\**\s*:?\s*(.+)")


def text(src):
    return src if isinstance(src, str) else "".join(src)


def names_from_first_cell(nb):
    for i, c in enumerate(nb.cells[:3]):
        if c.cell_type != "markdown":
            continue
        for line in text(c.source).splitlines():
            m = NAME_RE.search(line.replace("**", ""))
            if m:
                return i, [n.strip() for n in re.split(r",|\band\b|&", m.group(1)) if n.strip()]
    return None, []


def main(out_dir, paths):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for p in map(Path, paths):
        nb = nbformat.read(str(p), as_version=4)
        print(f"== {p.name}: nbformat {nb.nbformat}.{nb.nbformat_minor}, {len(nb.cells)} cells")
        idx, names = names_from_first_cell(nb)
        print(f"   names: {names} (cell {idx})")
        counts, errors, images = [], [], 0
        for i, c in enumerate(nb.cells):
            if c.cell_type != "code":
                continue
            ec = c.get("execution_count")  # may be None / missing
            counts.append(ec)
            try:
                ast.parse(text(c.source))
                syntax_ok = True
            except SyntaxError:
                syntax_ok = False
            for o in c.get("outputs", []):
                if o.output_type == "error":
                    errors.append((i, o.ename, o.evalue))
                png = o.get("data", {}).get("image/png") if o.output_type in ("display_data", "execute_result") else None
                if png:
                    images += 1
                    if isinstance(png, list):
                        png = "".join(png)
                    f = out / f"{p.stem}_cell{i}_{images}.png"
                    f.write_bytes(base64.b64decode(png))
            if not syntax_ok:
                print(f"   cell {i}: syntax_ok=False")
        print(f"   execution_counts: {counts}")
        seen = [c for c in counts if c is not None]
        print(f"   in order: {seen == sorted(seen) and len(set(seen)) == len(seen)}; "
              f"unexecuted code cells: {counts.count(None)}")
        print(f"   errors: {errors}; images saved: {images}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
