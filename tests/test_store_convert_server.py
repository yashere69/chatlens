import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from chatlens.cli import main
from chatlens.convert import from_whatsapp, to_turncheck
from chatlens.server import serve
from chatlens.store import TraceError, clean_label, load_labels, load_traces, save_labels

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_trace_validation(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"id": "a", "turns": [{"role": "bot", "text": "x"}]}\n')
    with pytest.raises(TraceError, match="role"):
        load_traces(p)
    p.write_text('{"id": "a", "turns": []}\n{"id": "a", "turns": []}\n')
    with pytest.raises(TraceError, match="duplicate"):
        load_traces(p)


def test_clean_label_normalises_codes_and_drops_them_on_pass():
    assert clean_label({"trace": "a", "verdict": "fail", "codes": ["Wrong Fee", " wrong fee"]})[
        "codes"
    ] == ["wrong-fee"]
    assert clean_label({"trace": "a", "verdict": "pass", "codes": ["x"]})["codes"] == []
    with pytest.raises(ValueError):
        clean_label({"trace": "a", "verdict": "maybe"})


def test_labels_round_trip(tmp_path):
    p = tmp_path / "sub" / "labels.jsonl"
    rows = {
        "b": clean_label({"trace": "b", "verdict": "pass"}),
        "a": clean_label({"trace": "a", "verdict": "fail", "codes": ["x"]}),
    }
    save_labels(p, rows)
    assert load_labels(p) == rows
    assert p.read_text().splitlines()[0].startswith('{"trace": "a"')


def test_whatsapp_import_assigns_store_replies_to_the_last_customer():
    text = (
        "01/02/26, 10:00 am - Asha: COD hai?\n"
        "01/02/26, 10:05 am - Store: Haan, ₹5,000 tak.\n"
        "01/02/26, 11:00 am - Ravi: size?\n"
        "01/02/26, 11:02 am - Store: S 36, M 38\n"
    )
    traces = {t["id"]: t for t in from_whatsapp(text, "Store")}
    assert [u["role"] for u in traces["asha-2026-02-01"]["turns"]] == ["customer", "agent"]
    assert traces["ravi-2026-02-01"]["turns"][1]["text"] == "S 36, M 38"


def test_turncheck_export_is_valid_yaml():
    trace = {
        "id": "t1",
        "turns": [{"role": "customer", "text": "COD hai?"}, {"role": "agent", "text": "no"}],
    }
    doc = yaml.safe_load(to_turncheck(trace, {"note": "wrong", "codes": ["x"]}))
    assert doc["steps"] == [{"send": "COD hai?"}, {"expect_reply": {}}]


def test_server_api(tmp_path):
    traces = load_traces(EXAMPLES / "traces.jsonl")
    labels_path = tmp_path / "labels.jsonl"
    httpd = serve(traces, labels_path, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert b"chatlens" in urllib.request.urlopen(base + "/").read()
        got = json.load(urllib.request.urlopen(base + "/api/traces"))
        assert len(got) == len(traces)
        body = json.dumps({"trace": traces[0]["id"], "verdict": "fail", "codes": ["X Y"]})
        req = urllib.request.Request(base + "/api/labels", data=body.encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        assert json.load(urllib.request.urlopen(req))["codes"] == ["x-y"]
        assert load_labels(labels_path)[traces[0]["id"]]["verdict"] == "fail"
        bad = urllib.request.Request(
            base + "/api/labels", method="POST", data=b'{"trace": "nope", "verdict": "pass"}'
        )
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad)
        assert e.value.code == 400
    finally:
        httpd.shutdown()


def test_cli_report_suggest_export(tmp_path, capsys):
    labels = str(EXAMPLES / "labels.jsonl")
    assert main(["report", labels, "--map", str(EXAMPLES / "axial.yaml")]) == 0
    assert "policy-error" in capsys.readouterr().out
    assert main(["suggest", labels, "--compare", str(EXAMPLES / "axial.yaml")]) == 0
    assert "kappa" in capsys.readouterr().out
    out = tmp_path / "scenarios"
    assert main(["export", str(EXAMPLES / "traces.jsonl"), labels, "-o", str(out)]) == 0
    assert len(list(out.glob("*.yaml"))) == sum(
        1 for x in (EXAMPLES / "labels.jsonl").read_text().splitlines() if '"fail"' in x
    )
