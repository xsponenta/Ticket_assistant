"""Shared figures for the evals (light surface, one sequential blue ramp)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
BLUE_RAMP = ["#f4f8fe", "#86b6ef", "#2a78d6", "#0d366b"]


def plot_confusion(matrix: Sequence[Sequence[int]], labels: Sequence[str], title: str, path: Path) -> None:
    """Confusion matrix with counts; rows = gold, columns = predicted (extra columns, e.g. 'none', are dropped)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    n = len(labels)
    data = [list(row[:n]) for row in matrix]
    fig, ax = plt.subplots(figsize=(1.1 * n + 1.0, 1.0 * n + 0.8))
    fig.patch.set_facecolor(SURFACE)
    ax.imshow(data, cmap=LinearSegmentedColormap.from_list("blue", BLUE_RAMP))
    vmax = max(max(r) for r in data) or 1
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=10, color="#ffffff" if v > 0.55 * vmax else INK)
    short = [label.replace("_", "\n") for label in labels]
    ax.set_xticks(range(n), short, fontsize=8)
    ax.set_yticks(range(n), short, fontsize=8)
    ax.set_xlabel("predicted", color=INK2)
    ax.set_ylabel("gold", color=INK2)
    ax.set_title(title, fontsize=10, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
