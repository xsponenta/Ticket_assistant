---
name: run-eval
description: Run or write an evaluation in this project (component eval, end-to-end, judge calibration) — smoke run, cost projection, budget guard, full run, results JSON with git commit, worst examples, frozen sets and the one-time test lock. Use before any `eval/eval_*.py` run, when adding a new eval script, or when someone asks to "run test".
---

# run-eval

> Extracted from how the evals for C1–C6 and the end-to-end run were done in this project (2026-11-15).

## Rules (AGENTS.md, as practised)
- **Frozen sets are never edited** to improve a score: `data/processed/splits.json` and everything in `data/eval/`, including the ablation set (`gap_ablation.jsonl`, hash in `gap_ablation_meta.json`), the scope split and the calibration pairs.
- **Never tune on test.** Few-shot examples, thresholds, prompts and k come from train/val/dev.
- **Test runs once,** via `src/eval/lock.check_test_allowed(split, confirm, force, final_config, results_dir, prefix)`. It needs `eval/<c>_final_config.json`, written only after the user approves the dev results, plus `--confirm-test`. A second test run needs `--force` and a reason.
- **A fix after test is a post-test fix** (e.g. M7). Rerun only the affected items with a separate label (`eval_e2e.py --keys`) and never replace the test numbers.

## Procedure
1. **Estimate before running.**
   - Get calls × tokens × price from `logs/llm_calls.jsonl` (`python -m src.llm --stats`, or per-model averages from earlier runs).
   - If a run has > 300 LLM calls or projects > $1: report the estimate and wait for approval.
2. **Smoke:** `--limit N` (5–20 items). The script prints the projected full cost from the uncached spend.
   - **Read the outputs yourself.** Most of our early problems were measurement bugs: backtick pairing, generic nouns counted as invented, a too-narrow "don't know" regex, cache-shared latency.
3. **Full run under a budget guard:** `Budget(limit, log_path, prefix)` from `src/eval/run_log.py`. Stop when exceeded; never silently continue.
   - Parallelise with `ThreadPoolExecutor(4–8)`; `llm.complete` is thread-safe.
   - Session ids `<comp>|<split>|<prompt version>|<item>` keep cost attribution clean.
4. **Results file:** `eval/results/<comp>_<split>[_smoke]_<UTC ts>.json`. It must contain:
   - metrics (with n and bootstrap 95% CIs from `src/eval/metrics.py`; mandatory for small classes);
   - models, prompt versions, the git commit (`git rev-parse HEAD`; the e2e lock refuses to run if HEAD differs from the config);
   - per-item outputs, so metrics can be recomputed (`--rescore`).
5. **Reporting:**
   - one row in `reports/05_evaluation.md` (date, component, metric, value, n, model, prompt version, note), written by the script for dev and test;
   - error analysis in `04_modeling.md`: **all** errors grouped by cause, and the **≥ 3 worst examples with a hypothesis each**. Separate system errors from gold or simulator artefacts.
6. **Caching:** identical requests hit the disk cache. Latency and cost must come from the uncached (first) run; e2e reports them from policy auto only.

## Checklist before saying "done"
- [ ] smoke read, measurement fixes logged
- [ ] projection ≤ budget, or approval given
- [ ] results JSON has the commit, the prompt versions, the per-item outputs
- [ ] 05 row(s), 04 analysis with worst-3
- [ ] ruff + pytest
