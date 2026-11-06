"""Build site/ for GitHub Pages: the labelling page in demo mode with the sample traces.

    python tools/build_site.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    site = ROOT / "site"
    site.mkdir(exist_ok=True)
    shutil.copy(ROOT / "src" / "chatlens" / "static" / "index.html", site / "index.html")
    traces = [json.loads(x) for x in (ROOT / "examples" / "traces.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    (site / "sample-traces.json").write_text(json.dumps(traces, ensure_ascii=False),
                                             encoding="utf-8")
    print(f"site/ ready with {len(traces)} sample traces")


if __name__ == "__main__":
    main()
