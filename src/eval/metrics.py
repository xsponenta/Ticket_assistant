"""Classification metrics shared by the evals (deterministic, no dependencies beyond the stdlib)."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

CLASSES = ["bug", "feature", "task", "idea"]


def accuracy(gold: Sequence[str], pred: Sequence[str | None]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold) if gold else 0.0


def per_class_prf(gold: Sequence[str], pred: Sequence[str | None], labels: Sequence[str] = CLASSES) -> dict:
    """{label: {precision, recall, f1, support}}; a None prediction counts as wrong."""
    out = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred, strict=True))
        fp = sum(g != label and p == label for g, p in zip(gold, pred, strict=True))
        fn = sum(g == label and p != label for g, p in zip(gold, pred, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        out[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


def macro_f1(gold: Sequence[str], pred: Sequence[str | None], labels: Sequence[str] = CLASSES) -> float:
    prf = per_class_prf(gold, pred, labels)
    return sum(v["f1"] for v in prf.values()) / len(labels)


def recall_of(label: str) -> Callable[[Sequence[str], Sequence[str | None]], float]:
    def metric(gold: Sequence[str], pred: Sequence[str | None]) -> float:
        return per_class_prf(gold, pred, [label])[label]["recall"]

    return metric


def confusion(gold: Sequence[str], pred: Sequence[str | None], labels: Sequence[str] = CLASSES) -> list[list[int]]:
    """Rows = gold, columns = predicted (labels + 'none' for a missing prediction)."""
    cols = [*labels, None]
    return [[sum(g == r and p == c for g, p in zip(gold, pred, strict=True)) for c in cols] for r in labels]


def bootstrap_ci(
    gold: Sequence[str],
    pred: Sequence[str | None],
    metric: Callable[[Sequence[str], Sequence[str | None]], float],
    n: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap 95% CI over items."""
    rng = random.Random(seed)
    idx = range(len(gold))
    values = sorted(
        metric([gold[i] for i in sample], [pred[i] for i in sample])
        for sample in ([rng.choice(idx) for _ in idx] for _ in range(n))
    )
    return values[int(0.025 * n)], values[int(0.975 * n) - 1]


def cohen_kappa(a: Sequence[str | None], b: Sequence[str | None]) -> float:
    """Cohen's kappa between two raters (labels compared as given; None is its own category)."""
    n = len(a)
    if not n:
        return 0.0
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    cats = set(a) | set(b)
    expected = sum((sum(x == c for x in a) / n) * (sum(y == c for y in b) / n) for c in cats)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def bootstrap_mean_ci(values: Sequence[float], n: int = 1000, seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap 95% CI of the mean of per-item values (e.g. reciprocal ranks)."""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    m = len(values)
    means = sorted(sum(values[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]
