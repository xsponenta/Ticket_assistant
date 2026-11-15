---
name: crisp-dm-report
description: Update the CRISP-DM reports and decision log of this project — which phase file to edit, how to log decisions, how to record an iteration back to an earlier phase in both reports, and the reporting style. Use after every completed task and whenever a result, decision or iteration must be written up.
---

# crisp-dm-report

> Extracted from how `reports/` was maintained in this project on 2026-11-15 (phases 1–5; the corpus
> iterations for C3; the ablation set; decisions D1–D5, L1–L3, B1–B2, M1–M7, E1–E2).

## Where things go
| Phase | File(s) |
|---|---|
| 1 Business Understanding | `reports/01_business_understanding.md` (targets B1/B2; written after phases 2–3 and logged as an iteration) |
| 2 Data Understanding | `reports/02_data_sanity.md`, `reports/02_data_understanding.md`, `notebooks/eda.ipynb` |
| 3 Data Preparation | `reports/03_data_preparation.md` (**regenerated** by `python src/data/report_prep.py`; edit the generator, not the file), `src/data/*` |
| 4 Modeling | `reports/04_modeling.md`: one section per component + pipeline + end-to-end |
| 5 Evaluation | `reports/05_evaluation.md` (one row per run), `eval/results/*.json` |
| 6 Deployment | `README.md`, `reports/06_deployment.md` |

## Decision log (`reports/decisions.md`)
- **Format:** every non-trivial decision is a table row with: date, decision, alternatives, why (with numbers and the results file).
- **Prefixes:**

  | Prefix | Covers |
  |---|---|
  | D | data |
  | L | LLM / models |
  | B | business targets |
  | M | pipeline / product |
  | E | evaluation sets |

- **Changes:** never delete a decision. Supersede it with a dated entry, and correct wrong statements in place, saying so (e.g. the spot-check attribution).
- **User decisions** are marked as such ("user decision"); post-test fixes are marked "post-test".

## Iterations (going back a phase)
- **When:** a later phase finds a problem in an earlier one (e.g. the doc corpus missed the generated reference tables, found in C3 modelling).
- **Where to log it:** as a "CRISP-DM iteration" in **both** reports — the earlier phase's report (what changed, verified invariants such as "the 2,034 existing chunks are unchanged") **and** the current one (why, effect, before and after) — plus a decisions.md entry.
- **Results:** keep the results of every version and show them side by side (C3: v1 / v2 / v3 corpus).
- **Stopping rule:** respect it if the user sets one ("this is the LAST corpus iteration").

## Style
- **Concise:** numbers over adjectives, with n and CIs. Every claim points to a script, a notebook cell or a results file.
- **Structure for each component section:** purpose → I/O → design → alternatives → dev table → error analysis (all errors grouped, worst-3 with hypotheses) → final config → test table → reading.
- **Honesty:** say plainly when a target is not met (❌), what is an upper or lower bound, what is an artefact of the setup (e.g. self-matches of hidden tickets in C2), and what was not done.
- **After each task:** suggest a commit message `[phase] <component>: <summary>`; never start the next phase unasked.
