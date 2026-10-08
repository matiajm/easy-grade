"""Easy Grade desktop app.

    python app.py                                   # open the app
    python app.py --folder demo_output/submissions  # open straight into a folder
    python app.py --debug                           # right-click > Inspect for dev tools
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import webview

from desktop.api import Api
from desktop.media import MediaServer

# When packaged with PyInstaller, bundled files live in sys._MEIPASS.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Easy Grade")
    parser.add_argument("--folder", help="Submissions folder to open on start")
    parser.add_argument("--debug", action="store_true", help="Enable developer tools in the window")
    args = parser.parse_args()

    media = MediaServer()  # local-only server so the window can play student videos
    api = Api(media)
    if args.folder:
        result = api.open_folder(args.folder)
        if not result.get("ok"):
            print("Could not open folder:", result.get("error"), file=sys.stderr)

    window = webview.create_window(
        "Easy Grade",
        str(BASE / "ui" / "index.html"),
        js_api=api,
        width=1360,
        height=880,
        min_size=(1000, 680),
    )
    api._attach(window)
    webview.start(debug=args.debug)
    media.close()


if __name__ == "__main__":
    main()
