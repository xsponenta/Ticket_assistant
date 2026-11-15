"""Stratified 70/15/15 train/val/test split of data/processed/issues.parquet (seed 42).

- Stratified by target_class.
- Both sides of a Duplicate link (and any chain of them) go to the same split: issues connected by
  Duplicate links form a group, and whole groups are assigned.
- The test split is FROZEN: if data/processed/splits.json exists, it is verified and never overwritten.

Usage:
    python src/data/split.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from prep_stats import PROCESSED, SEED, update_stats

RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
SPLITS_PATH = PROCESSED / "splits.json"


def duplicate_groups(keys: list[str], links: list[tuple[str, str]]) -> dict[str, str]:
    """Union-find over Duplicate links. Returns key -> group id (smallest key of the group)."""
    parent = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a, b in links:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {k: find(k) for k in keys}


def assign_splits(df: pd.DataFrame, seed: int = SEED) -> dict[str, str]:
    """Return key -> split. Groups are stratified by their majority class (ties: alphabetical)."""
    links = [(k, o) for k, origs in zip(df.key, df.duplicate_of) for o in origs]
    group_of = duplicate_groups(list(df.key), links)
    members: dict[str, list[str]] = {}
    for key in sorted(df.key):
        members.setdefault(group_of[key], []).append(key)
    class_of = dict(zip(df.key, df.target_class))

    by_class: dict[str, list[str]] = {}
    for gid, keys in sorted(members.items()):
        counts = Counter(class_of[k] for k in keys)
        major = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        by_class.setdefault(major, []).append(gid)

    rng = random.Random(seed)
    split_of: dict[str, str] = {}
    for cls in sorted(by_class):
        gids = by_class[cls]
        rng.shuffle(gids)
        total = sum(len(members[g]) for g in gids)
        train_cut, val_cut = round(RATIOS["train"] * total), round((RATIOS["train"] + RATIOS["val"]) * total)
        done = 0
        for g in gids:
            split = "train" if done < train_cut else "val" if done < val_cut else "test"
            for k in members[g]:
                split_of[k] = split
            done += len(members[g])
    return split_of


def test_hash(test_keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(test_keys)).encode()).hexdigest()


def main() -> None:
    df = pd.read_parquet(PROCESSED / "issues.parquet")

    if SPLITS_PATH.exists():
        frozen = json.loads(SPLITS_PATH.read_text())
        ok = test_hash(frozen["test"]) == frozen["test_sha256"]
        missing = set(frozen["train"] + frozen["val"] + frozen["test"]) ^ set(df.key)
        print(f"{SPLITS_PATH} exists and is frozen — not overwritten. Test hash ok: {ok}; "
              f"keys differing from issues.parquet: {len(missing)}")
        sys.exit(0 if ok and not missing else 1)

    split_of = assign_splits(df)
    df["split"] = df.key.map(split_of)

    # Invariant: both sides of every Duplicate pair inside the dataset share a split.
    pairs = [(k, o) for k, origs in zip(df.key, df.duplicate_of) for o in origs if o in split_of]
    crossing = [p for p in pairs if split_of[p[0]] != split_of[p[1]]]
    assert not crossing, f"duplicate pairs crossing splits: {crossing[:5]}"

    counts = pd.crosstab(df.target_class, df.split).reindex(columns=list(RATIOS)).fillna(0).astype(int)
    out = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "data/processed/issues.parquet",
        "seed": SEED,
        "ratios": RATIOS,
        "stratify": "target_class",
        "grouping": "connected components of Duplicate links stay in one split",
        "frozen": True,
        "counts": {s: {c: int(counts.loc[c, s]) for c in counts.index} for s in RATIOS},
        "test_sha256": test_hash([k for k, s in split_of.items() if s == "test"]),
        **{s: sorted(k for k, v in split_of.items() if v == s) for s in RATIOS},
    }
    SPLITS_PATH.write_text(json.dumps(out, indent=1) + "\n")

    group_sizes = Counter(Counter(duplicate_groups(list(df.key), pairs).values()).values())
    update_stats("splits", {
        "counts": out["counts"],
        "totals": {s: len(out[s]) for s in RATIOS},
        "duplicate_pairs_in_dataset": len(pairs),
        "duplicate_groups_size_ge_2": sum(n for size, n in group_sizes.items() if size >= 2),
        "largest_duplicate_group": max(group_sizes),
        "test_sha256": out["test_sha256"],
    })
    print(counts.assign(total=counts.sum(axis=1)))
    print(f"Wrote {SPLITS_PATH}; test split frozen (sha256 {out['test_sha256'][:12]}…)")


if __name__ == "__main__":
    main()
