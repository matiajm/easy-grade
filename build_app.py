"""Build the double-clickable app with PyInstaller.

    pip install -r requirements-dev.txt
    python build_app.py

Result:
    macOS:   dist/Easy Grade.app
    Windows: dist/Easy Grade/Easy Grade.exe

Build on each operating system you want to support: a Mac build only runs on Macs,
a Windows build only on Windows.
"""
import os
import sys

import PyInstaller.__main__

sep = os.pathsep  # ":" on macOS/Linux, ";" on Windows

args = [
    "app.py",
    "--name", "Easy Grade",
    "--windowed",          # no terminal window
    "--noconfirm",
    "--clean",
    f"--add-data=ui{sep}ui",
    f"--add-data=rubrics{sep}rubrics",
    f"--add-data=samples{sep}samples",
]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "app.easygrade.desktop"]

PyInstaller.__main__.run(args)
