"""End-to-end evaluation: a simulated user with a hidden real ticket talks to the real pipeline (headless driver).

python eval/eval_e2e.py --split smoke                              # 5 val tickets x both policies
python eval/eval_e2e.py --split test --confirm-test                # the 60 test simulator candidates, once
python eval/eval_e2e.py --rescore eval/results/e2e_transcripts_<...>.jsonl   # recompute metrics, no LLM
python eval/eval_e2e.py --split test --keys SPARK-1,SPARK-2       # post-test check of single tickets (labelled
                                                                    # "posttest"; never replaces the test numbers)

Policies: auto = confirm C1's top-1 class; corrects = the simulated user confirms the gold class (intended UX).
Gold fields: data/eval/gap_extractions.jsonl (confirmed + grounded required fields of the gold class).
Deterministic metrics only (see reports/04_modeling.md, end-to-end).
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.eval.ablation import EXTRACTIONS  # noqa: E402
from src.eval.lock import check_test_allowed  # noqa: E402
from src.eval.metrics import bootstrap_mean_ci  # noqa: E402
from src.eval.run_log import read_lines  # noqa: E402
from src.eval.simulator import (  # noqa: E402
    AI_RE,
    DONT_KNOW_RE,
    META_RE,
    SimulatedUser,
    dont_know_only,
    make_opener,
    sentences,
)
from src.eval.spans import (  # noqa: E402
    GENERIC_TERMS,
    TOKEN_RE,
    content_word_share,
    content_words,
    invented_tokens,
    risky_tokens,
)
from src.pipeline_driver import Policy, run_dialogue  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.ticket_fields import CLASSES, class_fields  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
FINAL_CONFIG = ROOT / "eval" / "e2e_final_config.json"
EVAL_REPORT = ROOT / "reports" / "05_evaluation.md"
POLICIES = ("auto", "corrects")
USER_STEPS = {"answer", "confirm_class", "skip", "scope_decision", "confirm_assumptions", "dismiss"}
BUG_ELEMENTS = ("steps_to_reproduce", "expected_behavior", "actual_behavior", "environment")
SEED, WORKERS, MIN_SHARE, TARGET_TURNS = 42, 4, 0.6, 4


# ---------------------------------------------------------------- data


def hidden_tickets(split: str) -> list[dict[str, Any]]:
    """test: the 60 simulator candidates; smoke: 5 val tickets (one per class + 1, seed 42)."""
    with EXTRACTIONS.open(encoding="utf-8") as f:
        recs = [r for r in map(json.loads, f) if "extraction" in r]
    if split == "test":
        return [r for r in recs if r["split"] == "test"]
    dev = sorted((r for r in recs if r["split"] == "dev"), key=lambda r: r["key"])
    rng = random.Random(SEED)
    picked = [rng.choice([r for r in dev if r["class"] == c]) for c in CLASSES]
    picked.append(rng.choice([r for r in dev if r not in picked]))
    return picked


# ---------------------------------------------------------------- run


def run_ticket(rec: dict[str, Any], split: str, pipeline: Any) -> list[dict[str, Any]]:
    """Both policies for one hidden ticket (auto first; corrects reuses the cached common prefix)."""
    prefix = f"sim|{split}|{rec['key']}"
    opener, leaks, attempts = make_opener(rec["summary"], rec["description"], prefix)
    out = []
    for policy in POLICIES:
        user = SimulatedUser(rec["text"], f"{prefix}|{policy}")
        start = time.perf_counter()
        state = run_dialogue(
            pipeline, opener, user, Policy(confirm_class=rec["class"] if policy == "corrects" else None)
        )
        out.append(
            {
                "key": rec["key"],
                "split": split,
                "gold_class": rec["class"],
                "policy": policy,
                "opener": opener,
                "opener_leaks": leaks,
                "opener_attempts": attempts,
                "sim_turns": user.turns,
                "wall_s": round(time.perf_counter() - start, 1),
                "state": state.model_dump(),
            }
        )
    return out


def sim_costs(rows: list[dict[str, Any]], split: str) -> dict[tuple[str, str], float]:
    """Uncached simulator cost per (key, policy); the opener is charged to the policy that ran first (auto)."""
    costs: Counter = Counter()
    for r in rows:
        sid = r.get("session_id") or ""
        if not sid.startswith(f"sim|{split}|") or r.get("cached"):
            continue
        parts = sid.split("|")
        policy = "auto" if parts[3] == "opener" else parts[3]
        costs[(parts[2], policy)] += r.get("cost") or 0.0
    return costs


# ---------------------------------------------------------------- scoring


def turn_latencies(trace: list[dict[str, Any]]) -> list[float]:
    """System time per user action: the summed latency of the steps between one user action and the next."""
    turns, current = [], 0.0
    for e in trace:
        if e["step"] in USER_STEPS:
            if current:
                turns.append(current)
            current = 0.0
        else:
            current += e["latency_ms"]
    if current:
        turns.append(current)
    return turns


def word_recall(gold: str, rendered: str) -> float:
    words = set(content_words(gold))
    vocab = set(TOKEN_RE.findall(rendered.lower()))
    return sum(w in vocab for w in words) / len(words) if words else 1.0


def has_content(fields: dict[str, Any], name: str) -> bool:
    f = fields.get(name) or {}
    return f.get("status") in ("confirmed", "assumed") and bool(f.get("value"))


def score(t: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    st, gold_cls, ext = t["state"], t["gold_class"], rec["extraction"]
    ticket = st.get("ticket")
    completed = st["stage"] == "done" and ticket is not None and not st.get("last_error")
    fields = ticket["fields"] if ticket and st.get("ticket_class") == gold_cls else {}
    gold_req = [
        f.name
        for f in class_fields(gold_cls)
        if f.required and ext[f.name]["status"] == "confirmed" and ext[f.name]["grounded"]
    ]
    recovered = [n for n in gold_req if has_content(fields, n)]
    user_text = "\n".join(x["content"] for x in st["conversation"] if x["role"] == "user")
    confirmed = [f["value"] for f in (ticket or {}).get("fields", {}).values() if f["status"] == "confirmed"]
    text = "\n".join([ticket["title"], *confirmed]) if ticket else ""
    ignore = GENERIC_TERMS | set(st.get("component") or [])
    candidates = [c for c, _ in st.get("class_candidates") or []]
    sim = []
    for s in t["sim_turns"]:
        targets = [q["target_field"] for q in s["questions"]]
        absent = [n for n in targets if ext.get(n, {}).get("status") != "confirmed"]
        sim.append(
            {
                "sentences": sentences(s["answer"]),
                "dont_know": bool(DONT_KNOW_RE.search(s["answer"])),
                "dont_know_only": dont_know_only(s["answer"]),
                "all_absent": bool(targets) and len(absent) == len(targets),
                "all_present": bool(targets) and not absent,
                "ai_mention": bool(AI_RE.search(s["answer"])),
                "meta_mention": bool(META_RE.search(s["answer"])),
            }
        )
    return {
        "key": t["key"],
        "policy": t["policy"],
        "gold_class": gold_cls,
        "completed": completed,
        "error": (st.get("last_error") or {}).get("step"),
        "user_turns": 1 + len(t["sim_turns"]),
        "clicks": sum(e["step"] in ("confirm_class", "confirm_assumptions", "scope_decision") for e in st["trace"]),
        "question_turns": st.get("question_turns", 0),
        "gold_required": len(gold_req),
        "recovered": len(recovered),
        "recall": [word_recall(ext[n]["value"] or "", fields[n]["value"]) for n in recovered],
        "recall_quotes": [word_recall(" ".join(ext[n]["quotes"]), fields[n]["value"]) for n in recovered],
        "grounded": [content_word_share(v, user_text) >= MIN_SHARE for v in confirmed],
        "risky": len(risky_tokens(text) - ignore),
        "invented_vs_conversation": invented_tokens(text, user_text, ignore),
        "invented_vs_ticket": invented_tokens(text, rec["text"], ignore),
        "class_top1": bool(candidates) and candidates[0] == gold_cls,
        "class_top2": gold_cls in candidates[:2],
        "bug_all_four": all(has_content(fields, n) for n in BUG_ELEMENTS) if gold_cls == "bug" else None,
        "system_cost": sum(e["cost"] for e in st["trace"]),
        "turn_latency_ms": turn_latencies(st["trace"]),
        "c3_stop_offered": st.get("scope_stop_offered", False),
        "c2_pass2_alert": bool((st.get("c2_pass2") or {}).get("alert")),
        "opener_leak": bool(t["opener_leaks"]),
        "sim": sim,
    }


def ci(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    lo, hi = bootstrap_mean_ci(values)
    return {"value": round(sum(values) / len(values), 3), "ci95": [round(lo, 3), round(hi, 3)], "n": len(values)}


def ratio_ci(pairs: list[tuple[float, float]]) -> dict[str, Any] | None:
    """Micro ratio sum(a)/sum(b) with a bootstrap over tickets."""
    if not pairs or not sum(b for _, b in pairs):
        return None
    rng = random.Random(SEED)
    boots = []
    for _ in range(1000):
        sample = [rng.choice(pairs) for _ in pairs]
        den = sum(b for _, b in sample)
        boots.append(sum(a for a, _ in sample) / den if den else 0.0)
    boots.sort()
    value = sum(a for a, _ in pairs) / sum(b for _, b in pairs)
    return {"value": round(value, 3), "ci95": [round(boots[25], 3), round(boots[974], 3)], "n": len(pairs)}


def pct(values: list[float], q: float) -> float | None:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 1) if values else None


def aggregate(scores: list[dict[str, Any]], fresh: bool = True) -> dict[str, Any]:
    """fresh=False (policy corrects): its LLM calls largely hit the cache filled by policy auto, so latency and
    cost are reported from auto only."""
    sims = [x for s in scores for x in s["sim"]]
    lat = [x for s in scores for x in s["turn_latency_ms"]]
    risky = sum(s["risky"] for s in scores)
    out = {
        "n": len(scores),
        "completion": ci([float(s["completed"]) for s in scores]),
        "user_turns": ci([float(s["user_turns"]) for s in scores]),
        "user_turns_le_target": ci([float(s["user_turns"] <= TARGET_TURNS) for s in scores]),
        "clicks": ci([float(s["clicks"]) for s in scores]),
        "field_recovery": ratio_ci([(s["recovered"], s["gold_required"]) for s in scores]),
        "content_recall": ci([r for s in scores for r in s["recall"]]),
        "content_recall_vs_quotes": ci([r for s in scores for r in s["recall_quotes"]]),
        "grounded_confirmed": ci([float(g) for s in scores for g in s["grounded"]]),
        "invented_vs_conversation": round(sum(len(s["invented_vs_conversation"]) for s in scores) / risky, 3)
        if risky
        else None,
        "invented_vs_ticket": round(sum(len(s["invented_vs_ticket"]) for s in scores) / risky, 3) if risky else None,
        "tickets_with_invented_fact": ci([float(bool(s["invented_vs_ticket"])) for s in scores]),
        "class_top1": ci([float(s["class_top1"]) for s in scores]),
        "class_top2": ci([float(s["class_top2"]) for s in scores]),
        "bug_all_four": ci([float(s["bug_all_four"]) for s in scores if s["bug_all_four"] is not None]),
        "system_cost_per_ticket": round(sum(s["system_cost"] for s in scores) / len(scores), 5) if scores else None,
        "latency_turn_p50_ms": pct(lat, 0.5),
        "latency_turn_p95_ms": pct(lat, 0.95),
        "question_turns": ci([float(s["question_turns"]) for s in scores]),
        "turn_cap_hit": sum(s["question_turns"] >= TARGET_TURNS for s in scores),
        "c3_stop_offered": sum(s["c3_stop_offered"] for s in scores),
        "c2_pass2_alerts": sum(s["c2_pass2_alert"] for s in scores),
        "errors": dict(Counter(s["error"] for s in scores if s["error"])),
        "per_class": {
            c: {
                "completion": ci([float(s["completed"]) for s in scores if s["gold_class"] == c]),
                "field_recovery": ratio_ci(
                    [(s["recovered"], s["gold_required"]) for s in scores if s["gold_class"] == c]
                ),
            }
            for c in CLASSES
        },
        "simulator": {
            "answers": len(sims),
            "le_2_sentences": ci([float(x["sentences"] <= 2) for x in sims]),
            "dont_know_when_absent": ci([float(x["dont_know"]) for x in sims if x["all_absent"]]),
            "answers_when_present": ci([float(not x["dont_know_only"]) for x in sims if x["all_present"]]),
            "ai_mentions": sum(x["ai_mention"] for x in sims),
            "meta_mentions": sum(x["meta_mention"] for x in sims),
            "opener_leaks": sum(s["opener_leak"] for s in scores),
        },
    }
    if not fresh:
        for key in ("system_cost_per_ticket", "latency_turn_p50_ms", "latency_turn_p95_ms"):
            out[key] = "see auto"
    return out


def fmt(m: dict[str, Any]) -> str:
    def v(key: str) -> Any:
        return m[key]["value"] if isinstance(m.get(key), dict) else m.get(key)

    return (
        f"completion {v('completion')}; field recovery {v('field_recovery')} "
        f"{m['field_recovery']['ci95'] if m['field_recovery'] else ''}; content recall {v('content_recall')}; grounded "
        f"{v('grounded_confirmed')}; invented vs conversation {v('invented_vs_conversation')} / vs ticket "
        f"{v('invented_vs_ticket')}; class top-1 {v('class_top1')} (top-2 {v('class_top2')}); user turns "
        f"{v('user_turns')}; bug all-4 {v('bug_all_four')}; system ${v('system_cost_per_ticket')}/ticket; "
        f"turn latency p50 {v('latency_turn_p50_ms')} ms / p95 {v('latency_turn_p95_ms')} ms"
    )


# ---------------------------------------------------------------- review file


def transcript_md(t: dict[str, Any], s: dict[str, Any]) -> str:
    st = t["state"]
    lines = [
        f"## {t['key']} · gold {t['gold_class']} · policy {t['policy']}",
        f"Recovered {s['recovered']}/{s['gold_required']} required fields · user turns {s['user_turns']} · "
        f"invented vs ticket {s['invented_vs_ticket'] or 'none'} · opener leaks {t['opener_leaks'] or 'none'}\n",
    ]
    for m in st["chat"]:
        who = "**User (simulated):**" if m["role"] == "user" else "**Assistant:**"
        lines.append(f"{who} {m['content']}\n")
    if st.get("ticket"):
        lines.append(f"**Final ticket** — {st['ticket']['title']}\n\n{st['ticket']['body_markdown']}\n")
    lines.append('Simulator OK? (stays in role / answers only what is asked / honest "don\'t know"): ___\n')
    return "\n".join(lines)


def review(transcripts: list[dict], scores: list[dict], path: Path) -> None:
    pool = [(t, s) for t, s in zip(transcripts, scores, strict=True) if t["policy"] == "corrects"]
    rng = random.Random(SEED)
    picked = [rng.choice([p for p in pool if p[0]["gold_class"] == c]) for c in CLASSES]
    worst = min(
        (p for p in pool if p not in picked),
        key=lambda p: (p[1]["recovered"] / max(1, p[1]["gold_required"]), -len(p[1]["invented_vs_ticket"])),
    )
    text = "# E2E transcripts for manual review (policy: corrects)\n\n" + "\n---\n\n".join(
        transcript_md(t, s) for t, s in [*picked, worst]
    )
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- main


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def evaluate(transcripts: list[dict], split: str) -> tuple[dict, list[dict]]:
    recs = {r["key"]: r for r in hidden_tickets(split)}
    scores = [score(t, recs[t["key"]]) for t in transcripts]
    return {p: aggregate([s for s in scores if s["policy"] == p], fresh=p == "auto") for p in POLICIES}, scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["smoke", "test"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--budget", type=float, default=1.0)
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rescore", type=Path, help="recompute metrics from a saved transcripts file (no LLM)")
    parser.add_argument("--keys", help="post-test check: rerun only these test tickets (comma-separated)")
    args = parser.parse_args()

    if args.rescore:
        transcripts = [json.loads(line) for line in args.rescore.read_text().splitlines() if line.strip()]
        metrics, _ = evaluate(transcripts, transcripts[0]["split"])
        print(json.dumps({p: fmt(m) for p, m in metrics.items()}, indent=1))
        return
    if not args.split:
        parser.error("--split or --rescore is required")
    keys = [k.strip() for k in args.keys.split(",")] if args.keys else []
    label = "posttest" if keys else args.split
    if args.split == "test" and not keys:
        check_test_allowed("test", args.confirm_test, args.force, FINAL_CONFIG, RESULTS_DIR, prefix="e2e")
        if json.loads(FINAL_CONFIG.read_text())["git_commit"] != git_commit():
            raise SystemExit("HEAD differs from git_commit in eval/e2e_final_config.json: commit, then update it.")

    from src.pipeline import Pipeline
    from src.pipeline_resources import load_components

    pipeline = Pipeline(load_components())
    recs = hidden_tickets(args.split)[: args.limit] if args.limit else hidden_tickets(args.split)
    if keys:
        recs = [r for r in recs if r["key"] in keys]
        if len(recs) != len(keys):
            raise SystemExit(f"Unknown keys for split {args.split}: {set(keys) - {r['key'] for r in recs}}")
    offset = llm.log_offset()

    def spent() -> float:
        return sum(r.get("cost") or 0 for r in read_lines(llm._settings().log_path, offset) if not r.get("cached"))

    def one(rec: dict) -> list[dict]:
        if spent() > args.budget:
            return []
        return run_ticket(rec, args.split, pipeline)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        transcripts = [t for ts in pool.map(one, recs) for t in ts]
    costs = sim_costs(read_lines(llm._settings().log_path, offset), args.split)
    for t in transcripts:
        t["sim_cost"] = round(costs.get((t["key"], t["policy"]), 0.0), 6)
    stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tpath = RESULTS_DIR / f"e2e_transcripts_{label}_{stamp}.jsonl"
    tpath.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in transcripts), encoding="utf-8")
    metrics, scores = evaluate(transcripts, args.split)
    for p in POLICIES:
        sims = [t["sim_cost"] for t in transcripts if t["policy"] == p]
        metrics[p]["simulator_cost_per_ticket"] = round(sum(sims) / len(sims), 5) if sims else None
    data = {
        "stage": "e2e" if not keys else "e2e_posttest",
        "split": args.split,
        "keys": keys or None,
        "git_commit": git_commit(),
        "models": llm._settings().models,
        "prompts": {n: load_prompt(n).version for n in ("sim_opener", "sim_user")},
        "n_tickets": len(recs),
        "spent": round(spent(), 4),
        "metrics": metrics,
        "scores": scores,
        "transcripts": tpath.name,
    }
    path = RESULTS_DIR / f"e2e_{label}_{stamp}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    rpath = RESULTS_DIR / f"e2e_review_{label}_{stamp}.md"
    if not keys:
        review(transcripts, scores, rpath)
    for p, m in metrics.items():
        print(f"  {p}: n={m['n']}; {fmt(m)}; simulator ${m['simulator_cost_per_ticket']}/ticket")
        print(f"     simulator: {json.dumps(m['simulator'])}")
    print(f"  spent ${data['spent']}\nWrote {path.relative_to(ROOT)}, {tpath.name}, {rpath.name}")
    if keys:
        with EVAL_REPORT.open("a", encoding="utf-8") as f:
            for p, m in metrics.items():
                row = [
                    datetime.now(UTC).date().isoformat(),
                    f"End-to-end POST-TEST check ({p})",
                    f"rerun of {', '.join(keys)} only",
                    fmt(m),
                    f"{m['n']} dialogues",
                    f"pipeline C1–C6 · simulator {llm._settings().models['simulator']}",
                    f"{data['prompts']['sim_opener']} · {data['prompts']['sim_user']}",
                    f"post-test robustness check, NOT the test result; commit {data['git_commit'][:7]}; {path.name}",
                ]
                f.write("| " + " | ".join(str(x) for x in row) + " |\n")
        return
    if args.split != "test":
        return
    with EVAL_REPORT.open("a", encoding="utf-8") as f:
        for p, m in metrics.items():
            row = [
                datetime.now(UTC).date().isoformat(),
                f"End-to-end ({p})",
                "completion · field recovery · recall · invented · class · turns · bug all-4 · cost · latency",
                fmt(m),
                f"{m['n']} dialogues",
                f"pipeline C1–C6 · simulator {llm._settings().models['simulator']}",
                f"{data['prompts']['sim_opener']} · {data['prompts']['sim_user']}",
                f"test, once; commit {data['git_commit'][:7]}; {path.name}",
            ]
            f.write("| " + " | ".join(str(x) for x in row) + " |\n")
        sim = metrics["corrects"]["simulator"]
        row = [
            datetime.now(UTC).date().isoformat(),
            "E2E simulator behaviour",
            '≤ 2 sentences · honest "don\'t know" · answers when present · AI mentions · opener leaks',
            f"≤2 sentences {sim['le_2_sentences']}; don't know when absent {sim['dont_know_when_absent']}; answers "
            f"when present {sim['answers_when_present']}; AI mentions {sim['ai_mentions']}; opener leaks "
            f"{sim['opener_leaks']}",
            f"{sim['answers']} answers",
            llm._settings().models["simulator"],
            f"{data['prompts']['sim_opener']} · {data['prompts']['sim_user']}",
            f"test, policy corrects; {path.name}",
        ]
        f.write("| " + " | ".join(str(x) for x in row) + " |\n")


if __name__ == "__main__":
    main()
