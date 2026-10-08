"""Shared helpers for the fixture-generator tests.

The generators draw charts with matplotlib, and PNG bytes can differ between operating systems and
matplotlib versions. So the tests regenerate into a temporary folder (never over the committed files)
and compare everything except the image bytes.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
needs_matplotlib = unittest.skipUnless(HAS_MATPLOTLIB, "matplotlib is needed to run the fixture generators")


def _strip_images(node):
    if isinstance(node, dict):
        return {k: ("<png>" if k == "image/png" else _strip_images(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_images(v) for v in node]
    return node


def snapshot(folder: Path, prefix: str = "") -> dict:
    """relative path -> comparable content (notebooks without their image payloads).
    prefix limits the comparison to team folders, so a committed README does not count."""
    out = {}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if not rel.startswith(prefix):
            continue
        if path.suffix == ".ipynb":
            out[rel] = json.dumps(_strip_images(json.loads(path.read_text(encoding="utf-8"))), sort_keys=True)
        elif path.suffix == ".png":
            out[rel] = path.read_bytes()[:8]  # only the PNG signature
        else:
            out[rel] = path.read_bytes().replace(b"\r\n", b"\n")
    return out


class generated_into:
    """Context manager: run fixtures/<script> --out TMP and yield TMP."""

    def __init__(self, script: str):
        self.script = script

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        out = Path(self._tmp.name)
        subprocess.run([sys.executable, str(ROOT / "easygrade" / "fixtures" / self.script), "--out", str(out)],
                       check=True, capture_output=True)
        return out

    def __exit__(self, *exc):
        self._tmp.cleanup()


def same_text(a: Path, b: Path) -> bool:
    """True if two text files match, ignoring line-ending differences."""
    return a.read_bytes().splitlines() == b.read_bytes().splitlines()
