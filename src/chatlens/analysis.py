"""From open codes to failure modes.

Following Hamel Husain and Shreya Shankar's error-analysis process: read traces, write a
free-form note and short codes for the first thing that went wrong (open coding), then group
codes into a small set of failure modes (axial coding) and count them. The counts tell you
which evals are worth writing.

`suggest` proposes an axial grouping from the codes alone (token overlap, no model), and
`compare_groupings` shows how it differs from your own. `kappa` is for two reviewers'
verdicts (`agree`).
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


_STOP = {"", "the", "a", "of", "to", "wrong", "missing", "no", "not"}


def _words(code: str) -> list[str]:
    """Content words of a code, in order."""
    return [w for w in re.split(r"[-_\s]+", code.lower()) if w not in _STOP]


def _tokens(code: str) -> set[str]:
    return set(_words(code))


def _group_name(group: list[str]) -> str:
    """The word most codes in the group share. On a tie, the last word of the first code:
    in "missing-tracking-link" or "wrong-return-window" that's the head noun. Picking from
    a set here made the name depend on the hash seed, so two runs could disagree."""
    counts = Counter(w for c in group for w in _tokens(c))
    if not counts:
        return group[0]
    top = max(counts.values())
    for code in sorted(group):
        for w in reversed(_words(code)):
            if counts[w] == top:
                return w
    return group[0]


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
        name = _group_name(g)
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


def _pairs(n: int) -> float:
    return n * (n - 1) / 2


def adjusted_rand(a: list[str], b: list[str]) -> float:
    """Adjusted Rand index between two groupings of the same items: 1 when they group
    identically, about 0 for chance. Unlike matching group names, it drops when either side
    splits or merges groups."""
    n = len(a)
    if n < 2:
        return 1.0
    index = sum(_pairs(c) for c in Counter(zip(a, b, strict=True)).values())
    sa = sum(_pairs(c) for c in Counter(a).values())
    sb = sum(_pairs(c) for c in Counter(b).values())
    expected = sa * sb / _pairs(n)
    best = (sa + sb) / 2
    if best == expected:
        return 1.0 if index == best else 0.0
    return (index - expected) / (best - expected)


def compare_groupings(
    labels: dict[str, dict], mine: dict[str, list[str]], suggested: dict[str, list[str]]
) -> dict:
    """How a suggested axial map groups your failed traces, compared with your own map:
    the adjusted Rand index, and for each suggested group, which of your modes its traces
    are in."""
    a, b = [], []
    for lab in labels.values():
        if lab["verdict"] != "fail":
            continue
        a.append(mode_of(lab, mine) or "(unmapped)")
        b.append(mode_of(lab, suggested) or "(unmapped)")
    crosstab: dict[str, Counter] = {}
    for m, s in zip(a, b, strict=True):
        crosstab.setdefault(s, Counter())[m] += 1
    return {"n": len(a), "ari": adjusted_rand(a, b), "crosstab": crosstab}


def compare_reviewers(
    a: dict[str, dict], b: dict[str, dict], axial: dict[str, list[str]] | None = None
) -> dict:
    """Agreement between two people who labelled the same traces.

    Verdict kappa over every trace both labelled; when an axial map is given, kappa over
    failure modes for the traces both called failed. `disagree` lists the traces to talk
    through, which is the point of having two reviewers.
    """
    both = sorted(set(a) & set(b))
    out: dict = {"both": len(both), "only_a": len(set(a) - set(b)), "only_b": len(set(b) - set(a))}
    if not both:
        return out
    va, vb = [a[t]["verdict"] for t in both], [b[t]["verdict"] for t in both]
    out["verdict_agreement"] = sum(x == y for x, y in zip(va, vb, strict=True)) / len(both)
    out["verdict_kappa"] = kappa(va, vb)
    out["disagree"] = [t for t, x, y in zip(both, va, vb, strict=True) if x != y]
    failed = [t for t in both if a[t]["verdict"] == b[t]["verdict"] == "fail"]
    if axial and failed:
        ma = [mode_of(a[t], axial) or "" for t in failed]
        mb = [mode_of(b[t], axial) or "" for t in failed]
        out["mode_kappa"] = kappa(ma, mb)
        out["mode_disagree"] = [t for t, x, y in zip(failed, ma, mb, strict=True) if x != y]
    return out
