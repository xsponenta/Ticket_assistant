---
name: llm-judge
description: Decide whether an LLM judge is needed and, if so, build and calibrate it — binary questions, rubric with edge cases in the prompt AND in the calibration CLI, Cohen's kappa >= 0.6, repeat consistency, deterministic metrics preferred. Use for any judge_* prompt, calibration, or "evaluate with an LLM" request.
---

# llm-judge

> Extracted from this project's C3 judges (citation support, chunk relevance; 2026-11-15). Both **failed
> calibration** (κ −0.04 and −0.29), and the rule below was added to AGENTS.md as a result.

## First: can it be deterministic?
- **Prefer deterministic checks:** schema validity, field presence, grounding (`src/eval/spans.py`), regex rule checks, hit@k, invented tokens.
- **What C4, C5, C6 and the e2e evaluation used:** only deterministic metrics, plus human audits where needed (the C4 leak audit, C5 clarity ratings).
- **Use a judge only when nothing deterministic works,** and say why in `decisions.md`.

## If a judge is needed
1. **Prompt** `src/prompts/judge_<name>.md`:
   - a binary question where possible, otherwise an anchored 1–5 rubric;
   - **reasoning before the verdict** (`src/schemas/judge.BinaryJudgement{reasoning, verdict}`);
   - role `judge` (temperature 0; a different model and provider from the generator: `config.yaml`);
   - **a rubric with explicit edge cases:** absence claims ("the docs do not show X": does the closest related chunk "support" it?), partial support, paraphrase.
2. **Calibration set:**
   - at least 30 items per judge, frozen, balanced between the judge's yes and no answers (`judge_label_cli.balanced_sample`);
   - labelled by the user in a CLI that shows **the same rubric** (the `labeling-cli` skill); the judge's answer is hidden.
3. **Report** (`--report`), per judge:
   - Cohen's κ human vs judge, % agreement, human-yes vs judge-yes counts;
   - the disagreement list;
   - **repeat consistency:** an uncached second judge run on the same pairs (`use_cache=False`) → agreement and κ.
4. **Gate:** κ ≥ 0.6 → the judge numbers count. If κ < 0.6:
   - mark every judge-based number **uncalibrated**;
   - diagnose before escalating. A self-consistent judge (high repeat agreement) with a low κ means a **criterion mismatch**, which a stronger model will not fix;
   - only then consider the L2 fallback (strong-tier judge, different provider), with a cost estimate and user approval.
5. **When the user resolves a mismatch** (as in C3: "the judge's stricter reading is the product's definition"), log it in `decisions.md`, keep the measured κ values, and state the annotation limitation.
