"""Get traces in, get failing conversations out as regression tests.

- WhatsApp exports become one trace per customer per day.
- Failed traces become turncheck scenarios (github.com/yashere69/turncheck): the customer's
  messages replayed in order, with the label's note kept as the scenario name so the person
  writing assertions knows what went wrong.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import yaml

_LINE = re.compile(
    r"^\[?(?P<d>\d{1,2}/\d{1,2}/\d{2,4}), (?P<t>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:[   ](?P<ap>[ap]\.?m\.?))?\]?(?: -)? (?P<who>[^:]+): (?P<text>.*)$",
    re.I,
)


def _at(d: str, t: str, ap: str | None) -> datetime:
    day, month, year = (int(x) for x in d.split("/"))
    year += 2000 if year < 100 else 0
    h, m, *rest = (int(x) for x in t.split(":"))
    if ap:
        h = h % 12 + (12 if ap.lower().startswith("p") else 0)
    return datetime(year, month, day, h, m, rest[0] if rest else 0)


def from_whatsapp(text: str, business: str) -> list[dict]:
    msgs: list[tuple[datetime, str, str]] = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if m:
            msgs.append((_at(m["d"], m["t"], m["ap"]), m["who"].strip(), m["text"]))
        elif msgs and raw.strip():
            at, who, body = msgs[-1]
            msgs[-1] = (at, who, body + "\n" + raw)
    traces: dict[str, dict] = {}
    current: dict[str, str] = {}  # the store's reply goes to whoever wrote last
    last_customer = None
    for at, who, body in sorted(msgs, key=lambda x: x[0]):
        if who != business:
            last_customer = who
            key = f"{who} {at:%Y-%m-%d}"
            current[who] = key
            role = "customer"
        elif last_customer:
            key = current[last_customer]
            role = "agent"
        else:
            continue
        trace = traces.setdefault(
            key,
            {
                "id": key.lower().replace(" ", "-"),
                "turns": [],
                "meta": {"customer": last_customer or who},
            },
        )
        trace["turns"].append({"role": role, "text": body, "at": at.isoformat()})
    return list(traces.values())


ROLE_MAP = {
    "user": "customer",
    "assistant": "agent",
    "tool": "tool",
    "function": "tool",
    "system": "system",
    "developer": "system",
}


def _content(c: object) -> str:
    """Message content is a string, or a list of parts in newer APIs; keep the text parts."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in c
            if isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text")
        )
    return ""


def from_chat_logs(text: str, source: str = "log", filename: str | None = None) -> list[dict]:
    """JSONL of logged chat-completions calls: each line {"messages": [...]} or a bare list,
    optionally with "id". This is what most apps already log, so it's the shortest path from
    production to a review session. Tool calls on assistant messages become tool turns."""
    traces = []
    where = filename or source  # source also prefixes trace ids; errors name the file
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{where}:{n}: not JSON ({e.msg})") from e
        msgs = row if isinstance(row, list) else row.get("messages")
        if not isinstance(msgs, list):
            raise ValueError(f"{where}:{n}: expected a 'messages' list")
        turns = []
        for m in msgs:
            role = ROLE_MAP.get(str(m.get("role")))
            if role is None:
                raise ValueError(f"{where}:{n}: unknown role {m.get('role')!r}")
            text_ = _content(m.get("content"))
            if text_:
                turns.append({"role": role, "text": text_})
            for call in m.get("tool_calls") or []:
                fn = call.get("function", {})
                turns.append(
                    {"role": "tool", "text": f"{fn.get('name')}({fn.get('arguments', '')})"}
                )
        rid = row.get("id") if isinstance(row, dict) else None
        traces.append(
            {"id": str(rid or f"{source}-{n}"), "turns": turns, "meta": {"source": f"{source}:{n}"}}
        )
    return traces


def write_jsonl(traces: list[dict], path: Path) -> None:
    path.write_text(
        "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces), encoding="utf-8"
    )


def to_turncheck(trace: dict, label: dict) -> str:
    steps: list[dict] = []
    for turn in trace["turns"]:
        if turn["role"] == "customer":
            steps.append({"send": turn["text"]})
            steps.append({"expect_reply": {}})
    doc = {
        "name": f"{trace['id']}: {label['note'] or ', '.join(label['codes'])}",
        "customer": {"wa_id": "919800000001", "name": "Test Customer"},
        "steps": steps,
    }
    header = (
        f"# From chatlens: {trace['id']} was labelled fail "
        f"({', '.join(label['codes']) or 'no codes'}).\n"
        "# Tighten the expect_reply steps to describe the correct behaviour.\n"
    )
    return header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
