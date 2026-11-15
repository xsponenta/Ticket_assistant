"""Figure: C4 / C5 / C6 scores, dev vs test (values read from the approved eval/results runs).

    python scripts/plot_c456_scores.py      # -> reports/figures/c4_c5_c6_scores.png

All metrics are "higher is better" in [0, 1]; error rates are shown as 1 - rate. Colours: categorical slots 1-2 of
the dataviz reference palette (validated: CVD and normal-vision separation, contrast on the light surface).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"
OUT = ROOT / "reports" / "figures" / "c4_c5_c6_scores.png"
RUNS = {
    "c4": ("c4_dev_20261115T165319Z.json", "c4_test_20261115T170923Z.json"),
    "c5o": ("c5_oracle_dev_20261115T165508Z.json", "c5_oracle_test_20261115T171019Z.json"),
    "c5c": ("c5_chained_dev_20261115T165555Z.json", "c5_chained_test_20261115T171107Z.json"),
    "c6": ("c6_dev_20261115T172323Z.json", "c6_test_20261115T180201Z.json"),
}
DEV, TEST = "#2a78d6", "#eb6834"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def load(run: str) -> list[dict]:
    return [json.loads((RES / f).read_text()) for f in RUNS[run]]


def v(m: dict | float | None) -> float:
    return m["value"] if isinstance(m, dict) else float(m)


def natural_gap_recall(run: dict) -> float:
    """Recall on fields already missing in the real ticket (not deleted by the ablation)."""
    items = {}
    for line in (ROOT / "data" / "eval" / "gap_ablation.jsonl").read_text().splitlines():
        item = json.loads(line)
        items[item["item_id"]] = item
    hits = total = 0
    for r in run["results"]:
        it = items[r["item_id"]]
        for f in it["gold_missing"]:
            if f not in it["removed"]:
                total += 1
                hits += r["states"][f]["status"] == "missing"
    return hits / total


def panels() -> list[tuple[str, list[tuple[str, float, float]]]]:
    c4, c5o, c5c, c6 = load("c4"), load("c5o"), load("c5c"), load("c6")
    m4 = [r["metrics"] for r in c4]
    m5o, m5c, m6 = [r["metrics"] for r in c5o], [r["metrics"] for r in c5c], [r["metrics"] for r in c6]
    return [
        (
            "C4 · Gap detector",
            [
                ("Missing-field F1", m4[0]["missing"]["f1"], m4[1]["missing"]["f1"]),
                (
                    "F1, missing + assumed (operational, M4)",
                    m4[0]["not_confirmed_view"]["f1"],
                    m4[1]["not_confirmed_view"]["f1"],
                ),
                ("Recall on gaps in the real ticket", natural_gap_recall(c4[0]), natural_gap_recall(c4[1])),
                ('"I don\'t know" detected as unknown', m4[0]["unknown_detected"], m4[1]["unknown_detected"]),
                ("Confirmed values with grounded evidence", m4[0]["confirmed_grounded"], m4[1]["confirmed_grounded"]),
            ],
        ),
        (
            "C5 · Question generator",
            [
                ("≤ 2 questions per turn", v(m5o[0]["le_2_per_turn"]), v(m5o[1]["le_2_per_turn"])),
                ("Required coverage (oracle)", v(m5o[0]["required_coverage"]), v(m5o[1]["required_coverage"])),
                (
                    "Required coverage (chained after C4)",
                    v(m5c[0]["required_coverage"]),
                    v(m5c[1]["required_coverage"]),
                ),
                ("No question about a given field", 1 - v(m5o[0]["redundancy_rate"]), 1 - v(m5o[1]["redundancy_rate"])),
                (
                    'No re-ask after "I don\'t know"',
                    1 - v(m5c[0]["unknown_reask_rate"]),
                    1 - v(m5c[1]["unknown_reask_rate"]),
                ),
            ],
        ),
        (
            "C6 · Ticket composer",
            [
                ("Schema-valid", m6[0]["schema_valid"], m6[1]["schema_valid"]),
                (
                    "Required fields rendered (of resolved)",
                    m6[0]["coverage_of_resolved"],
                    m6[1]["coverage_of_resolved"],
                ),
                ("Confirmed values grounded", v(m6[0]["grounded_confirmed"]), v(m6[1]["grounded_confirmed"])),
                ("No invented tokens", 1 - m6[0]["invented_token_rate"], 1 - m6[1]["invented_token_rate"]),
                ("Assumptions section complete", v(m6[0]["assumptions_complete"]), v(m6[1]["assumptions_complete"])),
            ],
        ),
    ]


def main() -> None:
    data = panels()
    plt.rcParams.update({"font.size": 11, "font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.2), facecolor=SURFACE)
    h = 0.36
    for ax, (title, rows) in zip(axes, data, strict=True):
        ax.set_facecolor(SURFACE)
        n = len(rows)
        ys = list(range(n))[::-1]
        for y, (_, dev, test) in zip(ys, rows, strict=True):
            for offset, value, colour in ((h / 2 + 0.02, dev, DEV), (-h / 2 - 0.02, test, TEST)):
                ax.barh(y + offset, value, height=h, color=colour, edgecolor=SURFACE, linewidth=0)
                ax.text(
                    min(value, 1.0) + 0.012,
                    y + offset,
                    f"{round(value + 1e-9, 2):.2f}",
                    va="center",
                    ha="left",
                    fontsize=9.5,
                    color=INK,
                )
        ax.set_yticks(ys, ["\n".join(textwrap.wrap(label, 24)) for label, _, _ in rows], color=INK)
        ax.set_xlim(0, 1.12)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "0.25", "0.5", "0.75", "1"], color=MUTED)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0)
        ax.set_title(title, loc="left", fontsize=13.5, fontweight="bold", color=INK, pad=12)
    handles = [plt.Rectangle((0, 0), 1, 1, color=DEV), plt.Rectangle((0, 0), 1, 1, color=TEST)]
    fig.legend(
        handles,
        ["dev (val-derived ablation set)", "test (evaluated once)"],
        loc="upper right",
        ncol=2,
        frameon=False,
        fontsize=11,
        labelcolor=INK,
    )
    fig.suptitle(
        "C4 · C5 · C6 — deterministic metrics, higher is better",
        x=0.01,
        ha="left",
        fontsize=15,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.01,
        0.01,
        "Ablation set: 303 dev / 301 test items (real tickets with 1–2 required fields deleted). "
        "C4 false-confirmed on deleted fields is not shown: 0.47 upper bound, 0.31 after the human leak audit. "
        "C5 chained coverage is low because C4 marks deleted fields as assumed/confirmed.",
        fontsize=9.5,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=170, facecolor=SURFACE)
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
