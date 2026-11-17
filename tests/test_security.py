"""The server is local-only, but a browser is a shared environment: any open tab can send
requests to 127.0.0.1. These tests attack it the way a hostile page would."""

import base64
import hashlib
import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from chatlens.cli import main
from chatlens.server import serve
from chatlens.store import TraceError, load_labels, load_traces

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def server(tmp_path):
    httpd = serve(load_traces(EXAMPLES / "traces.jsonl"), tmp_path / "labels.jsonl", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def request(port, method, path, body=b"", headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    for k, v in (headers or {}).items():
        conn.putheader(k, v)
    if body:
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders(body or None)
    r = conn.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    conn.close()
    return out


def test_dns_rebinding_cannot_read_conversations(server):
    """A page on evil.example whose DNS now points at 127.0.0.1 sends Host: evil.example."""
    assert request(server, "GET", "/api/traces")[0] == 200
    assert request(server, "GET", "/api/traces", host=f"localhost:{server}")[0] == 200
    for host in (f"evil.example:{server}", "127.0.0.1", f"127.0.0.1:{server + 1}"):
        assert request(server, "GET", "/api/traces", host=host)[0] == 403, host
        assert request(server, "GET", "/", host=host)[0] == 403, host


def test_writes_are_bounded_and_validated(server):
    json_ct = {"Content-Type": "application/json"}
    big = json.dumps({"trace": "x", "verdict": "fail", "note": "a" * 100_000}).encode()
    assert request(server, "POST", "/api/labels", big, json_ct)[0] == 413
    assert request(server, "POST", "/api/labels", headers=json_ct)[0] == 411
    for body in (b"[1, 2]", b'{"trace": 1, "verdict": "fail", "codes": "abc"}', b"\xff"):
        assert request(server, "POST", "/api/labels", body, json_ct)[0] == 400, body


def test_page_carries_a_strict_csp_matching_its_inline_script(server):
    status, headers, page = request(server, "GET", "/")
    assert status == 200
    csp = headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in csp and "frame-ancestors 'none'" in csp
    script = re.search(rb"<script>(.*?)</script>", page, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script).digest()).decode()
    assert f"'sha256-{digest}'" in csp
    api = request(server, "GET", "/api/labels")[1]
    assert api["X-Content-Type-Options"] == "nosniff"


def test_damaged_labels_file_stops_the_load(tmp_path):
    """Regression: a half-written line used to crash with a bare JSONDecodeError, and a
    line without "trace" with a KeyError."""
    p = tmp_path / "labels.jsonl"
    p.write_text('{"trace": "a", "verdict": "pass"}\n{"trace": "b", "verd\n', encoding="utf-8")
    with pytest.raises(TraceError, match=r"labels.jsonl:2"):
        load_labels(p)


def test_traces_are_normalised_or_rejected(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        '﻿{"id": 7, "turns": [{"role": "agent", "text": {"type": "template"}, "at": 0}]}\n',
        encoding="utf-8",
    )
    (t,) = load_traces(p)  # a BOM, a numeric id, structured text and epoch seconds
    assert t["id"] == "7"
    assert t["turns"][0]["text"] == '{"type": "template"}'
    assert t["turns"][0]["at"] == "1970-01-01T00:00:00+00:00"
    p.write_text('{"id": "a", "turns": ["hello"]}\n', encoding="utf-8")
    with pytest.raises(TraceError, match="must be an object"):
        load_traces(p)


def test_serve_refuses_an_empty_trace_file(tmp_path, capsys):
    empty = tmp_path / "t.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert main(["serve", str(empty), "--no-browser"]) == 2
    assert "no conversations" in capsys.readouterr().err


def test_agree_compares_two_reviewers(tmp_path, capsys):
    from chatlens.analysis import compare_reviewers

    def labels(rows):
        return {r[0]: {"trace": r[0], "verdict": r[1], "note": "", "codes": r[2]} for r in rows}

    a = labels([("t1", "fail", ["wrong-fee"]), ("t2", "pass", []), ("t3", "fail", ["no-link"])])
    b = labels([("t1", "fail", ["wrong-fee"]), ("t2", "fail", ["rude"]), ("t4", "pass", [])])
    axial = {"policy": ["wrong-fee"], "tone": ["rude"], "links": ["no-link"]}
    res = compare_reviewers(a, b, axial)
    assert (res["both"], res["only_a"], res["only_b"]) == (2, 1, 1)
    assert res["disagree"] == ["t2"] and res["verdict_agreement"] == 0.5
    assert res["mode_kappa"] == 1.0  # both failed only t1, both called it policy
    pa, pb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    from chatlens.store import save_labels

    save_labels(pa, a)
    save_labels(pb, b)
    (tmp_path / "map.yaml").write_text("policy: [wrong-fee]\ntone: [rude]\n", encoding="utf-8")
    assert main(["agree", str(pa), str(pb), "--map", str(tmp_path / "map.yaml")]) == 0
    out = capsys.readouterr().out
    assert "verdicts differ: t2" in out and "kappa" in out


def test_malformed_axial_map_is_an_error_not_a_traceback(tmp_path, capsys):
    p = tmp_path / "map.yaml"
    for text in ("policy: [wrong-fee\n", "- just\n- a list\n"):
        p.write_text(text, encoding="utf-8")
        assert main(["report", str(EXAMPLES / "labels.jsonl"), "--map", str(p)]) == 2
        assert "error:" in capsys.readouterr().err


def test_serve_does_not_look_up_its_own_hostname(tmp_path, monkeypatch):
    """http.server resolves the bind address before listening; on a macOS CI runner that
    took ~35 s, so `chatlens serve` would sit unreachable that long."""
    import socket

    def boom(*a):
        raise AssertionError("getfqdn called")

    monkeypatch.setattr(socket, "getfqdn", boom)
    httpd = serve(load_traces(EXAMPLES / "traces.jsonl"), tmp_path / "labels.jsonl", 0)
    httpd.server_close()
