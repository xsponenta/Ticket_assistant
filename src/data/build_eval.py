"""Build the evaluation sets in data/eval/ from data/processed/issues.parquet and splits.json.

  classification_test.jsonl   test split, ≤100 per class (all idea)        labels: target_class, components
  duplicates.jsonl            linked pairs: later issue = query, earlier = gold; + 100 non-duplicate queries (gold = null)
  scope_candidates.jsonl      80 resolved feature/idea issues for manual scope labelling (resolution = hint only)
  simulator_candidates.jsonl  test-split issues with rich descriptions, ≤15 per class (final pick later with an LLM)
  README.md                   how each set was built, sizes, label sources

Usage:
    python src/data/build_eval.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import pandas as pd

from clean import split_code
from prep_stats import EVAL, PROCESSED, SEED, update_stats

CLASSES = ["bug", "feature", "task", "idea"]
CLASSIFICATION_CAP = 100
NON_DUPLICATE_QUERIES = 100
NON_DUPLICATE_MIN_CREATED = pd.Timestamp("2020-04-01", tz="UTC")  # ≥ 3 months of corpus before the query
SCOPE_BUCKETS = {  # bucket -> (resolutions, how many)
    "fixed": (["Fixed"], 25),
    "declined": (["Won't Fix", "Won't Do", "Later"], 25),
    "not_a_problem_or_invalid": (["Not A Problem", "Invalid"], 25),
    "incomplete": (["Incomplete"], 5),
}
SIMULATOR_CAP = 15
SIMULATOR_MIN_WORDS = 80

# Bug signals from the EDA (notebooks/eda.ipynb §3), adapted to Markdown (code blocks are ``` fences now).
BUG_SIGNALS = {
    "repro": [  # keyword in prose, or a code snippet / shell prompt anywhere
        ("prose", r"steps? to reproduc|how to reproduc|to reproduce|reproduc(?:e|es|ed|ing|tion|ible)\b|\brepro\b"),
        ("full", r"^```|^\s*(?:scala|spark-sql|sql|>>)>"),
    ],
    "expected": [("prose", r"\bexpect(?:ed|s|ing)?\b|\bshould(?:n't| not)? (?:be|return|work|have|produce|give|succeed|fail|throw|not)\b"
                           r"|\bsupposed to\b|\bcorrect (?:result|output|answer|behaviou?r)")],
    "actual": [
        ("prose", r"\bactual(?:ly)?\b|\binstead\b|\bbut (?:got|gets|get|it|returns?|the result|we get|i get)\b|\bobserved\b"
                  r"|\b(?:returns?|gives?|produces?) (?:a )?(?:wrong|incorrect|null|empty)\b"),
        ("full", r"exception|traceback|stack ?trace|\berror\b|caused by:|^\s*at [a-z]+\.[\w.$]+\("),
    ],
    "version_env": [("full", r"\b(?:spark|pyspark)\s*(?:version\s*)?[:=]?\s*v?[1-4]\.\d|\bversion\s*[:=]?\s*v?\d+\.\d|\bv?[1-4]\.\d+\.\d+\b"
                             r"|\benvironment\b|(?<![.\w])(?:jdk|java|openjdk)(?:\s+version)?[\s:=]+(?:1\.8|8|11|17|21|25)\b"
                             r"|\bpython\s*(?:version\s*)?[:=]?\s*3\.\d|\bscala\s*2\.1[0-3]|\bhadoop\s*[23]\.\d"
                             r"|\b(?:ubuntu|centos|macos|mac os|windows|rhel|debian|amazon linux)\b|\b(?:emr|databricks|dataproc|hdinsight)\b")],
}
BUG_SIGNAL_RES = {name: [(scope, re.compile(p, re.I | re.M)) for scope, p in rules] for name, rules in BUG_SIGNALS.items()}


def prose(markdown: str) -> str:
    return "".join(seg for is_code, seg in split_code(markdown) if not is_code)


def bug_signals(markdown: str) -> dict[str, bool]:
    texts = {"full": markdown, "prose": prose(markdown)}
    return {name: any(rx.search(texts[scope]) for scope, rx in rules) for name, rules in BUG_SIGNAL_RES.items()}


def normalise_summary(summary: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", summary.lower()).split())


def n_words(text: str) -> int:
    return len(text.split())


def issue_fields(row: Any) -> dict[str, Any]:
    return {"key": row.key, "summary": row.summary, "description_md": row.description_md,
            "has_description": bool(row.has_description), "created": row.created.isoformat()}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sample_keys(keys: list[str], k: int, rng: random.Random) -> list[str]:
    keys = sorted(keys)
    return sorted(rng.sample(keys, k)) if len(keys) > k else keys


# ---------------------------------------------------------------- a. classification

def build_classification(df: pd.DataFrame) -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    test = df[df.split == "test"]
    rows, available = [], {}
    for cls in CLASSES:
        pool = test[test.target_class == cls]
        available[cls] = len(pool)
        for key in sample_keys(list(pool.key), CLASSIFICATION_CAP, rng):
            r = pool[pool.key == key].iloc[0]
            rows.append({**issue_fields(r),
                         "labels": {"target_class": r.target_class, "components": list(r.components)},
                         "meta": {"issuetype": r.issuetype, "resolution": r.resolution, "split": "test"}})
    stats = {"rows": len(rows), "by_class": {c: sum(r["labels"]["target_class"] == c for r in rows) for c in CLASSES},
             "available_in_test": available,
             "empty_description": sum(not r["has_description"] for r in rows)}
    return rows, stats


# ---------------------------------------------------------------- b. duplicates

def build_duplicates(df: pd.DataFrame) -> tuple[list[dict], dict]:
    """A Duplicate link is treated as UNDIRECTED: query = the later-created issue of the pair, gold = the earlier one
    (a user writing a new ticket must find the existing one). Ties on the creation time are broken by key."""
    by_key = df.set_index("key")
    created, summary = by_key.created.to_dict(), by_key.summary.to_dict()
    directed = [(k, o) for k, origs in zip(df.key, df.duplicate_of) for o in origs if o in created]  # (Jira duplicate, original)
    order = lambda k: (created[k], k)
    pairs = sorted({tuple(sorted(p, key=order)) for p in directed})  # (earlier, later), one per undirected link
    later_is_jira_duplicate = sum((later, earlier) in set(directed) for earlier, later in pairs)
    identical = [(e, l) for e, l in pairs if normalise_summary(summary[e]) == normalise_summary(summary[l])]
    valid = [p for p in pairs if p not in set(identical)]

    golds: dict[str, list[str]] = {}
    for earlier, later in valid:
        golds.setdefault(later, []).append(earlier)

    rows = []
    for q in sorted(golds):
        r = by_key.loc[q]
        gold_all = sorted(golds[q], key=lambda k: (created[k], k))
        rows.append({"kind": "duplicate", "query_key": q, "query_summary": r.summary, "query_description_md": r.description_md,
                     "query_created": r.created.isoformat(), "query_class": r.target_class, "split": r.split,
                     "gold": gold_all[0], "gold_all": gold_all, "gold_summary": summary[gold_all[0]],
                     "corpus_created_before": r.created.isoformat()})

    rng = random.Random(SEED)
    eligible = df[(df.duplicate_of.str.len() == 0) & (df.duplicated_by.str.len() == 0)
                  & (df.resolution != "Duplicate") & (df.created >= NON_DUPLICATE_MIN_CREATED)]
    for q in sample_keys(list(eligible.key), NON_DUPLICATE_QUERIES, rng):
        r = by_key.loc[q]
        rows.append({"kind": "non_duplicate", "query_key": q, "query_summary": r.summary, "query_description_md": r.description_md,
                     "query_created": r.created.isoformat(), "query_class": r.target_class, "split": r.split,
                     "gold": None, "gold_all": [], "gold_summary": None, "corpus_created_before": r.created.isoformat()})

    dup_rows = [r for r in rows if r["kind"] == "duplicate"]
    stats = {
        "directed_links_both_in_main": len(directed),
        "undirected_pairs_both_in_main": len(pairs),
        "pairs_where_jira_duplicate_is_the_later_issue": later_is_jira_duplicate,
        "pairs_where_jira_duplicate_is_the_earlier_issue": len(pairs) - later_is_jira_duplicate,
        "pairs_with_same_created_timestamp": sum(created[e] == created[l] for e, l in pairs),
        "excluded_identical_normalised_summary": len(identical),
        "valid_pairs": len(valid),
        "duplicate_queries": len(dup_rows),
        "queries_with_multiple_gold": sum(len(r["gold_all"]) > 1 for r in dup_rows),
        "non_duplicate_queries": len(rows) - len(dup_rows),
        "non_duplicate_pool": len(eligible),
        "duplicate_queries_by_split": {s: sum(r["split"] == s for r in dup_rows) for s in ("train", "val", "test")},
        "duplicate_queries_by_class": {c: sum(r["query_class"] == c for r in dup_rows) for c in CLASSES},
    }
    return rows, stats


# ---------------------------------------------------------------- c. scope candidates

def build_scope(df: pd.DataFrame) -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    pool = df[df.target_class.isin(["feature", "idea"]) & df.has_description]
    rows, stats = [], {}
    for bucket, (resolutions, k) in SCOPE_BUCKETS.items():
        chosen: list[str] = []
        per_split = {}
        for split in ("test", "val", "train"):  # prefer the frozen test split; top up only if it is too small
            cand = pool[pool.resolution.isin(resolutions) & (pool.split == split) & ~pool.key.isin(chosen)]
            take = sample_keys(list(cand.key), k - len(chosen), rng) if len(chosen) < k else []
            per_split[split] = len(take)
            chosen += take
        stats[bucket] = {"selected": len(chosen), "per_split": per_split,
                         "available_in_test": int((pool.resolution.isin(resolutions) & (pool.split == "test")).sum())}
        for key in chosen:
            r = pool[pool.key == key].iloc[0]
            rows.append({**issue_fields(r), "target_class": r.target_class, "components": list(r.components),
                         "split": r.split, "bucket": bucket, "resolution_hint": r.resolution})
    stats["rows"] = len(rows)
    stats["by_class"] = {c: sum(r["target_class"] == c for r in rows) for c in ("feature", "idea")}
    return rows, stats


# ---------------------------------------------------------------- d. simulator candidates

def build_simulator(df: pd.DataFrame) -> tuple[list[dict], dict]:
    rng = random.Random(SEED)
    test = df[(df.split == "test") & df.has_description].copy()
    test["n_words"] = test.description_md.map(n_words)
    signals = {k: bug_signals(t) for k, t in zip(test.key, test.description_md)}
    test["n_bug_signals"] = [sum(signals[k].values()) if c == "bug" else 0 for k, c in zip(test.key, test.target_class)]
    rows, stats = [], {}
    for cls in CLASSES:
        part = test[test.target_class == cls]
        rich = part[part.n_bug_signals >= 3] if cls == "bug" else part[part.n_words >= SIMULATOR_MIN_WORDS]
        stats[cls] = {"eligible": len(rich), "test_with_description": len(part)}
        for key in sample_keys(list(rich.key), SIMULATOR_CAP, rng):
            r = rich[rich.key == key].iloc[0]
            rows.append({**issue_fields(r), "target_class": cls, "components": list(r.components), "n_words": int(r.n_words),
                         "bug_signals": signals[key] if cls == "bug" else None})
    stats["rows"] = len(rows)
    return rows, stats


# ---------------------------------------------------------------- README

README = """# Evaluation sets (`data/eval/`)

Built by `python src/data/build_eval.py` from `data/processed/issues.parquet` (main dataset, decisions D1–D3,
text cleaned and PII-masked per D5) and the **frozen** `data/processed/splits.json` (seed {seed}).
All text fields are Markdown (`description_md`) and already masked (`<EMAIL>`, `<USER>`). Selections use
`random.Random({seed})` over sorted keys, so rebuilding gives the same files.

| File | Rows | Source | Labels (source) |
|---|---:|---|---|
| `classification_test.jsonl` | {cls_rows} | test split | `labels.target_class` (Jira issue type → D1 mapping), `labels.components` (Jira components) |
| `duplicates.jsonl` | {dup_rows} | whole main dataset | `gold` = the earlier issue of a Jira `Duplicate` link (undirected); `null` for non-duplicate queries |
| `scope_candidates.jsonl` | {scope_rows} | test split first, then val/train | none yet — labelled manually with `src/data/label_cli.py` → `scope_labeled.jsonl` |
| `simulator_candidates.jsonl` | {sim_rows} | test split | none — candidates; the final selection is made later with an LLM |

## classification_test.jsonl
- Test split, at most {cap} issues per class, sampled at random; all idea issues because the class is smaller.
  Per class: {cls_by_class}. Includes {cls_empty} issues with an empty description (summary-only tickets are a real input).
- Fields: `key, summary, description_md, has_description, created, labels{{target_class, components}}, meta{{issuetype, resolution, split}}`.
  `meta.issuetype` is the label source and `meta.resolution` is post-hoc information — **never feed `meta` to a model**.

## duplicates.jsonl
- A Jira `Duplicate` link is treated as **undirected**: of the two linked issues, the **later-created one is the query**
  and the **earlier one is gold** — a user writing a new ticket must find the existing one. Both issues must be in the
  main dataset. ({dup_pairs} linked pairs; in {dup_flipped} of them Jira marks the *earlier* issue as the duplicate, i.e. the
  Jira direction is the opposite of the query direction used here.)
- Retrieval corpus for a query = main-dataset issues with `created < corpus_created_before` (the query's creation time),
  so the gold issue is always in the corpus.
- Exclusion: **{dup_identical} pairs whose normalised summaries are identical** (lower-case, non-alphanumerics removed) — trivial matches.
- {dup_queries} duplicate queries ({dup_multi} are linked to several earlier issues: `gold` = the oldest, `gold_all` = all) and
  {nondup} non-duplicate queries (`gold: null`): issues with no Duplicate link in either direction, not resolved as
  Duplicate, created ≥ 2020-04-01, sampled at random.
- Queries come from all splits (field `split`), because duplicate retrieval is not trained on the classification data.
  Filter on `split == "test"` if a strictly held-out subset is needed ({dup_test} duplicate queries).
- Fields: `kind, query_key, query_summary, query_description_md, query_created, query_class, split, gold, gold_all, gold_summary, corpus_created_before`.

## scope_candidates.jsonl
- 80 resolved feature/idea issues with a non-empty description: {scope_buckets}.
- Drawn from the test split; a bucket is topped up from val, then train, only if the test split is too small (field `split`).
- `resolution_hint` is the Jira resolution — a **hint, not a label**. Labels come from manual annotation
  (`already_supported`, `needs_development`, `out_of_scope`, `insufficient_info`) with `src/data/label_cli.py`.

## simulator_candidates.jsonl
- Test-split issues with rich descriptions: bug = at least 3 of the 4 EDA bug signals (repro, expected, actual,
  version/env; stored in `bug_signals`), other classes = at least {min_words} words. At most {sim_cap} per class.
  Per class (selected / eligible): {sim_by_class}.
- Candidates only; the final selection is made later with an LLM.
"""


def main() -> None:
    df = pd.read_parquet(PROCESSED / "issues.parquet")
    splits = json.loads((PROCESSED / "splits.json").read_text())
    split_of = {k: s for s in ("train", "val", "test") for k in splits[s]}
    df["split"] = df.key.map(split_of)
    assert df.split.notna().all(), "issues.parquet and splits.json disagree"

    EVAL.mkdir(parents=True, exist_ok=True)
    cls_rows, cls_stats = build_classification(df)
    dup_rows, dup_stats = build_duplicates(df)
    scope_rows, scope_stats = build_scope(df)
    sim_rows, sim_stats = build_simulator(df)
    write_jsonl(EVAL / "classification_test.jsonl", cls_rows)
    write_jsonl(EVAL / "duplicates.jsonl", dup_rows)
    write_jsonl(EVAL / "scope_candidates.jsonl", scope_rows)
    write_jsonl(EVAL / "simulator_candidates.jsonl", sim_rows)

    (EVAL / "README.md").write_text(README.format(
        seed=SEED, cap=CLASSIFICATION_CAP, min_words=SIMULATOR_MIN_WORDS, sim_cap=SIMULATOR_CAP,
        cls_rows=cls_stats["rows"], dup_rows=len(dup_rows), scope_rows=scope_stats["rows"], sim_rows=sim_stats["rows"],
        cls_by_class=", ".join(f"{c} {n}" for c, n in cls_stats["by_class"].items()), cls_empty=cls_stats["empty_description"],
        dup_pairs=dup_stats["undirected_pairs_both_in_main"],
        dup_flipped=dup_stats["pairs_where_jira_duplicate_is_the_earlier_issue"], dup_identical=dup_stats["excluded_identical_normalised_summary"],
        dup_queries=dup_stats["duplicate_queries"], dup_multi=dup_stats["queries_with_multiple_gold"],
        nondup=dup_stats["non_duplicate_queries"], dup_test=dup_stats["duplicate_queries_by_split"]["test"],
        scope_buckets=", ".join(f"{b} {scope_stats[b]['selected']} ({' / '.join(SCOPE_BUCKETS[b][0])})" for b in SCOPE_BUCKETS),
        sim_by_class=", ".join(f"{c} {min(SIMULATOR_CAP, sim_stats[c]['eligible'])}/{sim_stats[c]['eligible']}" for c in CLASSES),
    ))
    update_stats("eval", {"classification_test": cls_stats, "duplicates": dup_stats,
                          "scope_candidates": scope_stats, "simulator_candidates": sim_stats})
    print(json.dumps({"classification_test": cls_stats, "duplicates": dup_stats, "scope_candidates": scope_stats,
                      "simulator_candidates": sim_stats}, indent=1))


if __name__ == "__main__":
    main()
