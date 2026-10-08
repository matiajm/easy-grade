"""Run the app's screen in a normal browser, against the real Python backend (for development and tests).

    python -m desktop.devserver               # then open http://127.0.0.1:8765/
    python -m desktop.devserver --port 9000

The page is ui/index.html with a small bridge (ui/dev_bridge.js) in place of pywebview: each
window.pywebview.api.<method>(...) call becomes POST /api/<method> with the arguments as a JSON list.
File dialogs can't open here, so they answer from a queue you fill with POST /__dialog
{"kind": "folder"|"open"|"save", "value": "<path>"}; a dialog with nothing queued counts as cancelled.
Local use only: it binds to 127.0.0.1.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import Api
from .media import MediaServer

UI = Path(__file__).resolve().parent.parent / "ui"


class DevApi(Api):
    """Api whose file dialogs answer from a queue instead of opening a window."""

    def __init__(self, media=None, sample_root=None):
        super().__init__(media)
        self.dialogs: dict[str, list[str]] = {}
        self.sample_root = sample_root  # where "Use the sample folder" writes (default: the home folder)

    def _dialog(self, kind: str, **kw):
        queue = self.dialogs.get(kind) or []
        return queue.pop(0) if queue else None


def make_handler(api: DevApi):
    lock = threading.Lock()  # the app serves one window; keep calls in order like pywebview mostly does

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                html = (UI / "index.html").read_text(encoding="utf-8")
                html = html.replace("<script>\n(function () {", '<script src="/dev_bridge.js"></script>\n<script>\n(function () {', 1)
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/dev_bridge.js":
                return self._send(200, (UI / "dev_bridge.js").read_bytes(), "application/javascript")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"[]"
            try:
                payload = json.loads(raw or b"[]")
            except ValueError:
                return self._send(400, b'{"ok": false, "error": "bad request"}', "application/json")
            if self.path == "/__dialog":
                api.dialogs.setdefault(payload["kind"], []).append(payload["value"])
                return self._send(200, b'{"ok": true}', "application/json")
            name = self.path.removeprefix("/api/")
            method = getattr(api, name, None)
            if name.startswith("_") or not callable(method):
                return self._send(404, b'{"ok": false, "error": "unknown method"}', "application/json")
            with lock:
                result = method(*payload)
            self._send(200, json.dumps(result).encode("utf-8"), "application/json")

    return Handler


def serve(port: int = 8765, sample_root=None):
    media = MediaServer()
    api = DevApi(media, sample_root)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api))
    return server, api, media


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    server, _, media = serve(a.port)
    print(f"EasyGrade dev server: http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        media.close()


if __name__ == "__main__":
    main()
