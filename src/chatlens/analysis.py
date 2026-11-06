"""From open codes to failure modes.

Following Hamel Husain and Shreya Shankar's error-analysis process: read traces, write a
free-form note and short codes for the first thing that went wrong (open coding), then group
codes into a small set of failure modes (axial coding) and count them. The counts tell you
which evals are worth writing.

`suggest` proposes an axial grouping from the codes alone (token overlap, no model), and
`kappa` measures how far that suggestion agrees with your own grouping.
"""

from __future__ import annotations

import re
from collections import Counter


def mode_of(label: dict, axial: dict[str, list[str]]) -> str | None:
    """The failure mode of a failed trace: the mode of its first mapped code."""
    if label["verdict"] != "fail":
        return None
    for code in label["codes"]:
        for mode, codes in axial.items():
            if code in codes:
                return mode
    return "unmapped"


def failure_table(labels: dict[str, dict], axial: dict[str, list[str]]) -> list[tuple]:
    total = len(labels)
    modes = Counter(m for lab in labels.values() if (m := mode_of(lab, axial)))
    return [(mode, n, n / total if total else 0.0) for mode, n in modes.most_common()]


def _tokens(code: str) -> set[str]:
    return set(re.split(r"[-_\s]+", code.lower())) - {
        "",
        "the",
        "a",
        "of",
        "to",
        "wrong",
        "missing",
        "no",
        "not",
    }


def suggest(codes: list[str], threshold: float = 0.34) -> dict[str, list[str]]:
    """Group codes that share content words. 'wrong-order-id' and 'order-id-misread' end up
    together; 'wrong-tone' and 'wrong-order-id' don't, because 'wrong' is ignored."""
    groups: list[list[str]] = []
    for code in sorted(set(codes)):
        t = _tokens(code)
        best, best_sim = None, threshold
        for g in groups:
            gt = set().union(*(_tokens(c) for c in g))
            sim = len(t & gt) / len(t | gt) if t | gt else 0.0
            if sim >= best_sim:
                best, best_sim = g, sim
        if best is None:
            groups.append([code])
        else:
            best.append(code)
    out = {}
    for g in groups:
        common = Counter(tok for c in g for tok in _tokens(c)).most_common(1)
        name = common[0][0] if common else g[0]
        while name in out:
            name += "+"
        out[name] = sorted(g)
    return out


def kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters' labels over the same items."""
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(
    labels: dict[str, dict], mine: dict[str, list[str]], suggested: dict[str, list[str]]
) -> float:
    """Kappa over failed traces between your axial map and a suggested one.

    The two maps use different mode names, so each suggested mode is renamed to the mode of
    yours it overlaps most before comparing.
    """
    rename = {}
    for s_mode, s_codes in suggested.items():
        overlap = Counter(m for m, codes in mine.items() for c in s_codes if c in codes)
        rename[s_mode] = overlap.most_common(1)[0][0] if overlap else s_mode
    a, b = [], []
    for lab in labels.values():
        if lab["verdict"] != "fail":
            continue
        ma, mb = mode_of(lab, mine), mode_of(lab, suggested)
        a.append(ma or "")
        b.append(rename.get(mb or "", mb or ""))
    return kappa(a, b)
