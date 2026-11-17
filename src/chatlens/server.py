"""Local HTTP server: the labelling page plus a three-route JSON API.

Binds to 127.0.0.1 only. Traces often contain customer conversations, so nothing here is
meant to be reachable from another machine, or from a web page in the same browser:

- every request must name this server in its Host header, which defeats DNS rebinding
  (a hostile page whose domain resolves to 127.0.0.1 can't read /api/traces);
- writes need a JSON content type and, when the browser sends one, a matching Origin;
- the page is served with a Content-Security-Policy that allows only its own inline
  script and style (by hash), so a conversation that contains HTML can't run code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from socketserver import TCPServer
from threading import Lock
from typing import cast

from .store import clean_label, load_labels, save_labels

MAX_BODY = 64 * 1024  # a label is a few hundred bytes
LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]"}


def _csp(page: bytes) -> str:
    """A policy that allows exactly the page's inline <script> and <style> blocks."""
    html = page.decode("utf-8")

    def digest(tag: str) -> str:
        body = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.S)
        if body is None:
            raise ValueError(f"index.html has no <{tag}> block")
        h = base64.b64encode(hashlib.sha256(body.group(1).encode()).digest()).decode()
        return f"'sha256-{h}'"

    return "; ".join(
        [
            "default-src 'none'",
            f"script-src {digest('script')}",
            f"style-src {digest('style')}",
            "connect-src 'self'",
            "img-src 'self'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )


def make_handler(traces: list[dict], labels_path: Path):
    labels = load_labels(labels_path)
    ids = {t["id"] for t in traces}
    lock = Lock()
    page = resources.files("chatlens.static").joinpath("index.html").read_bytes()
    csp = _csp(page)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy", csp)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: object) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def _host_ok(self) -> bool:
            host = self.headers.get("Host", "")
            name, _, port = host.rpartition(":")
            return name in LOCAL_NAMES and port == str(cast(HTTPServer, self.server).server_port)

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._json(403, {"error": "unexpected Host header"})
            if self.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path == "/api/traces":
                return self._json(200, traces)
            if self.path == "/api/labels":
                with lock:
                    return self._json(200, list(labels.values()))
            return self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                return self._json(403, {"error": "unexpected Host header"})
            if self.path != "/api/labels":
                return self._json(404, {"error": "not found"})
            # Any web page can POST a plain form to 127.0.0.1. Requiring a JSON content type
            # forces a CORS preflight that this server never answers, and checking Origin
            # catches browsers that send one anyway.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "expected application/json"})
            origin = self.headers.get("Origin")
            if origin and origin.split("://", 1)[-1] != self.headers.get("Host", ""):
                return self._json(403, {"error": "cross-origin request refused"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._json(411, {"error": "Content-Length required"})
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"error": f"a label must be under {MAX_BODY} bytes"})
            try:
                row = clean_label(json.loads(self.rfile.read(length)))
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                return self._json(400, {"error": str(e)})
            if row["trace"] not in ids:
                return self._json(400, {"error": "unknown trace"})
            with lock:
                labels[row["trace"]] = row
                save_labels(labels_path, labels)
            return self._json(200, row)

    return Handler


class LocalServer(ThreadingHTTPServer):
    """ThreadingHTTPServer without http.server's reverse-DNS lookup of the bind address,
    which runs before the socket listens and took about 35 seconds for 127.0.0.1 on a
    GitHub macOS runner. The page never uses the looked-up name."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), int(port)


def serve(traces: list[dict], labels_path: Path, port: int) -> ThreadingHTTPServer:
    return LocalServer(("127.0.0.1", port), make_handler(traces, labels_path))
