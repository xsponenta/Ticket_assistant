"""Build the processed issue tables (decisions D1–D3, cleaning per D5).

Inputs : data/raw/spark_issues.jsonl, data/raw/spark_wish_all.jsonl  (wish_other.jsonl is NOT used, D2)
Outputs: data/processed/issues.parquet     main dataset (created before 2026; non-idea from 2020-01-01, idea all history)
         data/processed/drift_2026.parquet  all issues created in 2026 (drift set)
         data/processed/prep_stats.json     counts of every step (section "prepare")

Usage:
    python src/data/prepare.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from clean import HTTP_USERINFO_RE, URL_CREDENTIALS_RE, clean_description, clean_summary
from prep_stats import PROCESSED, RAW, update_stats

# D1: issue type -> target class. Every other type (incl. Sub-task) is excluded.
CLASS_OF = {
    "Bug": "bug",
    "New Feature": "feature", "Improvement": "feature", "Story": "feature",
    "Task": "task", "Test": "task", "Documentation": "task", "Dependency upgrade": "task",
    "Wish": "idea", "Brainstorming": "idea",
}
CLASSES = ["bug", "feature", "task", "idea"]
# D3: main dataset date range for non-idea classes; idea is taken all-time.
MAIN_START = pd.Timestamp("2020-01-01", tz="UTC")
DRIFT_START = pd.Timestamp("2026-01-01", tz="UTC")
COLUMNS = ["key", "created", "issuetype", "target_class", "components", "resolution", "summary",
           "description_md", "has_description", "duplicate_of", "duplicated_by"]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def duplicate_maps(records: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Duplicate link direction (verified in EDA §5): on issue X, outwardIssue Y = 'X duplicates Y'
    (X duplicate, Y original); inwardIssue Y = 'X is duplicated by Y' (Y duplicate, X original)."""
    duplicate_of: dict[str, set[str]] = defaultdict(set)
    duplicated_by: dict[str, set[str]] = defaultdict(set)
    for r in records:
        for link in r["fields"].get("issuelinks") or []:
            if link["type"]["name"] != "Duplicate":
                continue
            if "outwardIssue" in link:
                dup, orig = r["key"], link["outwardIssue"]["key"]
            else:
                dup, orig = link["inwardIssue"]["key"], r["key"]
            duplicate_of[dup].add(orig)
            duplicated_by[orig].add(dup)
    return duplicate_of, duplicated_by


def to_row(r: dict[str, Any], duplicate_of: dict[str, set[str]], duplicated_by: dict[str, set[str]]) -> dict[str, Any]:
    f = r["fields"]
    description_md = clean_description(f.get("description"))
    return {
        "key": r["key"],
        "created": f["created"],
        "issuetype": f["issuetype"]["name"],
        "target_class": CLASS_OF[f["issuetype"]["name"]],
        "components": sorted(c["name"] for c in f.get("components") or []),
        "resolution": (f.get("resolution") or {}).get("name", "Unresolved"),
        "summary": clean_summary(f.get("summary")),
        "description_md": description_md,
        "has_description": bool(description_md),
        "duplicate_of": sorted(duplicate_of.get(r["key"], ())),
        "duplicated_by": sorted(duplicated_by.get(r["key"], ())),
    }


def class_counts(df: pd.DataFrame) -> dict[str, int]:
    return {c: int((df.target_class == c).sum()) for c in CLASSES}


def main() -> None:
    spark = read_jsonl(RAW / "spark_issues.jsonl")
    wish_all = read_jsonl(RAW / "spark_wish_all.jsonl")
    stats: dict[str, Any] = {"raw": {"spark_issues.jsonl": len(spark), "spark_wish_all.jsonl": len(wish_all),
                                     "wish_other.jsonl": "not used (D2)"}}

    # Union by key: SPARK Wish created since 2020 are in both files.
    records = {r["key"]: r for r in spark}
    overlap = sum(r["key"] in records for r in wish_all)
    records.update({r["key"]: r for r in wish_all})
    stats["union"] = {"unique_issues": len(records), "wish_in_both_files": overlap}
    print(f"Loaded {len(spark)} + {len(wish_all)} issues; {len(records)} unique ({overlap} Wish in both files)")

    # D1: mapping
    types = Counter(r["fields"]["issuetype"]["name"] for r in records.values())
    kept = [r for r in records.values() if r["fields"]["issuetype"]["name"] in CLASS_OF]
    stats["d1_mapping"] = {
        "before": len(records), "after": len(kept),
        "kept_by_type": {t: n for t, n in types.most_common() if t in CLASS_OF},
        "excluded_by_type": {t: n for t, n in types.most_common() if t not in CLASS_OF},
    }
    print(f"D1 mapping: {len(records)} -> {len(kept)} (excluded {len(records) - len(kept)})")

    # Clean text + duplicate links (links from all loaded records, so links to excluded types are kept too)
    duplicate_of, duplicated_by = duplicate_maps(list(records.values()))
    df = pd.DataFrame([to_row(r, duplicate_of, duplicated_by) for r in kept], columns=COLUMNS)
    df["created"] = pd.to_datetime(df["created"], utc=True)
    df = df.sort_values(["created", "key"]).reset_index(drop=True)

    # D3: date range. Everything created in 2026 goes to the drift set (all classes, incl. idea);
    # idea has no lower bound (all SPARK Wish history), the other classes start at 2020-01-01.
    is_idea = df.target_class == "idea"
    main_mask = (df.created < DRIFT_START) & (is_idea | (df.created >= MAIN_START))
    drift_mask = df.created >= DRIFT_START
    main, drift = df[main_mask].reset_index(drop=True), df[drift_mask].reset_index(drop=True)
    assert len(main) + len(drift) == len(df), "every kept issue must land in main or drift"
    stats["d3_date_range"] = {
        "before": len(df), "main": len(main), "drift_2026": len(drift),
        "main_by_class": class_counts(main), "drift_by_class": class_counts(drift),
        "main_by_type": main.issuetype.value_counts().to_dict(), "drift_by_type": drift.issuetype.value_counts().to_dict(),
        "idea_before_2020": int((main[main.target_class == "idea"].created < MAIN_START).sum()),
        "idea_in_2026_moved_to_drift": int((drift.target_class == "idea").sum()),
        "main_created_range": [str(main.created.min().date()), str(main.created.max().date())],
    }
    print(f"D3 date range: main {len(main)}, drift_2026 {len(drift)}")

    # Text / link stats
    main_keys = set(main.key)
    raw_desc = {r["key"]: r["fields"].get("description") or "" for r in kept}
    stats["text"] = {
        "main_raw_with_url_credentials": sum(
            bool(URL_CREDENTIALS_RE.search(raw_desc[k]) or HTTP_USERINFO_RE.search(raw_desc[k])) for k in main.key),
        "main_empty_description": int((~main.has_description).sum()),
        "main_empty_description_by_class": {c: int((~main[main.target_class == c].has_description).sum()) for c in CLASSES},
        "main_with_email_mask": int(main.description_md.str.contains("<EMAIL>", regex=False).sum()),
        "main_with_user_mask": int(main.description_md.str.contains("<USER>", regex=False).sum()),
        "main_with_code_block": int(main.description_md.str.contains("```", regex=False).sum()),
        "main_empty_summary": int((main.summary == "").sum()),
    }
    pairs_main = {(k, o) for k, ds in zip(main.key, main.duplicate_of) for o in ds if o in main_keys}
    stats["duplicates"] = {
        "main_issues_with_duplicate_of": int(main.duplicate_of.str.len().gt(0).sum()),
        "main_issues_with_duplicated_by": int(main.duplicated_by.str.len().gt(0).sum()),
        "pairs_both_in_main": len(pairs_main),
    }

    PROCESSED.mkdir(parents=True, exist_ok=True)
    main.to_parquet(PROCESSED / "issues.parquet", index=False)
    drift.to_parquet(PROCESSED / "drift_2026.parquet", index=False)
    update_stats("prepare", stats)
    print(f"Wrote {PROCESSED / 'issues.parquet'} ({len(main)} rows) and {PROCESSED / 'drift_2026.parquet'} ({len(drift)} rows)")
    print("Main by class:", stats["d3_date_range"]["main_by_class"])


if __name__ == "__main__":
    main()
