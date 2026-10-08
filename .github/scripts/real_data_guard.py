"""Fail if any notebook or video file exists outside the allowed fixture folders.

Usage: python real_data_guard.py [root]
"""
import sys
from pathlib import Path

BLOCKED = {".ipynb", ".mp4", ".mov", ".webm"}
# Fake data only. demo_output/ is the original synthetic demo set.
ALLOWED = ("easygrade/fixtures/", "demo_output/")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}


def find_violations(root: Path) -> list[str]:
    bad = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if SKIP_DIRS & set(rel.parts) or not p.is_file():
            continue
        if p.suffix.lower() in BLOCKED and not rel.as_posix().startswith(ALLOWED):
            bad.append(rel.as_posix())
    return sorted(bad)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    bad = find_violations(root)
    if bad:
        print("Real-data guard FAILED. Notebook/video files outside easygrade/fixtures/:")
        for b in bad:
            print(f"  {b}")
        return 1
    print("Real-data guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
