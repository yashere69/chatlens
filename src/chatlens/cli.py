"""chatlens command line."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import yaml

from . import __version__
from .analysis import agreement, failure_table, suggest
from .convert import from_chat_logs, from_whatsapp, to_turncheck, write_jsonl
from .server import serve
from .store import TraceError, load_labels, load_traces


def _axial(path: Path) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(v, list) and all(isinstance(c, str) for c in v) for v in data.values()
    ):
        raise ValueError(f"{path}: expected a mapping of failure mode -> list of codes")
    return {str(k): v for k, v in data.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chatlens")
    ap.add_argument("--version", action="version", version=f"chatlens {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="open the labelling page")
    s.add_argument("traces", type=Path)
    s.add_argument("--labels", type=Path, default=Path("labels.jsonl"))
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")

    i = sub.add_parser("import", help="WhatsApp export or chat-completions logs -> traces.jsonl")
    i.add_argument("export", type=Path)
    i.add_argument("--from", dest="fmt", choices=["whatsapp", "chat-logs"], default="whatsapp")
    i.add_argument("--business", help="the store's name in a WhatsApp export")
    i.add_argument("-o", "--out", type=Path, default=Path("traces.jsonl"))

    r = sub.add_parser("report", help="failure modes from labels and an axial map")
    r.add_argument("labels", type=Path)
    r.add_argument("--map", type=Path, help="YAML: failure mode -> list of codes")

    g = sub.add_parser("suggest", help="propose an axial map from your codes")
    g.add_argument("labels", type=Path)
    g.add_argument("--compare", type=Path, help="your own axial map, to compute kappa")

    e = sub.add_parser("export", help="failed traces -> turncheck scenarios")
    e.add_argument("traces", type=Path)
    e.add_argument("labels", type=Path)
    e.add_argument("-o", "--out", type=Path, default=Path("scenarios"))

    a = ap.parse_args(argv)
    try:
        if a.cmd == "serve":
            traces = load_traces(a.traces)
            if not traces:
                raise TraceError(f"{a.traces}: no conversations to label")
            try:
                httpd = serve(traces, a.labels, a.port)
            except OSError as e:
                raise OSError(f"can't listen on port {a.port} ({e.strerror}); try --port 0") from e
            url = f"http://127.0.0.1:{httpd.server_address[1]}/"
            print(f"{len(traces)} traces, labels in {a.labels}\nopen {url}  (Ctrl+C to stop)")
            if not a.no_browser:
                webbrowser.open(url)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            return 0
        if a.cmd == "import":
            text = a.export.read_text(encoding="utf-8")
            if a.fmt == "chat-logs":
                traces = from_chat_logs(text, a.export.stem)
            elif not a.business:
                print("error: WhatsApp imports need --business", file=sys.stderr)
                return 2
            else:
                traces = from_whatsapp(text, a.business)
            write_jsonl(traces, a.out)
            print(f"wrote {len(traces)} traces to {a.out}")
            return 0
        labels = load_labels(a.labels)
        if a.cmd == "report":
            axial = (
                _axial(a.map)
                if a.map
                else suggest([c for lab in labels.values() for c in lab["codes"]])
            )
            fails = sum(lab["verdict"] == "fail" for lab in labels.values())
            print(f"{len(labels)} traces labelled, {fails} failed\n")
            print(f"{'failure mode':<24}{'traces':>8}{'rate':>8}")
            for mode, n, rate in failure_table(labels, axial):
                print(f"{mode:<24}{n:>8}{rate:>8.0%}")
            return 0
        if a.cmd == "suggest":
            proposal = suggest([c for lab in labels.values() for c in lab["codes"]])
            print(yaml.safe_dump(proposal, sort_keys=True).rstrip())
            if a.compare:
                mine = _axial(a.compare)
                k = agreement(labels, mine, proposal)
                print(f"\n{len(proposal)} suggested groups vs {len(mine)} in {a.compare}")
                print(f"Cohen's kappa on failed traces, after matching groups: {k:.2f}")
            return 0
        traces_by_id = {t["id"]: t for t in load_traces(a.traces)}
        a.out.mkdir(parents=True, exist_ok=True)
        n = 0
        for lab in labels.values():
            if lab["verdict"] == "fail" and lab["trace"] in traces_by_id:
                (a.out / f"{lab['trace']}.yaml").write_text(
                    to_turncheck(traces_by_id[lab["trace"]], lab), encoding="utf-8"
                )
                n += 1
        print(f"wrote {n} scenarios to {a.out}/")
        return 0
    except (OSError, TraceError, ValueError, yaml.YAMLError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
