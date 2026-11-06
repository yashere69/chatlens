"""Build examples/traces.jsonl and examples/labels.jsonl for the demo.

Starts from a nakli chat export (a fictional store, generated data), imports it, then
injects four kinds of agent mistakes into some replies and writes labels for every trace,
with the free-form, inconsistent codes a real reviewer tends to use. The failures are
planted; that is what makes the demo's numbers checkable.

    python tools/make_sample.py path/to/chat-export-android.txt
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from chatlens.convert import from_whatsapp, write_jsonl
from chatlens.store import save_labels

ROOT = Path(__file__).resolve().parent.parent

FAILURES = [
    # (applies if, mutate, possible codes, note)
    (lambda t: "₹79" in t, lambda t: t.replace("₹79", "₹99"),
     ["wrong-shipping-fee", "fee-amount-wrong", "policy-number-wrong"],
     "quoted ₹99 shipping; policy says ₹79"),
    (lambda t: "7 din" in t, lambda t: t.replace("7 din", "15 din"),
     ["wrong-return-window", "return-days-wrong", "policy-number-wrong"],
     "said 15 days to return; policy is 7"),
    (lambda t: "Tracking" in t, lambda t: t.split(" Tracking")[0].split(" Tracking link")[0],
     ["missing-tracking-link", "no-tracking-link"],
     "order status without the tracking link"),
    (lambda t: True, lambda t: "Thank you for contacting Indigo Loom! We'll get back to you.",
     ["ignored-question", "question-ignored", "generic-reply"],
     "canned reply, didn't answer"),
]


def main(export: Path) -> None:
    r = random.Random(42)
    traces = from_whatsapp(export.read_text(encoding="utf-8"), "Indigo Loom")
    labels = {}
    for trace in traces:
        label = {"trace": trace["id"], "verdict": "pass", "note": "", "codes": []}
        if r.random() < 0.45:
            agent_turns = [t for t in trace["turns"] if t["role"] == "agent"]
            r.shuffle(agent_turns)
            for turn in agent_turns:
                specific = [f for f in FAILURES[:-1] if f[0](turn["text"])]
                if not specific and r.random() > 0.3:
                    continue
                options = specific or FAILURES[-1:]
                applies, mutate, codes, note = r.choice(options)
                turn["text"] = mutate(turn["text"])
                label = {"trace": trace["id"], "verdict": "fail", "note": note,
                         "codes": [r.choice(codes)]}
                break
        labels[trace["id"]] = label
    write_jsonl(traces, ROOT / "examples" / "traces.jsonl")
    save_labels(ROOT / "examples" / "labels.jsonl", labels)
    fails = sum(v["verdict"] == "fail" for v in labels.values())
    print(f"{len(traces)} traces, {fails} with a planted failure")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
