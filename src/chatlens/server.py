"""Local HTTP server: the labelling page plus a three-route JSON API.

Binds to 127.0.0.1 only. Traces often contain customer conversations, so nothing here is
meant to be reachable from another machine.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from threading import Lock

from .store import clean_label, load_labels, save_labels


def make_handler(traces: list[dict], labels_path: Path):
    labels = load_labels(labels_path)
    ids = {t["id"] for t in traces}
    lock = Lock()
    page = resources.files("chatlens.static").joinpath("index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: object) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path == "/api/traces":
                return self._json(200, traces)
            if self.path == "/api/labels":
                with lock:
                    return self._json(200, list(labels.values()))
            return self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/api/labels":
                return self._json(404, {"error": "not found"})
            # Any web page can POST a plain form to 127.0.0.1. Requiring a JSON content type
            # forces a CORS preflight that this server never answers, and checking Origin
            # catches browsers that send one anyway.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "expected application/json"})
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if origin and origin.split("://", 1)[-1] != host:
                return self._json(403, {"error": "cross-origin request refused"})
            try:
                row = clean_label(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            except (ValueError, KeyError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            if row["trace"] not in ids:
                return self._json(400, {"error": "unknown trace"})
            with lock:
                labels[row["trace"]] = row
                save_labels(labels_path, labels)
            return self._json(200, row)

    return Handler


def serve(traces: list[dict], labels_path: Path, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(traces, labels_path))
