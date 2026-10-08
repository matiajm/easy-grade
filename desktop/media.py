"""Tiny local web server so the app window can play student videos.

Why: the app window can't read arbitrary files from disk, and video players
need "range requests" to seek, which Python's built-in server doesn't do.

Safety: it listens on 127.0.0.1 only, and serves only files the app has
registered, under random tokens. Nothing else on disk is reachable.
"""
from __future__ import annotations

import mimetypes
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHUNK = 256 * 1024
TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
         ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo"}


class MediaServer:
    def __init__(self):
        self._files: dict[str, Path] = {}
        self._by_path: dict[str, str] = {}
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the console quiet
                pass

            def do_HEAD(self):
                self._serve(head=True)

            def do_GET(self):
                self._serve(head=False)

            def _serve(self, head: bool):
                m = re.fullmatch(r"/media/([A-Za-z0-9_-]+)", self.path.split("?")[0])
                path = server._files.get(m.group(1)) if m else None
                if path is None or not path.is_file():
                    self.send_error(404)
                    return
                size = path.stat().st_size
                ctype = TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                start, end = 0, size - 1
                rng = self.headers.get("Range")
                status = 200
                if rng:
                    rm = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
                    if not rm or (not rm.group(1) and not rm.group(2)):
                        self.send_error(416)
                        return
                    if rm.group(1):
                        start = int(rm.group(1))
                        end = int(rm.group(2)) if rm.group(2) else size - 1
                    else:  # suffix range: last N bytes
                        start = max(0, size - int(rm.group(2)))
                    end = min(end, size - 1)
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    status = 206
                length = end - start + 1 if size else 0
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if head or length == 0:
                    return
                try:
                    with path.open("rb") as f:
                        f.seek(start)
                        left = length
                        while left > 0:
                            buf = f.read(min(CHUNK, left))
                            if not buf:
                                break
                            self.wfile.write(buf)
                            left -= len(buf)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the player stopped reading (seek or close)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def url_for(self, path: str | Path) -> str:
        """Register a file and return the URL the video player should use."""
        p = Path(path).resolve()
        with self._lock:
            token = self._by_path.get(str(p))
            if token is None:
                token = secrets.token_urlsafe(12)
                self._files[token] = p
                self._by_path[str(p)] = token
        return f"http://127.0.0.1:{self.port}/media/{token}"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
