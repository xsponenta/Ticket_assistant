"""Calibrate the C3 judges against human labels (needed before judge numbers count; decision B1).

45 pairs, frozen on first use in data/eval/judge_calibration_c3_pairs.jsonl:
  - 30 citation pairs (request, C3 explanation, cited chunk) from the dev verdict run (final k);
  - 15 relevance pairs (request, retrieved chunk) from the dev retrieval run.
Each set is sampled with seed 42, balanced between the judge's yes and no answers where possible, so that kappa
is not dominated by one class. The judge's answer is hidden while you label.

Usage:
    python -m src.eval.judge_label_cli            # label (resumable) -> data/eval/judge_calibration_c3.jsonl
    python -m src.eval.judge_label_cli --report   # kappa per judge + repeat consistency (after eval_c3 judge-repeat)
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import shutil
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.eval.metrics import cohen_kappa

ROOT = Path(__file__).resolve().parents[2]
PAIRS = ROOT / "data" / "eval" / "judge_calibration_c3_pairs.jsonl"
LABELS = ROOT / "data" / "eval" / "judge_calibration_c3.jsonl"
REPEAT = ROOT / "data" / "eval" / "judge_calibration_c3_repeat.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
N_CITATION, N_RELEVANCE, SEED = 30, 15, 42
QUESTIONS = {
    "citation": "Does the cited documentation chunk support the explanation?",
    "relevance": "Is this retrieved chunk relevant to deciding the request?",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def balanced_sample(pairs: list[dict[str, Any]], n: int, rng: random.Random) -> list[dict[str, Any]]:
    """n pairs, half judged yes and half judged no where possible (the rest filled from the larger side)."""
    yes = sorted((p for p in pairs if p["judge_run1"]), key=lambda p: p["pair_id"])
    no = sorted((p for p in pairs if not p["judge_run1"]), key=lambda p: p["pair_id"])
    rng.shuffle(yes)
    rng.shuffle(no)
    take_no = min(len(no), n // 2)
    take_yes = min(len(yes), n - take_no)
    take_no = min(len(no), n - take_yes)
    return yes[:take_yes] + no[:take_no]


def latest(pattern: str) -> Path:
    files = sorted(glob.glob(str(RESULTS_DIR / pattern)))
    if not files:
        raise SystemExit(f"No results matching eval/results/{pattern}: run eval/eval_c3.py first.")
    return Path(files[-1])


def build_pairs() -> list[dict[str, Any]]:
    """Freeze the 45 calibration pairs from the latest dev verdict and retrieval results."""
    verdict = json.loads(latest("c3_verdict_2*.json").read_text())
    retrieval = json.loads(latest("c3_retrieval_2*.json").read_text())
    rng = random.Random(SEED)
    citation = [dict(p, type="citation") for p in verdict["final"]["citation_pairs"]]
    relevance = [dict(p, type="relevance") for p in retrieval["relevance_pairs"]]
    pairs = balanced_sample(citation, N_CITATION, rng) + balanced_sample(relevance, N_RELEVANCE, rng)
    rng.shuffle(pairs)
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    with PAIRS.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return pairs


def show(p: dict[str, Any], done: int, total: int) -> None:
    width = min(110, shutil.get_terminal_size((110, 30)).columns)
    print("\n" + "═" * width)
    print(f" Judge calibration (C3)   [{done}/{total} labelled]   type: {p['type']}")
    print("─" * width)
    print(textwrap.fill("Request: " + p["summary"], width))
    if p.get("description"):
        print(
            textwrap.indent(
                textwrap.fill(p["description"][:600] + ("…" if len(p["description"]) > 600 else ""), width - 2), "  "
            )
        )
    if p["type"] == "citation":
        print("─" * width)
        print(f"Answer verdict: {p['verdict']}   doc_reference: {p.get('doc_reference') or '—'}")
        print(textwrap.fill("Explanation: " + p["explanation"], width))
    print("─" * width)
    print(f"Chunk [{p['chunk_id']}]:")
    print(p["chunk_text"][:1800] + ("…" if len(p["chunk_text"]) > 1800 else ""))
    print("─" * width)
    print("QUESTION: " + QUESTIONS[p["type"]])


def label_loop(pairs: list[dict[str, Any]]) -> None:
    done = {r["pair_id"] for r in read_jsonl(LABELS)}
    for p in pairs:
        if p["pair_id"] in done:
            continue
        show(p, len(done), len(pairs))
        while True:
            answer = input("y = yes, n = no, s = skip, q = quit: ").strip().lower()
            if answer in ("y", "n", "s", "q"):
                break
        if answer == "q":
            return
        if answer == "s":
            continue
        with LABELS.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "pair_id": p["pair_id"],
                        "type": p["type"],
                        "human": answer == "y",
                        "labeled_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
                )
                + "\n"
            )
        done.add(p["pair_id"])


def report() -> dict[str, Any]:
    pairs = {p["pair_id"]: p for p in read_jsonl(PAIRS)}
    human = {r["pair_id"]: r["human"] for r in read_jsonl(LABELS)}
    repeat = {r["pair_id"]: r["judge_run2"] for r in read_jsonl(REPEAT)}
    out: dict[str, Any] = {"created_at": datetime.now(UTC).isoformat(timespec="seconds")}
    for kind in ("citation", "relevance"):
        ids = [i for i, p in pairs.items() if p["type"] == kind and i in human]
        h = [human[i] for i in ids]
        j1 = [pairs[i]["judge_run1"] for i in ids]
        both = [i for i in ids if i in repeat]
        out[kind] = {
            "n": len(ids),
            "human_yes": sum(h),
            "judge_yes": sum(j1),
            "agreement": round(sum(a == b for a, b in zip(h, j1, strict=True)) / len(ids), 3) if ids else None,
            "cohen_kappa_human_vs_judge": round(cohen_kappa(h, j1), 3) if ids else None,
            "repeat_n": len(both),
            "repeat_agreement": round(sum(pairs[i]["judge_run1"] == repeat[i] for i in both) / len(both), 3)
            if both
            else None,
            "repeat_kappa": round(cohen_kappa([pairs[i]["judge_run1"] for i in both], [repeat[i] for i in both]), 3)
            if both
            else None,
            "disagreements": [
                {"pair_id": i, "human": human[i], "judge": pairs[i]["judge_run1"]}
                for i in ids
                if human[i] != pairs[i]["judge_run1"]
            ],
        }
        out[kind]["calibrated"] = bool(
            out[kind]["cohen_kappa_human_vs_judge"] is not None
            and out[kind]["cohen_kappa_human_vs_judge"] >= 0.6
            and len(ids) >= 15
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        result = report()
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"c3_judge_calibration_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(result, indent=1))
        print(
            json.dumps(
                {
                    k: {m: v for m, v in d.items() if m != "disagreements"} if isinstance(d, dict) else d
                    for k, d in result.items()
                },
                indent=1,
            )
        )
        print(f"Saved {path.relative_to(ROOT)}")
        return
    pairs = read_jsonl(PAIRS) or build_pairs()
    try:
        label_loop(pairs)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
    print(f"\n{len(read_jsonl(LABELS))} of {len(pairs)} labelled → {LABELS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
