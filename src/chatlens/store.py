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
from datetime import UTC, datetime
from pathlib import Path

ROLES = {"customer", "agent", "tool", "system"}


class TraceError(ValueError):
    pass


def _turn(path: Path, n: int, turn) -> dict:
    if not isinstance(turn, dict):
        raise TraceError(f"{path}:{n}: each turn must be an object")
    if turn.get("role") not in ROLES:
        raise TraceError(f"{path}:{n}: turn role must be one of {sorted(ROLES)}")
    text = turn.get("text", "")
    out = {**turn, "text": text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)}
    at = turn.get("at")
    if isinstance(at, int | float) and not isinstance(at, bool):  # epoch seconds
        out["at"] = datetime.fromtimestamp(at, UTC).isoformat()
    elif at is not None and not isinstance(at, str):
        raise TraceError(f"{path}:{n}: turn 'at' must be an ISO time or epoch seconds")
    return out


def load_traces(path: Path) -> list[dict]:
    traces, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError as e:
            raise TraceError(f"{path}:{n}: not JSON ({e.msg})") from e
        if not isinstance(t, dict) or "id" not in t or not isinstance(t.get("turns"), list):
            raise TraceError(f"{path}:{n}: needs 'id' and a 'turns' list")
        if isinstance(t["id"], bool) or not isinstance(t["id"], str | int) or str(t["id"]) == "":
            raise TraceError(f"{path}:{n}: 'id' must be a non-empty string")
        t = {**t, "id": str(t["id"]), "turns": [_turn(path, n, u) for u in t["turns"]]}
        if t["id"] in seen:
            raise TraceError(f"{path}:{n}: duplicate id {t['id']!r}")
        seen.add(t["id"])
        traces.append(t)
    return traces


def load_labels(path: Path) -> dict[str, dict]:
    """Labels written by an earlier session. A damaged line stops the load instead of
    being dropped, because saving would then silently delete it."""
    if not path.exists():
        return {}
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = clean_label(json.loads(line))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as e:
            raise TraceError(f"{path}:{n}: not a label ({e}); fix or remove the line") from e
        out[row["trace"]] = row
    return out


def clean_label(row: dict) -> dict:
    verdict = row.get("verdict")
    if verdict not in {"pass", "fail"}:
        raise ValueError("verdict must be 'pass' or 'fail'")
    raw_codes = row.get("codes", [])
    if not isinstance(raw_codes, list) or not all(isinstance(c, str) for c in raw_codes):
        raise ValueError("codes must be a list of strings")
    codes = sorted({"-".join(c.lower().split()) for c in raw_codes if c.strip()})
    if verdict == "pass":
        codes = []
    return {
        "trace": str(row["trace"]),
        "verdict": verdict,
        "note": str(row.get("note", "")).strip(),
        "codes": codes,
    }


def save_labels(path: Path, labels: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".labels-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for key in sorted(labels):
            f.write(json.dumps(labels[key], ensure_ascii=False) + "\n")
    os.replace(tmp, path)
