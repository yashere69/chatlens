import pytest

from chatlens.analysis import (
    adjusted_rand,
    compare_groupings,
    failure_table,
    kappa,
    mode_of,
    suggest,
)

AXIAL = {
    "policy-error": ["wrong-fee", "wrong-return-window"],
    "non-answer": ["ignored-question", "generic-reply"],
}


def lab(trace, verdict, *codes):
    return {"trace": trace, "verdict": verdict, "note": "", "codes": list(codes)}


def test_kappa_reference_values():
    assert kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    # textbook 2x2: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> kappa 0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert kappa(a, b) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        kappa([], [])


def test_mode_of_and_table():
    labels = {
        "t1": lab("t1", "fail", "wrong-fee"),
        "t2": lab("t2", "fail", "generic-reply"),
        "t3": lab("t3", "fail", "brand-new-code"),
        "t4": lab("t4", "pass"),
    }
    assert mode_of(labels["t4"], AXIAL) is None
    assert mode_of(labels["t3"], AXIAL) == "unmapped"
    table = dict((m, n) for m, n, _ in failure_table(labels, AXIAL))
    assert table == {"policy-error": 1, "non-answer": 1, "unmapped": 1}


def test_suggest_groups_by_content_words():
    groups = suggest(["missing-tracking-link", "no-tracking-link", "wrong-tone", "wrong-fee"])
    as_sets = [set(g) for g in groups.values()]
    assert {"missing-tracking-link", "no-tracking-link"} in as_sets
    assert {"wrong-tone"} in as_sets and {"wrong-fee"} in as_sets


def test_compare_groupings_ignores_names_but_not_splits():
    labels = {
        f"t{i}": lab(f"t{i}", "fail", c)
        for i, c in enumerate(
            ["wrong-fee", "wrong-return-window", "ignored-question", "generic-reply"]
        )
    }
    renamed = {
        "fee": ["wrong-fee", "wrong-return-window"],
        "q": ["ignored-question", "generic-reply"],
    }
    same_shape = compare_groupings(labels, AXIAL, renamed)
    split = {"a": ["wrong-fee"], "b": ["wrong-return-window"], "q": ["ignored-question"]}
    assert same_shape["ari"] == 1.0
    assert compare_groupings(labels, AXIAL, split)["ari"] < 1.0
    assert same_shape["crosstab"]["fee"] == {"policy-error": 2}


def test_adjusted_rand_known_values():
    assert adjusted_rand(list("aabb"), list("xxyy")) == 1.0
    assert adjusted_rand(list("aabb"), list("xyxy")) < 0
    assert abs(adjusted_rand(list("aabb"), list("xxyz")) - 0.5714) < 0.001  # sklearn's value
