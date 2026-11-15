"""src/eval/metrics.py and the item selection of src/eval/human_label_cli.py."""

import pandas as pd
import pytest

from src.eval import samples
from src.eval.metrics import CLASSES, accuracy, bootstrap_ci, confusion, macro_f1, per_class_prf, recall_of


def test_metrics():
    gold = ["bug", "bug", "feature", "task", "idea", "idea"]
    pred = ["bug", "feature", "feature", "task", "feature", None]
    prf = per_class_prf(gold, pred)
    assert prf["feature"] == pytest.approx({"precision": 1 / 3, "recall": 1.0, "f1": 0.5, "support": 1})
    assert macro_f1(gold, pred) == pytest.approx((2 / 3 + 0.5 + 1 + 0) / 4)
    assert accuracy(gold, pred) == pytest.approx(0.5)
    assert recall_of("idea")(gold, pred) == 0.0
    assert confusion(gold, pred)[3] == [0, 1, 0, 0, 1]  # idea row: one -> feature, one -> none
    low, high = bootstrap_ci(gold * 5, pred * 5, macro_f1, n=200)
    assert low <= macro_f1(gold, pred) <= high


def test_human_ceiling_sample_from_llm_subset_disjoint_from_bakeoff():
    rows = [{"key": f"{c}-{i:03d}", "target_class": c} for c in CLASSES for i in range(150 if c != "idea" else 25)]
    val = pd.DataFrame(rows)
    subset = samples.llm_val_subset(val)
    assert sum(k.startswith("idea") for k in subset) == 25 and len(subset) == 325
    keys = samples.human_ceiling_sample(val)
    assert len(keys) == 40 and set(keys) <= set(subset)
    assert not set(keys) & set(samples.bakeoff_sample(val))
    assert {c: sum(k.startswith(c) for k in keys) for c in CLASSES} == dict.fromkeys(CLASSES, 10)
    assert keys == samples.human_ceiling_sample(val)  # deterministic
