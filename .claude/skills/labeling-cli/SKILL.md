---
name: labeling-cli
description: Build a terminal tool for the user to label or audit items (scope labels, judge calibration pairs, evidence review, leak audits) — resumable, rubric on screen, model outputs hidden, frozen case set, labels never overwritten. Use whenever a task needs human labels or a human audit.
---

# labeling-cli

> Extracted from the four labelling tools built in this project on 2026-11-15:
> `src/data/label_cli.py` (scope labels), `src/eval/judge_label_cli.py` (C3 judge calibration),
> `src/eval/scope_evidence_cli.py` (supporting-chunk review) and `src/eval/c4_audit_cli.py` (C4 leak audit).
> It also records the mistake that made one of them weaker than it should have been.

## Requirements
1. **A frozen case set.** Sample the cases once (seed 42; stratify where it matters, using proportional allocation with largest remainders, as in `c4_audit_cli.allocate`) and write them to `data/eval/<name>_cases.jsonl` (+ a `_meta.json` with population counts and sources). Reuse them on every start; never resample.
2. **Resumable and append-only.** Answers are appended to `data/eval/<name>_labels.jsonl` (`case_id`, `label`, `labeled_at`) right after each input. On restart, skip the labelled ids. Accept `s` = skip and `q` = quit. **Labels are never overwritten by code.** A label the user wants to change is changed by the user.
3. **The rubric on screen, with edge cases.** Show the exact definition the label means, plus edge cases: absence statements, partial information, paraphrase, information that belongs to another field.
   - **Lesson:** `label_cli` asked for a "supporting chunk" without defining it, and showed only 280-character previews. The supporting chunks turned out to be topical, not evidence. In the C3 judge calibration, the annotator's "support" and the judge's "support" were different criteria (κ −0.04).
   - When the labels calibrate a judge, the **same rubric** must be in the judge prompt (the `llm-judge` skill).
4. **Blind.** Hide model outputs, judge answers, statuses and Jira resolutions unless the task needs them (`label_cli` has an opt-in `--show-hint`). The C4 audit hid C4's status and evidence and showed the deleted text separately as "does not count".
5. **Enough context, clearly separated.** Show the full text the model saw, then what is *not* to be judged, below a rule, then the field definition.
6. **A `--report` mode** that is deterministic: agreement / κ / stratified estimates with bootstrap CIs, written to `eval/results/<name>_<ts>.json`.

## Honesty rules
- Never fill in or "fix" a user's labels. If the user's message still contains template text (e.g. an unfilled bracket), say so; do not treat it as a confirmation.
- Attribute reviews correctly: "reviewed by the assistant" is not "confirmed by the user".
