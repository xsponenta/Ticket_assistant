"""Test-split lock shared by the component evals: test (and drift) are evaluated ONCE, with an approved config."""

from __future__ import annotations

from pathlib import Path


def check_test_allowed(
    split: str, confirm: bool, force: bool, final_config: Path, results_dir: Path, prefix: str = "c1"
) -> None:
    if split == "val":
        return
    if not confirm:
        raise SystemExit(f"--split {split} needs --confirm-test (final evaluation, run once after val approval).")
    if not final_config.exists():
        raise SystemExit(f"{final_config.name} is missing: it is written after the val results are approved.")
    if not force and list(results_dir.glob(f"{prefix}_{split}_*.json")):
        raise SystemExit(f"{prefix.upper()} was already evaluated on {split} ({prefix}_{split}_*.json); use --force.")
