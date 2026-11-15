"""C1 evaluation: baseline (TF-IDF + LogisticRegression) and LLM (few-shot) classifier.

VAL = tuning (baseline C grid, LLM k grid). TEST and DRIFT = final configs only, ONCE, after the val results are
approved (eval/c1_final_config.json + --confirm-test). Both input modes: "full" and "summary" (summary-only).

Usage:
    python eval/eval_c1.py --split val --limit 5                    # smoke run: LLM on 5 per class, projected cost
    python eval/eval_c1.py --split val --budget 1.2                 # full val run
    python eval/eval_c1.py --human-report eval/results/c1_val_<ts>.json   # human ceiling vs models (no calls)
    python eval/eval_c1.py --split test --confirm-test              # once, after approval
    python eval/eval_c1.py --split drift --confirm-test             # once, after approval
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.components.classifier import CLASSES, MODES, FewShotIndex, classify, input_text, map_components  # noqa: E402
from src.components.classifier_baseline import (  # noqa: E402
    build_features,
    fit_class_model,
    fit_component_model,
    rank_components,
)
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import (  # noqa: E402
    accuracy,
    bootstrap_ci,
    cohen_kappa,
    confusion,
    macro_f1,
    per_class_prf,
    recall_of,
)
from src.eval.plots import plot_confusion  # noqa: E402
from src.eval.run_log import Budget, call_metrics, paid_calls, read_lines  # noqa: E402
from src.eval.samples import drift_slice, human_ceiling_sample, llm_val_subset, load_split  # noqa: E402
from src.prompting import load_prompt  # noqa: E402

FINAL_CONFIG = ROOT / "eval" / "c1_final_config.json"
RESULTS_DIR = ROOT / "eval" / "results"
FIG_DIR = ROOT / "reports" / "figures"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
HUMAN_LABELS = ROOT / "data" / "eval" / "human_ceiling_val.jsonl"
WORKERS = 6
K_TIE = 0.01  # prefer the smaller (cheaper) k when within this macro-F1 of the best


# ---------------------------------------------------------------- data


def load_items(split: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Rows for the split, keys for the baseline (all) and keys for the LLM (subset / frozen eval set)."""
    if split == "val":
        df = load_split("val")
        return df, list(df.key), llm_val_subset(df)
    if split == "test":
        df = load_split("test")
        with (ROOT / "data" / "eval" / "classification_test.jsonl").open() as f:
            frozen = [json.loads(line)["key"] for line in f]
        return df, list(df.key), frozen
    df = pd.read_parquet(ROOT / "data" / "processed" / "drift_2026.parquet")
    return df, list(df.key), drift_slice(df)


def limit_keys(keys: list[str], labels: dict[str, str], per_class: int | None) -> list[str]:
    if not per_class:
        return keys
    out: list[str] = []
    for cls in CLASSES:
        out += [k for k in keys if labels[k] == cls][:per_class]
    return out


# ---------------------------------------------------------------- metrics


def evaluate(keys: list[str], gold: dict[str, str], comps: dict[str, set[str]], preds: dict[str, Any]) -> dict:
    g = [gold[k] for k in keys]
    p = [(preds.get(k) or {}).get("label") for k in keys]
    ranked = [(preds.get(k) or {}).get("component") or [] for k in keys]
    f1_lo, f1_hi = bootstrap_ci(g, p, macro_f1)
    has_idea = "idea" in g
    idea_lo, idea_hi = bootstrap_ci(g, p, recall_of("idea")) if has_idea else (None, None)
    prf = per_class_prf(g, p)
    return {
        "n": len(keys),
        "failures": sum(x is None for x in p),
        "accuracy": round(accuracy(g, p), 4),
        "macro_f1": round(macro_f1(g, p), 4),
        "macro_f1_ci95": [round(f1_lo, 4), round(f1_hi, 4)],
        "idea_recall": round(prf["idea"]["recall"], 4) if has_idea else None,
        "idea_recall_ci95": [round(idea_lo, 4), round(idea_hi, 4)] if has_idea else None,
        "per_class": {c: {m: round(v, 4) for m, v in d.items()} for c, d in prf.items()},
        "confusion": confusion(g, p),
        "component_top1": round(
            sum(bool(r[:1]) and r[0] in comps[k] for k, r in zip(keys, ranked, strict=True)) / len(keys), 4
        ),
        "component_top3": round(
            sum(bool(set(r[:3]) & comps[k]) for k, r in zip(keys, ranked, strict=True)) / len(keys), 4
        ),
    }


# ---------------------------------------------------------------- baseline


def run_baseline(
    train: pd.DataFrame,
    rows: pd.DataFrame,
    mode: str,
    keys: list[str],
    c_grid: list[float],
    fixed: dict[str, float] | None,
) -> dict[str, Any]:
    texts = lambda df: [input_text(s, d, mode) for s, d in zip(df.summary, df.description_md, strict=True)]  # noqa: E731
    eval_rows = rows.set_index("key").loc[keys].reset_index()
    features = build_features()
    x_train = features.fit_transform(texts(train))
    x_eval = features.transform(texts(eval_rows))
    y_train = list(train.target_class)
    comp_train = [map_components(list(c)) for c in train.components]
    gold = dict(zip(eval_rows.key, eval_rows.target_class, strict=True))
    comp_gold = {k: map_components(list(c)) for k, c in zip(eval_rows.key, eval_rows.components, strict=True)}

    grid, comp_grid = [], []
    if fixed:
        best_c, best_cc = fixed["C_class"], fixed["C_component"]
    else:  # tune on the eval rows (val only)
        for c in c_grid:
            pred = list(fit_class_model(x_train, y_train, c).predict(x_eval))
            grid.append({"C": c, "macro_f1": round(macro_f1(list(eval_rows.target_class), pred), 4)})
        for c in c_grid:
            ranked = rank_components(fit_component_model(x_train, comp_train, c), x_eval, top=1)
            top1 = sum(r[0] in comp_gold[k] for k, r in zip(eval_rows.key, ranked, strict=True)) / len(eval_rows)
            comp_grid.append({"C": c, "top1": round(top1, 4)})
        best_c = max(grid, key=lambda r: (r["macro_f1"], -r["C"]))["C"]
        best_cc = max(comp_grid, key=lambda r: (r["top1"], -r["C"]))["C"]

    class_model = fit_class_model(x_train, y_train, best_c)
    comp_model = fit_component_model(x_train, comp_train, best_cc)
    start = time.perf_counter()
    x = features.transform(texts(eval_rows))
    proba = class_model.predict_proba(x)
    ranked = rank_components(comp_model, x)
    per_item_ms = 1000 * (time.perf_counter() - start) / max(1, len(eval_rows))
    classes = list(class_model.classes_)
    preds = {
        k: {"label": classes[int(p.argmax())], "confidence": round(float(p.max()), 4), "component": r}
        for k, p, r in zip(eval_rows.key, proba, ranked, strict=True)
    }
    return {
        "C_grid": grid,
        "C_component_grid": comp_grid,
        "C_class": best_c,
        "C_component": best_cc,
        "latency_ms_per_item": round(per_item_ms, 3),
        "preds": preds,
        "gold": gold,
        "comp_gold": comp_gold,
    }


# ---------------------------------------------------------------- LLM


def run_llm(
    index: FewShotIndex, rows: pd.DataFrame, mode: str, k: int, keys: list[str], split: str, budget: Budget
) -> dict[str, dict[str, Any] | None]:
    prompt = load_prompt("c1_classifier")
    by_key = rows.set_index("key")

    def work(key: str) -> tuple[str, dict[str, Any] | None]:
        if budget.exceeded():
            return key, {"error": "skipped: budget exceeded"}
        r = by_key.loc[key]
        try:
            out = classify(
                r.summary,
                r.description_md,
                mode=mode,
                k=k,
                index=index,
                prompt=prompt,
                session_id=f"c1|{prompt.version}|{split}|{mode}|k{k}|{key}",
            )
        except Exception as exc:  # one failing item must not stop the run
            return key, {"error": f"{type(exc).__name__}: {exc}"[:300]}
        return key, {
            "label": out.label,
            "confidence": out.confidence,
            "component": list(out.component),
            "rationale": out.rationale,
        }

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return dict(pool.map(work, keys))  # key -> {"label", ...} or {"error": ...}


# ---------------------------------------------------------------- reporting helpers


def worst_errors(keys: list[str], gold: dict[str, str], preds: dict[str, Any], n: int = 10) -> list[str]:
    """Wrong predictions by confidence; idea<->feature and bug->task are forced in (up to 3 each)."""
    wrong = [k for k in keys if preds.get(k) and preds[k]["label"] != gold[k]]
    wrong.sort(key=lambda k: (-preds[k]["confidence"], k))
    pairs = {("idea", "feature"), ("feature", "idea")}
    forced = [k for k in wrong if (gold[k], preds[k]["label"]) in pairs][:3]
    forced += [k for k in wrong if (gold[k], preds[k]["label"]) == ("bug", "task")][:3]
    rest = [k for k in wrong if k not in forced]
    return (forced + rest)[:n]


def human_comparison(data: dict[str, Any]) -> dict[str, Any] | None:
    """Human ceiling (40 val items) vs Jira, and the final baseline / LLM configs (mode full) on the same items."""
    if not HUMAN_LABELS.exists():
        return None
    with HUMAN_LABELS.open() as f:
        human = {r["key"]: r["human_label"] for r in map(json.loads, f)}
    val = load_split("val")
    keys = [k for k in human_ceiling_sample(val) if k in human]
    if not keys:
        return None
    jira = dict(zip(val.key, val.target_class, strict=True))
    g = [jira[k] for k in keys]
    out: dict[str, Any] = {"n": len(keys)}
    h = [human[k] for k in keys]
    lo, hi = bootstrap_ci(g, h, macro_f1)
    out["human_vs_jira"] = {
        "macro_f1": round(macro_f1(g, h), 4),
        "macro_f1_ci95": [round(lo, 4), round(hi, 4)],
        "accuracy": round(accuracy(g, h), 4),
    }
    for variant in ("baseline", "llm"):
        final = data.get(variant, {}).get("full")
        if not final:
            continue
        preds = final["final_preds"]
        p = [(preds.get(k) or {}).get("label") for k in keys]
        out[f"{variant}_vs_jira"] = {"macro_f1": round(macro_f1(g, p), 4), "accuracy": round(accuracy(g, p), 4)}
        out[f"human_vs_{variant}"] = {"agreement": round(accuracy(h, p), 4), "cohen_kappa": round(cohen_kappa(h, p), 4)}
    out["human_jira_disagreements"] = [
        {"key": k, "jira": jira[k], "human": human[k]} for k in keys if jira[k] != human[k]
    ]
    return out


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return sha.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def append_eval_rows(rows: list[list[str]]) -> None:
    if not EVAL_REPORT.exists():
        EVAL_REPORT.write_text(
            "# 05 · Evaluation\n\nOne row per evaluation run of a final configuration "
            "(AGENTS.md). Values with bootstrap 95% CIs where given.\n\n"
            "| Date | Component | Metric | Value | n | Model | Prompt version | Note |\n"
            "|---|---|---|---|---:|---|---|---|\n"
        )
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write("| " + " | ".join(row) + " |\n")


def fmt_metrics(m: dict[str, Any]) -> str:
    ci = m["macro_f1_ci95"]
    idea = "—" if m["idea_recall"] is None else f"{m['idea_recall']:.2f}"
    return (
        f"macro-F1 {m['macro_f1']:.3f} [{ci[0]:.2f}–{ci[1]:.2f}]; acc {m['accuracy']:.3f}; idea R {idea}; "
        f"comp top-1/3 {m['component_top1']:.2f}/{m['component_top3']:.2f}"
    )


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["val", "test", "drift"], default="val")
    parser.add_argument("--variant", choices=["baseline", "llm", "all"], default="all")
    parser.add_argument("--mode", choices=["full", "summary", "both"], default="both")
    parser.add_argument("--k", default="0,2,4", help="few-shot examples per class to try (val)")
    parser.add_argument("--C", default="0.1,0.3,1,3,10", help="LogisticRegression C grid (val)")
    parser.add_argument("--limit", type=int, help="LLM smoke run: N items per class; prints the projected cost")
    parser.add_argument("--budget", type=float, default=1.2, help="stop LLM calls above this spend (USD)")
    parser.add_argument("--confirm-test", action="store_true", help="required for --split test/drift")
    parser.add_argument("--force", action="store_true", help="allow a second test/drift evaluation")
    parser.add_argument("--human-report", type=Path, help="add the human-ceiling comparison to a val results file")
    args = parser.parse_args()

    if args.human_report:
        data = json.loads(args.human_report.read_text())
        data["human_ceiling"] = human_comparison(data)
        args.human_report.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(
            json.dumps(
                {k: v for k, v in (data["human_ceiling"] or {}).items() if k != "human_jira_disagreements"}, indent=1
            )
        )
        return

    check_test_allowed(args.split, args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR)
    final = json.loads(FINAL_CONFIG.read_text()) if args.split != "val" else None
    modes = list(MODES) if args.mode == "both" else [args.mode]
    variants = ["baseline", "llm"] if args.variant == "all" else [args.variant]
    train = load_split("train")
    rows, base_keys, llm_keys = load_items(args.split)
    labels = dict(zip(rows.key, rows.target_class, strict=True))
    comps = {k: map_components(list(c)) for k, c in zip(rows.key, rows.components, strict=True)}
    llm_keys = limit_keys(llm_keys, labels, args.limit)
    assert not set(base_keys) & set(train.key), "eval items must not be in train"
    if args.split == "val":
        assert not (set(base_keys) | set(llm_keys)) & set(load_split("test").key), "val run touched test keys"

    prompt = load_prompt("c1_classifier")
    settings = llm._settings()
    data: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "split": args.split,
        "limit": args.limit,
        "generator_model": settings.models["generator"],
        "generator_reasoning": settings.reasoning.get("generator"),
        "prompt_version": prompt.version,
        "n_baseline_items": len(base_keys),
        "n_llm_items": len(llm_keys),
        "llm_keys": llm_keys,
    }
    budget = Budget(args.budget, settings.log_path, prefix="c1|")

    if "baseline" in variants:
        data["baseline"] = {}
        for mode in modes:
            fixed = final["baseline"][mode] if final else None
            res = run_baseline(train, rows, mode, base_keys, [float(c) for c in args.C.split(",")], fixed)
            data["baseline"][mode] = {
                "C_class": res["C_class"],
                "C_component": res["C_component"],
                "C_grid": res["C_grid"],
                "C_component_grid": res["C_component_grid"],
                "latency_ms_per_item": res["latency_ms_per_item"],
                "metrics_all": evaluate(base_keys, labels, comps, res["preds"]),
                "metrics_llm_items": evaluate(llm_keys, labels, comps, res["preds"]),
                "final_preds": res["preds"],
            }
            m = data["baseline"][mode]
            print(f"baseline {mode:<8} C={m['C_class']:<5} all: {fmt_metrics(m['metrics_all'])}")

    if "llm" in variants:
        data["llm"] = {}
        ks = [final["llm"][m]["k"] for m in modes] if final else None
        for i, mode in enumerate(modes):
            index = FewShotIndex(train, mode)
            assert set(index.keys) <= set(train.key), "few-shot examples must come from train"
            grid = {}
            for k in [ks[i]] if ks else [int(x) for x in args.k.split(",")]:
                preds = run_llm(index, rows, mode, k, llm_keys, args.split, budget)
                ok = {key: v for key, v in preds.items() if v and "label" in v}
                calls = call_metrics(
                    paid_calls(
                        read_lines(settings.log_path),
                        budget.run_rows(),
                        f"c1|{prompt.version}|{args.split}|{mode}|k{k}|",
                    )
                )
                grid[k] = {"metrics": evaluate(llm_keys, labels, comps, ok), "calls": calls, "preds": preds}
                print(
                    f"llm      {mode:<8} k={k}  {fmt_metrics(grid[k]['metrics'])}; ${calls['cost']:.4f} "
                    f"({calls['calls']} calls, p50 {calls['latency_p50_ms']} ms); spent ${budget.spent():.4f}"
                )
            best = max(grid[k]["metrics"]["macro_f1"] for k in grid)
            best_k = min(k for k in grid if grid[k]["metrics"]["macro_f1"] >= best - K_TIE)
            data["llm"][mode] = {
                "k_grid": {str(k): {"metrics": v["metrics"], "calls": v["calls"]} for k, v in grid.items()},
                "k": best_k,
                "final_metrics": grid[best_k]["metrics"],
                "final_calls": grid[best_k]["calls"],
                "final_preds": {key: v for key, v in grid[best_k]["preds"].items() if v and "label" in v},
                "all_preds": {str(k): v["preds"] for k, v in grid.items()},
            }

    if "llm" in data and "full" in data["llm"]:
        final_llm = data["llm"]["full"]["final_preds"]
        data["worst_errors"] = [
            {
                "key": k,
                "gold": labels[k],
                "llm": final_llm[k],
                "baseline": data.get("baseline", {}).get("full", {}).get("final_preds", {}).get(k),
                "summary": rows.set_index("key").loc[k].summary,
            }
            for k in worst_errors(llm_keys, labels, final_llm)
        ]
    if args.split == "val" and not args.limit:
        data["human_ceiling"] = human_comparison(data)
    data["spent_this_run"] = round(budget.spent(), 6)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"c1_{args.split}{'_smoke' if args.limit else ''}_{stamp}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"Wrote {path.relative_to(ROOT)}; LLM spend this run ${data['spent_this_run']:.4f}")

    if args.limit and "llm" in data:
        full_n = len(load_items(args.split)[2])
        projected = sum(
            v["calls"]["cost"] / max(1, len(llm_keys)) * full_n
            for mode in data["llm"].values()
            for v in mode["k_grid"].values()
        )
        print(f"Projected LLM cost of the full {args.split} run ({full_n} items × configs): ${projected:.3f}")
        return

    rows_05 = []
    date = datetime.now(UTC).date().isoformat()
    for mode in modes:
        if "baseline" in data:
            m = data["baseline"][mode]
            name = f"c1_baseline_{mode}_{args.split}"
            plot_confusion(
                m["metrics_llm_items"]["confusion"],
                CLASSES,
                f"C1 baseline · {mode} · {args.split}",
                FIG_DIR / f"{name}.png",
            )
            rows_05.append(
                [
                    date,
                    "C1 classifier (baseline)",
                    "class + component",
                    fmt_metrics(m["metrics_llm_items"]),
                    str(m["metrics_llm_items"]["n"]),
                    f"TF-IDF+LogReg C={m['C_class']}",
                    "—",
                    f"{args.split}, mode {mode}; same items as the LLM; all {args.split}: "
                    f"macro-F1 {m['metrics_all']['macro_f1']:.3f} (n={m['metrics_all']['n']})",
                ]
            )
        if "llm" in data:
            m = data["llm"][mode]
            name = f"c1_llm_{mode}_{args.split}"
            plot_confusion(
                m["final_metrics"]["confusion"],
                CLASSES,
                f"C1 LLM · {mode} · k={m['k']} · {args.split}",
                FIG_DIR / f"{name}.png",
            )
            rows_05.append(
                [
                    date,
                    "C1 classifier (LLM)",
                    "class + component",
                    fmt_metrics(m["final_metrics"]),
                    str(m["final_metrics"]["n"]),
                    f"{data['generator_model']} (reasoning off)",
                    data["prompt_version"],
                    f"{args.split}, mode {mode}, k={m['k']} per class; "
                    f"${m['final_calls']['cost_per_100_calls']}/100 calls, "
                    f"p50 {m['final_calls']['latency_p50_ms']} ms",
                ]
            )
    append_eval_rows(rows_05)
    print(f"Appended {len(rows_05)} rows to {EVAL_REPORT.relative_to(ROOT)}; figures in {FIG_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
