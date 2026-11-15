"""Named, deterministic samples of the val split, shared by evals and labelling tools (VAL ONLY, never test)."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

from src.eval.metrics import CLASSES

ROOT = Path(__file__).resolve().parents[2]
LLM_VAL_PER_CLASS, LLM_VAL_SEED = 100, 42  # mirrors data/eval/classification_test.jsonl (≤100 per class, all idea)
BAKEOFF_PER_CLASS, BAKEOFF_SEED = 10, 42  # scripts/model_bakeoff.py, classification part
HUMAN_PER_CLASS, HUMAN_SEED = 10, 7


def load_split(name: str) -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet")
    splits = json.loads((ROOT / "data" / "processed" / "splits.json").read_text())
    return df[df.key.isin(set(splits[name]))].reset_index(drop=True)


def _per_class_sample(df: pd.DataFrame, per_class: int, seed: int, exclude: set[str] = frozenset()) -> list[str]:
    rng = random.Random(seed)
    keys: list[str] = []
    for cls in CLASSES:
        pool = sorted(set(df[df.target_class == cls].key) - exclude)
        keys += sorted(rng.sample(pool, min(per_class, len(pool))))
    return keys


def llm_val_subset(val: pd.DataFrame) -> list[str]:
    """C1 LLM tuning subset: 100 per class (all idea), seed 42."""
    return _per_class_sample(val, LLM_VAL_PER_CLASS, LLM_VAL_SEED)


def bakeoff_sample(val: pd.DataFrame) -> list[str]:
    """The 40 classification items of the model bake-off (same procedure as scripts/model_bakeoff.py)."""
    return _per_class_sample(val, BAKEOFF_PER_CLASS, BAKEOFF_SEED)


def human_ceiling_sample(val: pd.DataFrame) -> list[str]:
    """40 items (10 per class, seed 7) from the LLM val subset, excluding the bake-off items; shuffled order."""
    subset = val[val.key.isin(set(llm_val_subset(val)))]
    keys = _per_class_sample(subset, HUMAN_PER_CLASS, HUMAN_SEED, exclude=set(bakeoff_sample(val)))
    random.Random(HUMAN_SEED).shuffle(keys)
    return keys


DRIFT_PER_CLASS, DRIFT_SEED = 100, 42


def drift_slice(drift: pd.DataFrame) -> list[str]:
    """C1 drift slice: 100 per class from drift_2026 (all idea: only 3 exist), seed 42."""
    return _per_class_sample(drift, DRIFT_PER_CLASS, DRIFT_SEED)
