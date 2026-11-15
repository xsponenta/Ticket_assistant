---
name: add-component
description: Build a new pipeline component (or a new variant of one) for the Ticket Intake Assistant — schema, versioned prompt, component, deterministic metrics, eval script, dev run, frozen config, single test run, report rows. Use whenever the task is "add/implement/build component Cn" or a new LLM step in src/components/.
---

# add-component

> Extracted from this project's own practice (C1–C6, built on 2026-11-15). It codifies what we actually did,
> including the fixes we needed. It is not a generic template.

## Order of work
1. **Plan first** (CLAUDE.md: plan mode for multi-file tasks). Name the inputs and outputs, the metrics, the eval set, the cost estimate, and the gates.
2. **Schema:** `src/schemas/<cN>.py` (pydantic).
   - Make every key the model must fill **required, with no defaults.** With defaults, structured output silently omits keys: we lost C4 evidence and extraction quotes this way.
   - Put evidence or quote fields *first*.
   - When the fields depend on the class, build the model with `pydantic.create_model(..., __config__=ConfigDict(extra="forbid"))` (see `c4_model`, `draft_model`), so a missing or extra field triggers the repair retry.
   - Field definitions come only from `src/schemas/ticket_types.yaml`, via `src/schemas/ticket_fields.py`.
3. **Prompt:** `src/prompts/<cN_name>.md`, with front matter `version: <name>/vN` and `## system` / `## user` sections. Render it with `src/prompting.load_prompt`. Never put prompt text inline.
   - Write the decision rubric **with explicit edge cases** (absence statements, partial information, paraphrase, information only the assistant said).
   - Bump the version for any change after a saved run.
4. **Component:** `src/components/<name>.py`. One `llm.complete(..., role="generator", component=..., schema=..., max_tokens=...)`.
   - **Always set `max_tokens`.** We once had a 131k-token runaway that cost $0.07 in a single call.
   - Components never import each other; shared helpers go to `src/prompting.py`, `src/schemas/` or `src/eval/spans.py`.
   - **Let code enforce hard rules** that do not need language. For example, C6's `render()` sets the Jira type, "Unknown (reporter)", the assumptions section, and no priority. The LLM writes only text.
5. **Metrics: deterministic first** (AGENTS.md):
   - schema validity, field presence, grounding (`src/eval/spans.py`: `find_spans`, `quote_grounded`, `content_word_share`, `invented_tokens`), rule checks;
   - a judge only where nothing deterministic works (see the `llm-judge` skill).
   - Unit-test every metric on hand-made cases (`tests/test_<cN>.py`), no LLM.
6. **Eval script:** `eval/eval_<cN>.py` with `--split dev|test`, `--limit N` (smoke), `--budget`, `--confirm-test`, `--force`. Follow the `run-eval` skill.
7. **Dev run:**
   - smoke → read the outputs → fix *measurement* bugs (log them);
   - full dev → error analysis (all errors grouped; the ≥ 3 worst with hypotheses);
   - **at most one prompt revision**, and only for a systematic pattern. Never tune on artefacts of the gold.
8. **Stop for approval.** Then write `eval/<cN>_final_config.json` (approved_at, source run, prompt version, role, max_tokens) → `--split test --confirm-test` **once**.
9. **Reports:**
   - `reports/04_modeling.md`: a section with purpose, I/O, design, alternatives, dev and test tables, error analysis;
   - `reports/05_evaluation.md`: one row per run (written by the script);
   - `reports/decisions.md`: every non-trivial choice (date, decision, alternatives, why).
10. **Wrap-up:** ruff (new and changed files) + `python -m pytest -q`. Report what changed, how to run it, what to verify by hand, and the next step; suggest `[phase] <component>: <summary>`.

## Pitfalls we hit
- A prompt or schema fixed after a smoke run is a **smoke fix**; log it, but don't count it as the tuning revision (C4 `c4_gap/v1 → v2`).
- Ablation gold can leak, because deleted information survives elsewhere. Quantify it (C4 audit) before blaming the model.
- When a stage keeps the same name after a failure, loops in tests must stop on `last_error`.
