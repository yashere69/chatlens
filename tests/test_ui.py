"""The labelling page in a real browser: the keyboard flow, hostile conversation text,
the CSP, and an axe accessibility scan. The CSP forbids eval, so the tests wait with
locators rather than page.wait_for_function. Skipped when Playwright or its Chromium is
missing (CI installs both in the `ui` job)."""

import json
import re
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

from chatlens.server import serve  # noqa: E402
from chatlens.store import load_labels, load_traces  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
XSS = "<img src=x onerror=\"document.title='pwned'\">"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


@pytest.fixture
def app(tmp_path, browser):
    traces = load_traces(EXAMPLES / "traces.jsonl")[:3]
    traces.append({"id": "hostile", "turns": [{"role": "customer", "text": XSS}]})
    src = tmp_path / "traces.jsonl"
    src.write_text("".join(json.dumps(t) + "\n" for t in traces), encoding="utf-8")
    labels = tmp_path / "labels.jsonl"
    httpd = serve(load_traces(src), labels, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    page = browser.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/")
    page.wait_for_selector(".turn")
    yield page, traces, labels, errors
    page.close()
    httpd.shutdown()
    httpd.server_close()


def test_keyboard_flow_saves_labels(app):
    page, traces, labels, errors = app
    page.keyboard.press("f")  # fail: focus moves to the note
    page.keyboard.type("quoted the wrong COD limit")
    page.keyboard.press("Tab")
    page.keyboard.type("wrong fee, Policy Error")
    page.keyboard.press("Control+Enter")  # save and go to the next conversation
    expect(page.locator("#progress")).to_have_text(re.compile(r"^1 of"))
    page.keyboard.press("p")  # pass and move on
    expect(page.locator("#progress")).to_have_text(re.compile(r"^2 of"))
    page.keyboard.press("k")
    page.keyboard.press("k")
    assert page.input_value("#codes") == "policy-error, wrong-fee"
    saved = load_labels(labels)
    assert saved[traces[0]["id"]]["codes"] == ["policy-error", "wrong-fee"]
    assert saved[traces[1]["id"]]["verdict"] == "pass"
    assert errors == []


def test_conversation_html_is_shown_as_text_not_run(app):
    page, traces, _, errors = app
    page.click("nav button:has-text('hostile')")
    page.wait_for_selector("text=<img src=x")
    assert page.title() == "chatlens"
    assert page.locator("#turns img").count() == 0
    assert not [e for e in errors if "Content Security Policy" in e]


def test_no_serious_accessibility_violations(app):
    axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")
    page = app[0]
    results = axe_mod.Axe().run(page)
    bad = [
        (v["id"], v["impact"], len(v["nodes"]))
        for v in results.response["violations"]
        if v["impact"] in {"serious", "critical"}
    ]
    assert bad == [], bad


def test_the_current_conversation_stays_in_view(tmp_path, browser):
    """Regression: with a long list, j moved the selection off-screen."""
    src = tmp_path / "many.jsonl"
    src.write_text(
        "".join(
            json.dumps({"id": f"c{k:04d}", "turns": [{"role": "customer", "text": "hi"}]}) + "\n"
            for k in range(300)
        ),
        encoding="utf-8",
    )
    httpd = serve(load_traces(src), tmp_path / "labels.jsonl", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    page = browser.new_page(viewport={"width": 1100, "height": 700})
    try:
        page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/")
        page.wait_for_selector(".turn")
        for _ in range(120):
            page.keyboard.press("j")
        expect(page.locator("h2.tid")).to_have_text("c0120")
        expect(page.locator("nav button[aria-current='true']")).to_be_in_viewport()
    finally:
        page.close()
        httpd.shutdown()
        httpd.server_close()
