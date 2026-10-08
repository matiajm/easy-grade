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
    # The notebook checks, the sample folder and the guarded exports use the easygrade package and its data.
    "--collect-submodules=easygrade",
    f"--add-data=easygrade/config{sep}easygrade/config",
    f"--add-data=easygrade/fixtures/batch_a{sep}easygrade/fixtures/batch_a",
    f"--add-data=easygrade/eval/answer_key.json{sep}easygrade/eval",
]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "app.easygrade.desktop"]

PyInstaller.__main__.run(args)
