"""C3 evaluation: scope checker on the user's 80 scope labels (dev 30 for tuning, test 50 evaluated once).

python eval/eval_c3.py --stage split                          # once: frozen data/eval/scope_split.json
python eval/eval_c3.py --stage retrieval [--limit 5]          # dev: BM25 / dense / hybrid, hit@k + relevance judge
python eval/eval_c3.py --stage verdict [--limit 5]            # dev: k in {3,5,8}, citation judge, grounding
python -m src.eval.judge_label_cli                            # you label 45 calibration pairs
python eval/eval_c3.py --stage judge-repeat                   # judge repeat run on the same 45 pairs
python eval/eval_c3.py --stage compare                        # dev: 3 corpus versions x subsets, confusion matrices
python -m src.eval.judge_label_cli --report                   # kappa per judge + repeat consistency
python eval/eval_c3.py --stage test --confirm-test            # once, after approval (eval/c3_final_config.json)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.components.scope_checker import VARIANTS, DocIndex, check, load_chunks, request_text  # noqa: E402
from src.eval.judges import judge_citation, judge_relevance, reference_grounded  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import accuracy, bootstrap_ci, confusion, macro_f1, per_class_prf  # noqa: E402
from src.eval.plots import plot_confusion  # noqa: E402
from src.eval.run_log import Budget, call_metrics, paid_calls, read_lines  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.retrieval.dense import Embedder  # noqa: E402
from src.schemas.c3 import SCOPE_LABELS  # noqa: E402

LABELS = list(SCOPE_LABELS)
SPLIT_PATH = ROOT / "data" / "eval" / "scope_split.json"
REPEAT = ROOT / "data" / "eval" / "judge_calibration_c3_repeat.jsonl"
PAIRS = ROOT / "data" / "eval" / "judge_calibration_c3_pairs.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "c3_final_config.json"
FIG_DIR = ROOT / "reports" / "figures"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
EMB_DIR = ROOT / "data" / "processed" / "embeddings"
K_GRID = (3, 5, 8)
HIT_KS = (1, 3, 5, 8, 10)
DEV_SIZE, SEED, WORKERS = 30, 42, 6


# ---------------------------------------------------------------- data


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_items() -> dict[str, dict[str, Any]]:
    """key -> candidate fields + human label + supporting chunk ids."""
    cands = {c["key"]: c for c in read_jsonl(ROOT / "data" / "eval" / "scope_candidates.jsonl")}
    items = {}
    for r in read_jsonl(ROOT / "data" / "eval" / "scope_labeled.jsonl"):
        c = cands[r["key"]]
        items[r["key"]] = {
            "key": r["key"],
            "summary": c["summary"],
            "description": c["description_md"],
            "label": r["label"],
            "supporting": r["supporting_chunk_ids"],
            "resolution_hint": c["resolution_hint"],
            "target_class": c["target_class"],
        }
    return items


def make_split(labels: dict[str, str], dev_size: int = DEV_SIZE, seed: int = SEED) -> dict[str, list[str]]:
    """Stratified by label, largest-remainder allocation of the dev quota, seeded shuffle within each label."""
    by_label: dict[str, list[str]] = {}
    for key, label in sorted(labels.items()):
        by_label.setdefault(label, []).append(key)
    total = len(labels)
    exact = {lab: len(keys) * dev_size / total for lab, keys in by_label.items()}
    quota = {lab: int(x) for lab, x in exact.items()}
    order = sorted(by_label, key=lambda lab: (-(exact[lab] - quota[lab]), LABELS.index(lab) if lab in LABELS else 99))
    for lab in order[: dev_size - sum(quota.values())]:
        quota[lab] += 1
    rng = random.Random(seed)
    dev: list[str] = []
    for lab in sorted(by_label):
        keys = sorted(by_label[lab])
        rng.shuffle(keys)
        dev += keys[: quota[lab]]
    test = sorted(set(labels) - set(dev))
    return {"dev": sorted(dev), "test": test}


def load_split() -> dict[str, Any]:
    if not SPLIT_PATH.exists():
        raise SystemExit("Run --stage split first.")
    return json.loads(SPLIT_PATH.read_text())


def latest(pattern: str) -> dict[str, Any]:
    files = sorted(glob.glob(str(RESULTS_DIR / pattern)))
    if not files:
        raise SystemExit(f"No eval/results/{pattern}; run the previous stage first.")
    return json.loads(Path(files[-1]).read_text())


def doc_index(variant: str, chunks: list[dict]) -> DocIndex:
    embedder_id = llm._settings().models["embedder"]
    encoder = Embedder(embedder_id) if variant != "bm25" else None
    cache = EMB_DIR / f"doc_chunks__{embedder_id.replace('/', '__')}.npy"
    return DocIndex(chunks, variant, encoder, cache)


def corpus_info(chunks: list[dict]) -> dict[str, Any]:
    """Fingerprint of the doc corpus a run used (the corpus changed twice during C3 modelling)."""
    digest = hashlib.sha256("".join(c["chunk_id"] + c["text"] for c in chunks).encode()).hexdigest()
    return {
        "n_chunks": len(chunks),
        "n_generated": sum("__generated" in c["chunk_id"] for c in chunks),
        "sha256": digest[:16],
    }


def parallel(fn, jobs: list) -> list:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(fn, jobs))


EVIDENCE = ROOT / "data" / "eval" / "scope_evidence_added.jsonl"


def evidence_subsets(items: dict, keys: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """docs-evidenced = a supporting chunk from labelling OR added later with scope_evidence_cli; else knowledge-based.
    Returns the subsets and the already_supported keys whose evidence review is still pending."""
    added = {r["key"]: r["added_chunk_ids"] for r in read_jsonl(EVIDENCE)} if EVIDENCE.exists() else {}
    evidenced = [k for k in keys if items[k]["supporting"] or added.get(k)]
    pending = [
        k for k in keys if items[k]["label"] == "already_supported" and not items[k]["supporting"] and k not in added
    ]
    return {
        "all": keys,
        "docs_evidenced": evidenced,
        "knowledge_based": [k for k in keys if k not in evidenced],
    }, pending


# Dev verdict runs per corpus version (CRISP-DM iterations, reports/decisions.md); each is the run of the variant
# chosen by the retrieval stage on that corpus. Files before iteration 2 carry no corpus fingerprint.
CORPUS_VERSIONS = {
    "v1_original": ("2,034 Markdown chunks", "c3_verdict_20261115T151215Z.json"),
    "v2_reference_lists": ("+ 111 reference list chunks", "c3_verdict_20261115T152008Z.json"),
    "v3_one_entry": ("+ 898 one-entry reference chunks", None),  # None: latest verdict run on the current corpus
}


def latest_on_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    for f in sorted(glob.glob(str(RESULTS_DIR / "c3_verdict_2*.json")), reverse=True):
        run = json.loads(Path(f).read_text())
        if run["final"].get("corpus", {}).get("sha256") == corpus["sha256"]:
            return run | {"file": Path(f).name}
    raise SystemExit("No dev verdict run on the current corpus: run --stage verdict first.")


def stage_compare(items: dict) -> dict[str, Any]:
    """Dev accuracy on all / docs-evidenced / knowledge-based items and the confusion matrix, per corpus version."""
    out: dict[str, Any] = {"stage": "compare", "versions": {}}
    for name, (desc, fname) in CORPUS_VERSIONS.items():
        run = (
            latest_on_corpus(corpus_info(load_chunks()))
            if fname is None
            else json.loads((RESULTS_DIR / fname).read_text()) | {"file": fname}
        )
        rep = subset_report(items, run["final"])
        out["pending_evidence_review"] = rep.pop("pending_evidence_review")
        out["versions"][name] = {
            "corpus": desc,
            "file": run["file"],
            "variant": run["final"]["variant"],
            "k": run["final"]["k"],
            **rep,
        }
        plot_confusion(
            rep["all"]["confusion"],
            LABELS,
            f"C3 · dev · {name} · {run['final']['variant']} k={run['final']['k']}",
            FIG_DIR / f"c3_dev_{name}.png",
        )
        print(f"{name} ({desc}; {run['file']})")
        for sub in ("all", "docs_evidenced", "knowledge_based"):
            m = rep[sub]
            print(f"  {sub:<16} n={m['n']:<3} " + (fmt(m) if m["n"] else "—"))
    return out


def subset_report(items: dict, run: dict[str, Any]) -> dict[str, Any]:
    results = {r["key"]: r for r in run["results"]}
    subsets, pending = evidence_subsets(items, list(results))
    out: dict[str, Any] = {"pending_evidence_review": pending}
    for name, keys in subsets.items():
        rs = [results[k] for k in keys]
        cites = [c for c in run["citation_pairs"] if c["key"] in set(keys)]
        out[name] = verdict_metrics(items, rs, cites) if rs else {"n": 0}
    return out


# ---------------------------------------------------------------- stages


def stage_retrieval(items: dict, dev: list[str], budget: Budget) -> dict[str, Any]:
    chunks = load_chunks()
    by_id = {c["chunk_id"]: c for c in chunks}
    top: dict[str, dict[str, list[str]]] = {}
    for variant in VARIANTS:
        index = doc_index(variant, chunks)
        top[variant] = {
            k: [index.ids[i] for i in index.search(request_text(items[k]["summary"], items[k]["description"]), 10)]
            for k in dev
        }

    pairs = sorted({(k, cid) for v in VARIANTS for k in dev for cid in top[v][k][:5]})

    def judge(pair: tuple[str, str]) -> dict[str, Any]:
        key, cid = pair
        it = items[key]
        if budget.exceeded():
            return {"pair_id": f"rel|{key}|{cid}", "error": "budget"}
        try:
            j = judge_relevance(it["summary"], it["description"], by_id[cid], session_id=f"c3|rel|{key}|{cid}")
        except Exception as exc:
            return {"pair_id": f"rel|{key}|{cid}", "error": f"{type(exc).__name__}: {exc}"[:200]}
        return {
            "pair_id": f"rel|{key}|{cid}",
            "key": key,
            "summary": it["summary"],
            "description": it["description"][:1500],
            "chunk_id": cid,
            "chunk_text": by_id[cid]["text"],
            "judge_run1": j.verdict,
            "judge_reasoning": j.reasoning,
        }

    judged = [p for p in parallel(judge, pairs) if "judge_run1" in p]
    relevant = {(p["key"], p["chunk_id"]): p["judge_run1"] for p in judged}
    with_support = [k for k in dev if items[k]["supporting"]]
    data: dict[str, Any] = {
        "stage": "retrieval",
        "corpus": corpus_info(chunks),
        "n_dev": len(dev),
        "n_with_supporting_chunk": len(with_support),
        "variants": {},
        "relevance_pairs": judged,
        "top10": top,
    }
    for variant in VARIANTS:
        hit = {
            f"hit@{k}": round(
                sum(any(c in top[variant][key][:k] for c in items[key]["supporting"]) for key in with_support)
                / max(1, len(with_support)),
                3,
            )
            for k in HIT_KS
        }
        rel = [[relevant.get((key, cid)) for cid in top[variant][key][:5]] for key in dev]
        rel_at5 = sum(sum(bool(x) for x in r) / 5 for r in rel) / len(dev)
        any5 = sum(any(bool(x) for x in r) for r in rel) / len(dev)
        data["variants"][variant] = {**hit, "relevance@5": round(rel_at5, 3), "any_relevant@5": round(any5, 3)}
        print(f"  {variant:<7} {hit} relevance@5 {rel_at5:.3f} any-relevant@5 {any5:.3f}")
    data["chosen_variant"] = max(
        VARIANTS, key=lambda v: (data["variants"][v]["relevance@5"], data["variants"][v]["hit@5"])
    )
    data["judge_calls"] = call_metrics(paid_calls(read_lines(llm._settings().log_path), budget.run_rows(), "c3|rel|"))
    print(f"Chosen retrieval variant: {data['chosen_variant']}; judge calls {data['judge_calls']}")
    return data


def run_verdicts(items: dict, keys: list[str], variant: str, k: int, tag: str, budget: Budget) -> dict[str, Any]:
    chunks = load_chunks()
    by_id = {c["chunk_id"]: c for c in chunks}
    index = doc_index(variant, chunks)
    prompt = load_prompt("c3_scope")

    def verdict(key: str) -> dict[str, Any]:
        it = items[key]
        if budget.exceeded():
            return {"key": key, "error": "skipped: budget exceeded"}
        try:
            out, retrieved = check(
                it["summary"],
                it["description"],
                k=k,
                index=index,
                prompt=prompt,
                session_id=f"c3|{tag}|{prompt.version}|{variant}|k{k}|{key}",
            )
        except Exception as exc:
            return {"key": key, "error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"key": key, "output": out.model_dump(), "retrieved": retrieved}

    results = parallel(verdict, keys)
    jobs = [
        (r["key"], cid, r["output"])
        for r in results
        if "output" in r
        for cid in r["output"]["cited_chunk_ids"]
        if cid in r["retrieved"]
    ]

    def cite(job: tuple[str, str, dict]) -> dict[str, Any]:
        key, cid, out = job
        it = items[key]
        try:
            j = judge_citation(it["summary"], out, by_id[cid], session_id=f"c3|cite|{tag}|{variant}|k{k}|{key}|{cid}")
        except Exception as exc:
            return {"pair_id": f"cite|{key}|{cid}", "error": f"{type(exc).__name__}: {exc}"[:200]}
        return {
            "pair_id": f"cite|{key}|{cid}",
            "key": key,
            "summary": it["summary"],
            "description": it["description"][:1500],
            "verdict": out["verdict"],
            "explanation": out["explanation"],
            "doc_reference": out.get("doc_reference"),
            "chunk_id": cid,
            "chunk_text": by_id[cid]["text"],
            "judge_run1": j.verdict,
            "judge_reasoning": j.reasoning,
        }

    citations = [c for c in parallel(cite, jobs) if "judge_run1" in c]
    for r in results:
        if "output" in r:
            texts = [by_id[c]["text"] for c in r["retrieved"]]
            r["doc_reference_grounded"] = (
                reference_grounded(r["output"].get("doc_reference"), texts)
                if r["output"]["verdict"] == "already_supported"
                else None
            )
    log_rows, run_rows = read_lines(llm._settings().log_path), budget.run_rows()
    calls = call_metrics(paid_calls(log_rows, run_rows, f"c3|{tag}|{prompt.version}|{variant}|k{k}|"))
    judge_calls = call_metrics(paid_calls(log_rows, run_rows, f"c3|cite|{tag}|{variant}|k{k}|"))
    return {
        "variant": variant,
        "k": k,
        "prompt_version": prompt.version,
        "corpus": corpus_info(chunks),
        "results": results,
        "citation_pairs": citations,
        "metrics": verdict_metrics(items, results, citations),
        "calls": calls,
        "judge_calls": judge_calls,
    }


def precision_of(items: dict, claims: list[dict]) -> float | None:
    """Share of already_supported verdicts whose label is already_supported (None without claims)."""
    return (
        round(sum(items[r["key"]]["label"] == "already_supported" for r in claims) / len(claims), 3) if claims else None
    )


def verdict_metrics(items: dict, results: list[dict], citations: list[dict]) -> dict[str, Any]:
    keys = [r["key"] for r in results]
    gold = [items[k]["label"] for k in keys]
    pred = [r["output"]["verdict"] if "output" in r else None for r in results]
    majority = max(LABELS, key=gold.count)
    lo, hi = bootstrap_ci(gold, pred, accuracy)
    flo, fhi = bootstrap_ci(gold, pred, lambda g, p: macro_f1(g, p, LABELS))
    outs = [r["output"] for r in results if "output" in r]
    cited = [
        (r["key"], c, c in r["retrieved"]) for r in results if "output" in r for c in r["output"]["cited_chunk_ids"]
    ]
    supported = [r for r in results if "output" in r and r["output"]["verdict"] == "already_supported"]
    grounded = [r for r in supported if r["doc_reference_grounded"]]
    sentences = [len([s for s in r["explanation"].replace("e.g.", "eg").split(". ") if s.strip()]) for r in outs]
    return {
        "n": len(keys),
        "failures": sum(p is None for p in pred),
        "accuracy": round(accuracy(gold, pred), 3),
        "accuracy_ci95": [round(lo, 3), round(hi, 3)],
        "majority_label": majority,
        "majority_baseline": round(gold.count(majority) / len(gold), 3),
        "macro_f1": round(macro_f1(gold, pred, LABELS), 3),
        "macro_f1_ci95": [round(flo, 3), round(fhi, 3)],
        "per_class": {c: {m: round(v, 3) for m, v in d.items()} for c, d in per_class_prf(gold, pred, LABELS).items()},
        "gold_counts": {c: gold.count(c) for c in LABELS},
        "pred_counts": {c: pred.count(c) for c in LABELS},
        "confusion": confusion(gold, pred, LABELS),
        "items_without_citation": sum(not o["cited_chunk_ids"] for o in outs),
        "invalid_citation_rate": round(sum(not ok for _, _, ok in cited) / len(cited), 3) if cited else None,
        "citation_support_rate": round(sum(c["judge_run1"] for c in citations) / len(citations), 3)
        if citations
        else None,
        "n_citations_judged": len(citations),
        # M3: C3 is precision-oriented; "already supported" is shown only when doc_reference is grounded.
        "already_supported_claims": len(supported),
        "already_supported_precision": precision_of(items, supported),
        "already_supported_grounded_claims": len(grounded),
        "already_supported_precision_grounded": precision_of(items, grounded),
        "doc_reference_grounded": round(sum(bool(r["doc_reference_grounded"]) for r in supported) / len(supported), 3)
        if supported
        else None,
        "ungrounded_references": [
            {"key": r["key"], "doc_reference": r["output"]["doc_reference"]}
            for r in supported
            if not r["doc_reference_grounded"]
        ],
        "explanation_le_2_sentences": round(sum(s <= 2 for s in sentences) / len(sentences), 3) if sentences else None,
    }


def fmt(m: dict[str, Any]) -> str:
    return (
        f"acc {m['accuracy']:.3f} [{m['accuracy_ci95'][0]:.2f}–{m['accuracy_ci95'][1]:.2f}] (majority "
        f"{m['majority_baseline']:.3f}); macro-F1 {m['macro_f1']:.3f}; citation support {m['citation_support_rate']}; "
        f"doc_ref grounded {m['doc_reference_grounded']}; already_supported precision "
        f"{m['already_supported_precision']} ({m['already_supported_claims']} claims), grounded-only "
        f"{m['already_supported_precision_grounded']} ({m['already_supported_grounded_claims']}); "
        f"invalid citations {m['invalid_citation_rate']}"
    )


def stage_verdict(items: dict, dev: list[str], variant: str, budget: Budget) -> dict[str, Any]:
    grid = {}
    for k in K_GRID:
        grid[k] = run_verdicts(items, dev, variant, k, "dev", budget)
        print(
            f"  {variant} k={k}: {fmt(grid[k]['metrics'])}; ${grid[k]['calls']['cost']:.4f} + judge "
            f"${grid[k]['judge_calls']['cost']:.4f}; spent ${budget.spent():.4f}"
        )
    best = max(g["metrics"]["accuracy"] for g in grid.values())
    best_k = min(k for k in grid if grid[k]["metrics"]["accuracy"] >= best - 1 / len(dev) - 1e-9)
    return {
        "stage": "verdict",
        "variant": variant,
        "k_grid": {
            str(k): {"metrics": g["metrics"], "calls": g["calls"], "judge_calls": g["judge_calls"]}
            for k, g in grid.items()
        },
        "k": best_k,
        "final": grid[best_k],
        "all": {str(k): g["results"] for k, g in grid.items()},
    }


def stage_judge_repeat() -> list[dict[str, Any]]:
    """Re-run both judges (uncached) on the 45 frozen calibration pairs."""
    pairs = read_jsonl(PAIRS)
    if not pairs:
        raise SystemExit("No calibration pairs yet: run `python -m src.eval.judge_label_cli` first.")

    def rerun(p: dict[str, Any]) -> dict[str, Any]:
        chunk = {"chunk_id": p["chunk_id"], "text": p["chunk_text"]}
        if p["type"] == "citation":
            out = {"verdict": p["verdict"], "explanation": p["explanation"], "doc_reference": p.get("doc_reference")}
            j = judge_citation(p["summary"], out, chunk, session_id=f"c3|repeat|{p['pair_id']}", use_cache=False)
        else:
            j = judge_relevance(
                p["summary"], p["description"], chunk, session_id=f"c3|repeat|{p['pair_id']}", use_cache=False
            )
        return {"pair_id": p["pair_id"], "type": p["type"], "judge_run2": j.verdict, "reasoning_run2": j.reasoning}

    rows = parallel(rerun, pairs)
    with REPEAT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


# ---------------------------------------------------------------- main


def save(stage: str, data: dict[str, Any], smoke: bool) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"c3_{stage}{'_smoke' if smoke else ''}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"Wrote {path.relative_to(ROOT)}")
    return path


def append_rows(rows: list[list[str]]) -> None:
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write("| " + " | ".join(row) + " |\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--stage", choices=["split", "retrieval", "verdict", "judge-repeat", "compare", "test"], required=True
    )
    parser.add_argument("--limit", type=int, help="smoke run on the first N dev items")
    parser.add_argument("--variant", choices=VARIANTS, help="override the retrieval variant for --stage verdict")
    parser.add_argument("--budget", type=float, default=1.0)
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    items = load_items()
    if args.stage == "split":
        if SPLIT_PATH.exists():
            raise SystemExit(f"{SPLIT_PATH.relative_to(ROOT)} exists and is frozen.")
        split = make_split({k: v["label"] for k, v in items.items()})
        split.update(
            seed=SEED,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            dev_counts={c: sum(items[k]["label"] == c for k in split["dev"]) for c in LABELS},
            test_counts={c: sum(items[k]["label"] == c for k in split["test"]) for c in LABELS},
            test_sha256=hashlib.sha256("\n".join(split["test"]).encode()).hexdigest(),
        )
        SPLIT_PATH.write_text(json.dumps(split, indent=1))
        print(f"Wrote {SPLIT_PATH.relative_to(ROOT)}: dev {split['dev_counts']}, test {split['test_counts']}")
        return

    split = load_split()
    budget = Budget(args.budget, llm._settings().log_path, prefix="c3|")
    date = datetime.now(UTC).date().isoformat()
    if args.stage == "compare":
        data = stage_compare(items)
        if data["pending_evidence_review"]:
            print(
                f"NOTE: evidence review pending for {len(data['pending_evidence_review'])} already_supported dev items "
                "(python -m src.eval.scope_evidence_cli); they count as knowledge-based for now."
            )
        save("compare", data, False)
        return

    if args.stage == "judge-repeat":
        rows = stage_judge_repeat()
        print(f"Wrote {REPEAT.relative_to(ROOT)} ({len(rows)} pairs); spent ${budget.spent():.4f}")
        return

    if args.stage == "test":
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix="c3")
        final = json.loads(FINAL_CONFIG.read_text())
        if corpus_info(load_chunks())["sha256"] != final["corpus_sha256"]:
            raise SystemExit("The doc corpus differs from the approved one (corpus_sha256 in c3_final_config.json).")
        res = run_verdicts(items, split["test"], final["variant"], final["k"], "test", budget)
        subsets = subset_report(items, res)
        data = {"stage": "test", "final_config": final, **res, "subsets": subsets}
        path = save("test", data, False)
        plot_confusion(
            res["metrics"]["confusion"],
            LABELS,
            f"C3 · test · {final['variant']} k={final['k']}",
            FIG_DIR / "c3_test.png",
        )
        for name in ("all", "docs_evidenced", "knowledge_based"):
            print(f"  test {name:<16} n={subsets[name]['n']:<3} " + (fmt(subsets[name]) if subsets[name]["n"] else "—"))
        append_rows(
            [
                [
                    date,
                    "C3 scope checker",
                    f"verdict (test, {name})",
                    fmt(subsets[name]),
                    str(subsets[name]["n"]),
                    f"{llm._settings().models['generator']} · {final['variant']} k={final['k']}",
                    res["prompt_version"],
                    f"test, once; corpus {res['corpus']['n_chunks']} chunks; citation judge uncalibrated "
                    f"(κ −0.04); {path.name}",
                ]
                for name in ("all", "docs_evidenced", "knowledge_based")
                if subsets[name]["n"]
            ]
        )
        return

    dev = split["dev"][: args.limit] if args.limit else split["dev"]
    assert not set(dev) & set(split["test"]), "dev run touched test items"
    if args.stage == "retrieval":
        data = stage_retrieval(items, dev, budget)
        path = save("retrieval", data, bool(args.limit))
        if not args.limit:
            append_rows(
                [
                    [
                        date,
                        "C3 retrieval",
                        "hit@5 (lower bound) · judged relevance@5",
                        f"{v}: hit@5 {m['hit@5']}, relevance@5 {m['relevance@5']}, "
                        f"any-relevant@5 {m['any_relevant@5']}",
                        f"{len(dev)} ({data['n_with_supporting_chunk']} with a supporting chunk)",
                        v,
                        "judge_chunk_relevance/v1",
                        f"dev; corpus {data['corpus']['n_chunks']} chunks; hit@k biased to BM25; "
                        f"judge uncalibrated until --report; {path.name}",
                    ]
                    for v, m in data["variants"].items()
                ]
            )
        return

    variant = args.variant or latest("c3_retrieval_2*.json")["chosen_variant"]
    data = stage_verdict(items, dev, variant, budget)
    path = save("verdict", data, bool(args.limit))
    if args.limit:
        per_item = sum(g["calls"]["cost"] + g["judge_calls"]["cost"] for g in data["k_grid"].values()) / len(dev)
        print(f"Projected dev verdict cost (30 items, 3 k): ${per_item * DEV_SIZE:.3f}")
        return
    m = data["final"]["metrics"]
    plot_confusion(m["confusion"], LABELS, f"C3 · dev · {variant} k={data['k']}", FIG_DIR / "c3_dev.png")
    append_rows(
        [
            [
                date,
                "C3 scope checker",
                "verdict (dev, tuning)",
                fmt(m),
                str(m["n"]),
                f"{llm._settings().models['generator']} · {variant} k={data['k']}",
                data["final"]["prompt_version"],
                f"dev; corpus {data['final']['corpus']['n_chunks']} chunks; k grid "
                f"{[(k, g['metrics']['accuracy']) for k, g in data['k_grid'].items()]}; {path.name}",
            ]
        ]
    )


if __name__ == "__main__":
    main()
