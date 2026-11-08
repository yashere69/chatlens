"""How the labelling page scales with the number of conversations.

Generates N synthetic two-turn conversations, serves them, and drives the page in
headless Chromium: page load until the first conversation renders, then the mean time
per `j` keypress over 20 presses, then the mean time per `p` (label + save + next) over
10. Results depend on the machine; they show the shape, not a guarantee.

    pip install playwright && python -m playwright install chromium
    python tools/ui_latency.py 200 2000 10000
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from chatlens.server import serve  # noqa: E402
from chatlens.store import load_traces  # noqa: E402


def measure(n: int, browser) -> str:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "traces.jsonl"
        turn = [{"role": "customer", "text": "COD hai? " * 20}, {"role": "agent", "text": "Haan"}]
        src.write_text(
            "".join(json.dumps({"id": f"c{k:05d}", "turns": turn}) + "\n" for k in range(n)),
            encoding="utf-8",
        )
        httpd = serve(load_traces(src), Path(d) / "labels.jsonl", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        page = browser.new_page()
        t0 = time.perf_counter()
        page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/")
        page.wait_for_selector(".turn")
        load = time.perf_counter() - t0
        t0 = time.perf_counter()
        for _ in range(20):
            page.keyboard.press("j")
        expect(page.locator("h2.tid")).to_have_text("c00020")
        move = (time.perf_counter() - t0) / 20
        t0 = time.perf_counter()
        for k in range(10):
            page.keyboard.press("p")
            expect(page.locator("#progress")).to_have_text(f"{k + 1} of {n} labelled")
        label = (time.perf_counter() - t0) / 10
        page.close()
        httpd.shutdown()
        httpd.server_close()
    return f"| {n:,} | {load:.2f} s | {move * 1000:.0f} ms | {label * 1000:.0f} ms |"


def main() -> None:
    sizes = [int(x) for x in sys.argv[1:]] or [200, 2000, 10000]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        print("| conversations | page load | per `j` | per `p` (label + save) |")
        print("|---|---|---|---|")
        for n in sizes:
            print(measure(n, browser))
        browser.close()


if __name__ == "__main__":
    main()
