"""Traces and labels on disk.

traces.jsonl  one conversation per line: {"id", "turns": [{"role", "text", "at"?}], "meta"?}
labels.jsonl  one label per trace:       {"trace", "verdict": "pass"|"fail", "note", "codes"}

Labels are rewritten whole, through a temporary file and a rename, on every save, so a
crash mid-write can't leave half a file. At a few hundred traces that's cheap.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROLES = {"customer", "agent", "tool", "system"}


class TraceError(ValueError):
    pass


def load_traces(path: Path) -> list[dict]:
    traces, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError as e:
            raise TraceError(f"{path}:{n}: not JSON ({e.msg})") from e
        if not isinstance(t, dict) or "id" not in t or not isinstance(t.get("turns"), list):
            raise TraceError(f"{path}:{n}: needs 'id' and a 'turns' list")
        if t["id"] in seen:
            raise TraceError(f"{path}:{n}: duplicate id {t['id']!r}")
        for turn in t["turns"]:
            if turn.get("role") not in ROLES:
                raise TraceError(f"{path}:{n}: turn role must be one of {sorted(ROLES)}")
        seen.add(t["id"])
        traces.append(t)
    return traces


def load_labels(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["trace"]] = row
    return out


def clean_label(row: dict) -> dict:
    verdict = row.get("verdict")
    if verdict not in {"pass", "fail"}:
        raise ValueError("verdict must be 'pass' or 'fail'")
    codes = sorted({c.strip().lower().replace(" ", "-") for c in row.get("codes", []) if
                    c.strip()})
    if verdict == "pass":
        codes = []
    return {"trace": str(row["trace"]), "verdict": verdict,
            "note": str(row.get("note", "")).strip(), "codes": codes}


def save_labels(path: Path, labels: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".labels-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for key in sorted(labels):
            f.write(json.dumps(labels[key], ensure_ascii=False) + "\n")
    os.replace(tmp, path)
