"""C2 evaluation: duplicate finder (BM25 / dense / hybrid RRF), no LLM calls.

Stages (train+val queries only, except `test`):
    python eval/eval_c2.py --stage embedders              # dense MRR of 3 small embedders → choose (L3)
    python eval/eval_c2.py --stage variants               # BM25 / dense / hybrid × modes, alert threshold, errors
    python eval/eval_c2.py --stage test --confirm-test    # once, after approval (eval/c2_final_config.json)
    add --limit N for a smoke run on N duplicate + N non-duplicate queries

Ranks are computed within the corpus of issues created before the query (never the query itself), up to 100;
MRR is MRR@100. A hit = any gold in `gold_all`. Jira keys are masked as <ISSUE> in queries and docs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402  (settings only: models.embedder; no LLM calls)
from src.components.duplicate_finder import VARIANTS, DuplicateFinder  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import bootstrap_mean_ci  # noqa: E402
from src.retrieval.dense import PREFIXES, Embedder  # noqa: E402
from src.retrieval.text import issue_keys  # noqa: E402

DEPTH = 100
MODES = ("full", "summary")
EMBEDDERS = list(PREFIXES)
MAX_FALSE_ALARM = 0.20  # B1 target for C2
EMB_DIR = ROOT / "data" / "processed" / "embeddings"
RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "c2_final_config.json"
FIG_DIR = ROOT / "reports" / "figures"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"


# ---------------------------------------------------------------- data


def load_queries(splits: set[str], limit: int | None) -> tuple[list[dict], list[dict]]:
    with (ROOT / "data" / "eval" / "duplicates.jsonl").open() as f:
        rows = [json.loads(line) for line in f]
    dup = [r for r in rows if r["kind"] == "duplicate" and r["split"] in splits]
    non = [r for r in rows if r["kind"] != "duplicate" and r["split"] in splits]
    return (dup[:limit], non[:limit]) if limit else (dup, non)


def cache_path(model_id: str, masked: bool) -> Path:
    return EMB_DIR / f"{model_id.replace('/', '__')}{'' if masked else '__unmasked'}.npy"


# ---------------------------------------------------------------- evaluation


def run_queries(finder: DuplicateFinder, queries: list[dict], mode: str) -> list[dict[str, Any]]:
    """Per query: gold rank (or None beyond DEPTH), alert score, top-5 keys, latency."""
    out = []
    for q in queries:
        start = time.perf_counter()
        ranked, _, alert_score = finder.search(
            q["query_summary"],
            q["query_description_md"],
            mode,
            pd.Timestamp(q["corpus_created_before"]),
            q["query_key"],
            DEPTH,
        )
        ms = 1000 * (time.perf_counter() - start)
        keys = [str(finder.keys[i]) for i in ranked]
        gold = set(q["gold_all"])
        rank = next((i + 1 for i, k in enumerate(keys) if k in gold), None)
        out.append(
            {
                "query_key": q["query_key"],
                "kind": q["kind"],
                "rank": rank,
                "alert_score": round(alert_score, 6),
                "top5": keys[:5],
                "ms": round(ms, 2),
            }
        )
    return out


def ranking_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    dup = [r for r in records if r["kind"] == "duplicate"]
    rr = [1 / r["rank"] if r["rank"] else 0.0 for r in dup]
    m: dict[str, Any] = {"n": len(dup)}
    for k in (1, 5, 10):
        hits = [1.0 if r["rank"] and r["rank"] <= k else 0.0 for r in dup]
        lo, hi = bootstrap_mean_ci(hits)
        m[f"recall@{k}"], m[f"recall@{k}_ci95"] = round(sum(hits) / len(hits), 4), [round(lo, 4), round(hi, 4)]
    lo, hi = bootstrap_mean_ci(rr)
    m["mrr"], m["mrr_ci95"] = round(sum(rr) / len(rr), 4), [round(lo, 4), round(hi, 4)]
    m["not_in_top100"] = sum(r["rank"] is None for r in dup)
    ms = sorted(r["ms"] for r in records)
    m["latency_p50_ms"], m["latency_p95_ms"] = round(statistics.median(ms), 1), round(ms[int(0.95 * (len(ms) - 1))], 1)
    m["recall_curve"] = [round(sum(1 for r in dup if r["rank"] and r["rank"] <= k) / len(dup), 4) for k in range(1, 21)]
    return m


def alert_metrics(records: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    dup = [r for r in records if r["kind"] == "duplicate"]
    non = [r for r in records if r["kind"] != "duplicate"]
    alerts_dup = sum(r["alert_score"] >= threshold for r in dup)
    alerts_non = sum(r["alert_score"] >= threshold for r in non)
    useful = sum(r["alert_score"] >= threshold and r["rank"] is not None and r["rank"] <= 5 for r in dup)
    total = alerts_dup + alerts_non
    return {
        "threshold": threshold,
        "n_duplicate": len(dup),
        "n_non_duplicate": len(non),
        "alert_recall": round(alerts_dup / len(dup), 4) if dup else None,
        "alert_precision": round(alerts_dup / total, 4) if total else None,
        "false_alarm_rate": round(alerts_non / len(non), 4) if non else None,
        "useful_alert_rate": round(useful / len(dup), 4) if dup else None,
    }


def choose_threshold(records: list[dict[str, Any]], max_false_alarm: float = MAX_FALSE_ALARM) -> float:
    """Max alert recall subject to false-alarm rate <= max_false_alarm; else best F1. Ties → higher threshold."""
    candidates = sorted({r["alert_score"] for r in records}, reverse=True)
    stats = [alert_metrics(records, t) for t in candidates]
    feasible = [s for s in stats if s["false_alarm_rate"] is not None and s["false_alarm_rate"] <= max_false_alarm]
    if feasible:
        return max(feasible, key=lambda s: (s["alert_recall"], s["threshold"]))["threshold"]

    def f1(s: dict[str, Any]) -> float:
        p, r = s["alert_precision"] or 0.0, s["alert_recall"] or 0.0
        return 2 * p * r / (p + r) if p + r else 0.0

    return max(stats, key=lambda s: (f1(s), s["threshold"]))["threshold"]


def key_overlap(dup_queries: list[dict], issues: pd.DataFrame) -> dict[str, Any]:
    """Duplicate queries that cite at least one Jira key also cited by one of their gold issues (own keys excluded)."""
    by_key = issues.set_index("key")

    def cited(key: str, summary: str, description: str) -> set[str]:
        return issue_keys(f"{summary}\n{description}") - {key}

    shared = []
    for q in dup_queries:
        q_keys = cited(q["query_key"], q["query_summary"], q["query_description_md"])
        g_keys: set[str] = set()
        for g in q["gold_all"]:
            if g in by_key.index:
                g_keys |= cited(g, by_key.loc[g, "summary"], by_key.loc[g, "description_md"])
        if q_keys & g_keys:
            shared.append(q["query_key"])
    return {"n_queries": len(dup_queries), "share_a_cited_key": len(shared), "keys": shared}


# ---------------------------------------------------------------- outputs


def plot_recall_curves(curves: dict[str, list[float]], title: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"bm25": "#2a78d6", "dense": "#eb6834", "hybrid": "#1baf7a"}
    fig, ax = plt.subplots(figsize=(6, 3.4))
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ks = list(range(1, 21))
    label_y: list[float] = []
    for name, curve in sorted(curves.items(), key=lambda kv: -kv[1][-1]):
        ax.plot(ks, curve, color=colors[name], linewidth=2, label=name)
        y = min([curve[-1], *[v - 0.05 for v in label_y]])  # nudge direct labels apart
        label_y.append(y)
        ax.text(20.4, y, name, color="#52514e", fontsize=9, va="center")
    ax.axvline(5, color="#c3c2b7", linewidth=1, linestyle="--")
    ax.set_xticks([1, 5, 10, 15, 20])
    ax.set_xlabel("k", color="#52514e")
    ax.set_ylabel("Recall@k", color="#52514e")
    ax.set_ylim(0, 1)
    ax.set_xlim(1, 22)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    ax.set_title(title, fontsize=10, loc="left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def append_eval_rows(rows: list[list[str]]) -> None:
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write("| " + " | ".join(row) + " |\n")


def fmt(m: dict[str, Any]) -> str:
    return (
        f"MRR {m['mrr']:.3f} [{m['mrr_ci95'][0]:.2f}–{m['mrr_ci95'][1]:.2f}]; R@1/5/10 "
        f"{m['recall@1']:.2f}/{m['recall@5']:.2f}/{m['recall@10']:.2f}; p50 {m['latency_p50_ms']} ms"
    )


def save(stage: str, data: dict[str, Any], smoke: bool) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"c2_{stage}{'_smoke' if smoke else ''}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"Wrote {path.relative_to(ROOT)}")
    return path


# ---------------------------------------------------------------- stages


def stage_embedders(issues: pd.DataFrame, dup: list[dict], limit: int | None) -> dict[str, Any]:
    data: dict[str, Any] = {"stage": "embedders", "n_queries": len(dup), "models": {}}
    for model_id in EMBEDDERS:
        encoder = Embedder(model_id)
        finder = DuplicateFinder(issues, "dense", encoder, cache_path=cache_path(model_id, True))
        data["models"][model_id] = {"encode_seconds": finder.dense.encode_seconds, "prefixes": PREFIXES[model_id]}
        for mode in MODES:
            m = ranking_metrics(run_queries(finder, dup, mode))
            data["models"][model_id][mode] = m
            print(f"  {model_id:<42} {mode:<8} {fmt(m)}")
    best = max(m["full"]["mrr"] for m in data["models"].values())
    near = [mid for mid, m in data["models"].items() if m["full"]["mrr"] >= best - 0.01]
    data["chosen"] = min(near, key=lambda mid: data["models"][mid]["full"]["latency_p50_ms"])
    print(f"Chosen embedder (MRR full, tie within 0.01 → fastest): {data['chosen']}")
    return data


def evaluate_variants(
    issues: pd.DataFrame, queries: list[dict], embedder_id: str, variants: list[str], masked: bool = True
) -> dict[str, dict[str, list[dict]]]:
    encoder = Embedder(embedder_id)
    out: dict[str, dict[str, list[dict]]] = {}
    for variant in variants:
        finder = DuplicateFinder(
            issues,
            variant,
            encoder if variant != "bm25" else None,
            cache_path=cache_path(embedder_id, masked),
            mask_keys=masked,
        )
        out[variant] = {mode: run_queries(finder, queries, mode) for mode in MODES}
    return out


def stage_variants(issues: pd.DataFrame, dup: list[dict], non: list[dict], embedder_id: str) -> dict[str, Any]:
    records = evaluate_variants(issues, dup + non, embedder_id, list(VARIANTS))
    data: dict[str, Any] = {
        "stage": "variants",
        "embedder": embedder_id,
        "n_duplicate": len(dup),
        "n_non_duplicate": len(non),
        "variants": {},
    }
    for variant, by_mode in records.items():
        data["variants"][variant] = {
            mode: {"metrics": ranking_metrics(recs), "records": recs} for mode, recs in by_mode.items()
        }
        for mode in MODES:
            print(f"  {variant:<7} {mode:<8} {fmt(data['variants'][variant][mode]['metrics'])}")
    chosen = max(VARIANTS, key=lambda v: data["variants"][v]["full"]["metrics"]["mrr"])
    data["chosen_variant"] = chosen
    for mode in MODES:
        recs = data["variants"][chosen][mode]["records"]
        threshold = choose_threshold(recs)  # per mode: summary-only queries score lower cosines
        data.setdefault("alert", {})[mode] = alert_metrics(recs, threshold)
    data["key_overlap"] = key_overlap(dup, issues)
    unmasked = evaluate_variants(issues, dup, embedder_id, ["hybrid"], masked=False)["hybrid"]["full"]
    data["sensitivity_unmasked_hybrid_full"] = ranking_metrics(unmasked)
    data["worst_misses"] = worst_misses(data, chosen)
    print(f"Chosen variant (MRR, full): {chosen}; alert {data['alert']['full']}")
    print(
        f"Key overlap: {data['key_overlap']['share_a_cited_key']}/{data['key_overlap']['n_queries']}; "
        f"hybrid MRR unmasked {data['sensitivity_unmasked_hybrid_full']['mrr']:.3f}"
    )
    return data


def worst_misses(data: dict[str, Any], chosen: str, n: int = 10) -> list[dict[str, Any]]:
    recs = [r for r in data["variants"][chosen]["full"]["records"] if r["kind"] == "duplicate"]
    misses = [r for r in recs if r["rank"] is None or r["rank"] > 10]
    misses.sort(key=lambda r: (-(r["rank"] or DEPTH + 1), r["query_key"]))
    ranks = {v: {r["query_key"]: r["rank"] for r in data["variants"][v]["full"]["records"]} for v in VARIANTS}
    return [
        {
            "query_key": r["query_key"],
            "rank": r["rank"],
            "top5": r["top5"],
            "rank_by_variant": {v: ranks[v][r["query_key"]] for v in VARIANTS},
        }
        for r in misses[:n]
    ]


def stage_test(issues: pd.DataFrame, final: dict[str, Any]) -> dict[str, Any]:
    dup, non = load_queries({"test"}, None)
    records = evaluate_variants(issues, dup + non, final["embedder"], [final["variant"]])[final["variant"]]
    data: dict[str, Any] = {
        "stage": "test",
        "final_config": final,
        "n_duplicate": len(dup),
        "n_non_duplicate": len(non),
    }
    for mode in MODES:
        data[mode] = {
            "metrics": ranking_metrics(records[mode]),
            "alert": alert_metrics(records[mode], final["alert_threshold"][mode]),
            "records": records[mode],
        }
        print(f"  test {final['variant']} {mode:<8} {fmt(data[mode]['metrics'])}; alert {data[mode]['alert']}")
    # false alarms on all 100 non-duplicate queries (train+val+test) at the frozen threshold
    _, all_non = load_queries({"train", "val", "test"}, None)
    all_recs = evaluate_variants(issues, all_non, final["embedder"], [final["variant"]])[final["variant"]]
    data["false_alarm_all_100"] = {
        mode: alert_metrics(all_recs[mode], final["alert_threshold"][mode])["false_alarm_rate"] for mode in MODES
    }
    return data


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=["embedders", "variants", "test"], required=True)
    parser.add_argument("--limit", type=int, help="smoke run: first N duplicate and N non-duplicate queries")
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    issues = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet")
    if args.stage == "test":
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix="c2")
        data = stage_test(issues, json.loads(FINAL_CONFIG.read_text()))
        path = save("test", data, False)
        f = data["final_config"]
        date = datetime.now(UTC).date().isoformat()
        rows = [
            [
                date,
                "C2 duplicate finder",
                "ranking (test)",
                fmt(data[mode]["metrics"]),
                str(data[mode]["metrics"]["n"]),
                f"{f['variant']} · {f['embedder']}",
                "—",
                f"test, mode {mode}; {path.name}",
            ]
            for mode in MODES
        ]
        for mode in MODES:
            a = data[mode]["alert"]
            rows.append(
                [
                    date,
                    "C2 duplicate finder",
                    f"alert (test, mode {mode})",
                    f"recall {a['alert_recall']}; precision "
                    f"{a['alert_precision']}; false alarms {a['false_alarm_rate']} (all 100 non-dup: "
                    f"{data['false_alarm_all_100'][mode]})",
                    f"{a['n_duplicate']}+{a['n_non_duplicate']}",
                    f"{f['variant']} · {f['embedder']}",
                    "—",
                    f"threshold {f['alert_threshold'][mode]} (chosen on train+val)",
                ]
            )
        append_eval_rows(rows)
        return

    dup, non = load_queries({"train", "val"}, args.limit)
    test_keys = {q["query_key"] for q in load_queries({"test"}, None)[0] + load_queries({"test"}, None)[1]}
    assert not {q["query_key"] for q in dup + non} & test_keys, "tuning touched test queries"
    if args.stage == "embedders":
        save("embedders", stage_embedders(issues, dup, args.limit), bool(args.limit))
        return

    embedder_id = llm._settings().models["embedder"]
    if embedder_id == llm.PLACEHOLDER:
        raise SystemExit("models.embedder is not set in config.yaml: run --stage embedders and record L3 first.")
    data = stage_variants(issues, dup, non, embedder_id)
    path = save("variants", data, bool(args.limit))
    if args.limit:
        return
    plot_recall_curves(
        {v: data["variants"][v]["full"]["metrics"]["recall_curve"] for v in VARIANTS},
        f"C2 Recall@k · train+val (n={len(dup)}) · mode full",
        FIG_DIR / "c2_recall_trainval.png",
    )
    date = datetime.now(UTC).date().isoformat()
    rows = [
        [
            date,
            "C2 duplicate finder",
            "ranking (train+val, selection)",
            fmt(data["variants"][v][m]["metrics"]),
            str(len(dup)),
            f"{v} · {embedder_id if v != 'bm25' else 'BM25'}",
            "—",
            f"train+val, mode {m}; {path.name}",
        ]
        for v in VARIANTS
        for m in (("full", "summary") if v == data["chosen_variant"] else ("full",))
    ]
    for mode in MODES:
        a = data["alert"][mode]
        rows.append(
            [
                date,
                "C2 duplicate finder",
                f"alert (train+val, mode {mode})",
                f"recall {a['alert_recall']}; precision {a['alert_precision']}; false alarms {a['false_alarm_rate']}",
                f"{a['n_duplicate']}+{a['n_non_duplicate']}",
                f"{data['chosen_variant']} · {embedder_id}",
                "—",
                f"threshold {a['threshold']} (max recall s.t. false alarms ≤ 0.20, chosen per mode)",
            ]
        )
    append_eval_rows(rows)


if __name__ == "__main__":
    main()
