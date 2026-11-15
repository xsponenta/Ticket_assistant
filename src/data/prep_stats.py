"""Shared paths and the stats file (data/processed/prep_stats.json) that each preparation step updates.

reports/03_data_preparation.md is rendered from this file by report_prep.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
EVAL = ROOT / "data" / "eval"
STATS_PATH = PROCESSED / "prep_stats.json"
SEED = 42


def update_stats(section: str, values: dict[str, Any]) -> None:
    stats = json.loads(STATS_PATH.read_text()) if STATS_PATH.exists() else {}
    stats[section] = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **values}
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n")


def load_stats() -> dict[str, Any]:
    return json.loads(STATS_PATH.read_text()) if STATS_PATH.exists() else {}
