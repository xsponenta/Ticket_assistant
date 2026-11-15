# 01 · Business Understanding: Ticket Intake Assistant for Apache Spark

_CRISP-DM iteration: this report was **finalised after Data Understanding** (and after data preparation and the model bake-off), so its numbers come from that evidence. Logged in the change log of `reports/decisions.md`. Sources: [`02_data_understanding.md`](02_data_understanding.md) (EDA, SPARK issues created 2020+), [`model_selection.md`](model_selection.md) (bake-off on val), and the [Spark contributing guide](https://spark.apache.org/contributing.html), fetched 2026-11-15._

## Problem
Spark gets "a new JIRA or pull request every few hours": about 3.5–4.7k issues a year in 2020–2025. The contributing guide asks for a descriptive title, a short reproduction for bugs, an Affects Version and detail for features. Unreproducible reports "may be closed". Most tickets fall short of this:

| Evidence (SPARK issues 2020+) | Value |
|---|---:|
| Bug descriptions with all 4 structure elements (reproduction, expected, actual, version/environment) | **3.4%** |
| … that state the expected behaviour explicitly / the actual behaviour explicitly | 19% / 21% |
| Issues with an empty description (Bug 15%, Improvement 30%, Task 33%) | **36.7%** |
| Resolved bugs closed as Incomplete, Duplicate, Invalid, Not A Problem, Cannot Reproduce or Won't Fix | **16.0%** |
| Issues resolved as Duplicate (40% of them with no Duplicate link) | 2.1% (669) |
| SPARK Wish (idea) outcome: Fixed / Incomplete (stale, bulk-closed) / Won't Fix | 10.8% / 19.6% / 16.5% |

Incomplete or duplicate tickets cost committer triage time and delay fixes. Users lose time on tickets that get closed.

## Users
- **Primary:** Spark users (data, ML and platform engineers) who hit a problem or want a change and don't know Spark's Jira conventions.
- **Secondary:** contributors who file a ticket for their own pull request. This is a growing share: the `pull-request-available` label is on 89% of 2026 bugs.
- **Beneficiaries:** committers and triagers who read, deduplicate and resolve tickets.

## Goals
1. **Actionable tickets.** Every required field of the ticket type is confirmed by the user or explicitly marked missing.
2. **Fewer duplicates.** Show likely existing SPARK issues before the ticket is written.
3. **Correct routing.** Point usage questions to user@spark.apache.org, as the guide says. Point large or out-of-scope proposals to dev@ or spark-packages.org.
4. **Low friction.** At most 4 user turns, with at most 2 questions per turn.
5. **No invented facts.** The ticket contains only what the user said, or what is clearly marked as an assumption.

## Scope
- **In scope:**
  - SPARK tickets in English, in four classes;
  - output as Jira-ready Markdown + JSON for the user to paste in;
  - duplicate search over SPARK issues;
  - a scope check against the Spark 4.3.0 docs.
- **Out of scope:**
  - filing tickets automatically (no Jira write access);
  - fixing bugs or writing code;
  - other ASF projects;
  - Sub-tasks, Umbrellas and Epics;
  - setting Priority (Major or below; committers set higher) and Fix Version;
  - security vulnerabilities (redirected to the private security@ process);
  - general support Q&A beyond routing.

## Ticket types
Field definitions, descriptions and Spark-specific examples live in [`src/schemas/ticket_types.yaml`](../src/schemas/ticket_types.yaml), the single source of truth. Every ticket also has `summary`, `component` and optional `labels` (`correctness` / `data-loss`).

| Class (Jira types, D1) | Required fields | Optional |
|---|---|---|
| bug (Bug) | steps_to_reproduce, expected_behavior, actual_behavior, environment (version, API language, deployment) | regression_since, workaround |
| feature (New Feature, Improvement, Story) | motivation, proposed_behavior, acceptance_criteria | alternatives_considered, design_reference |
| task (Task, Test, Documentation, Dependency upgrade) | goal, scope (in/out), definition_of_done | related_issues |
| idea (Wish, Brainstorming) | problem_hypothesis, target_users, expected_impact | open_questions |

## Success criteria (accepted 2026-11-15 with three changes, decision B1)
All are measured on frozen sets in `data/eval/`, with n and bootstrap 95% CIs reported. A metric from the LLM judge counts only after **judge calibration**: agreement with human labels of Cohen's κ ≥ 0.6 on at least 30 items, including a repeat-consistency check.

- **C1 input modes.** C1 is reported in two input modes:
  - **full** (summary + description): the targets apply to this mode;
  - **summary-only**: a proxy for the vague first message a user types in the app, reported for reference.
- **C1 targets were adjusted to the human ceiling (B2).** The user labelled 40 val issues without seeing the Jira type (`python -m src.eval.human_label_cli`) and scored **macro-F1 0.37 (95% CI 0.21–0.50)** and idea recall 0.40 against the Jira labels, below the original targets (0.60 / 0.50). As agreed in B1, **the C1 class targets are 0.37 macro-F1 and 0.40 idea recall**; the component targets are unchanged. How to read this:
  - **Jira types encode Spark's filing conventions, not only our class definitions.** For example, committers file planned API work as Task and test fixes as Bug; outside users file concrete feature requests as Wish (`04_modeling.md`, C1 error analysis).
  - **The task is ambiguous even for a person.** A careful reader using our definitions agrees with Jira on only 35% of items.
  - **So in the product, C1 is a suggestion the user confirms** (decision M1): the UI shows the predicted class and the second most likely one, and the user picks. A C1 error costs one click, not a wrong ticket.
- **C4 and C5** are evaluated on an **ablation set**: rich val/test tickets with 1–2 required fields removed, where gold = the removed fields. **Simulated dialogues are used for end-to-end evaluation only.**

| Component | Eval set (n) | Metric | Initial target | Reference point |
|---|---|---|---|---|
| C1 classifier | classification_test (324), mode **full** (summary-only reported for reference) | macro-F1 · idea recall | **≥ 0.37 · ≥ 0.40** (set to the human ceiling, B2; originally 0.60 · 0.50) | human vs Jira 0.37 [0.21–0.50], idea recall 0.40 (val, n = 40); zero-shot bake-off 0.36–0.44 |
| C1 component | same, mode full | top-1 / top-3 accuracy | ≥ 0.60 / ≥ 0.85 | majority class (SQL) ≈ 0.43 |
| C2 duplicate finder | duplicates (148 duplicate + 100 non-duplicate queries) | Recall@5 · MRR · false alarms on non-duplicates | ≥ 0.60 · ≥ 0.45 · ≤ 0.20 | BM25-only baseline |
| C3 scope checker | scope_labeled (80, manual labels) | accuracy · cited chunk supports the verdict | ≥ 0.65 · ≥ 0.80 | majority label `already_supported`: accuracy 0.525 (80 manual labels) |
| C4 gap detector | **ablation set** (rich val/test tickets, 1–2 required fields removed; gold = removed fields; to be built) | recall of the removed fields · false "confirmed" rate | ≥ 0.90 · ≤ 0.05 | — |
| C5 question generator | same ablation set | ≤ 2 questions per turn · each question targets a removed required field | 100% · ≥ 0.90 | — |
| C6 ticket composer | composed tickets | schema-valid · confirmed required fields present · unsupported claims | 100% · 100% · ≤ 5% | grounding check + judge |
| End-to-end | 60 simulated dialogues (the only place they are used); drift-2026 slice reported separately | required-field completeness · fact recall · hallucinated facts · user turns · cost · p95 latency per turn | ≥ 0.90 · ≥ 0.80 · ≤ 5% of claims · ≤ 4 · ≤ $0.01 per ticket · ≤ 8 s | real bugs with all 4 elements: 3.4% |

Business proxy: at least 90% of assistant-produced bug tickets contain all four structure elements, compared with 3.4% in SPARK history.

## Risks and mitigations
| Risk | Evidence | Mitigation |
|---|---|---|
| Labels overlap between idea, feature and task | Bake-off: no configuration predicted *idea* correctly (82% of idea predictions went to *feature*); 18 of 40 val items wrong for every model; *task* was over-predicted for bugs (31%) and features (26%). The contributing guide: "generally, Bug, Improvement and New Feature are the only types used". | The user confirms the class (C1 shows its top-2, M1); targets set to the human ceiling (B2); idea errors reported separately. Imitating Jira conventions in the prompt was rejected (it would contradict our definitions). |
| Small idea class | 162 in main, **24 in test**; 72% are from before 2020. | Bootstrap CIs (mandatory); no resampling (D4); per-class reporting. |
| LLM-judge bias | The judge is a "lite" model; at temperature 0 it misread one of 11 ping calls; no strong-tier model was tested. | Judge from a different provider than the generator; calibration against human labels plus a repeat check; binary or anchored rubrics; switch to a strong judge if κ < 0.6 (L2). |
| 2026 drift | 2026 bug descriptions: median 114 words (vs 50–93), Jira headings 11.6% (vs ≤ 3.6%), root-cause / fix sections 11.4%, PR label 89%, Connect component 30%. | 2026 kept as a separate drift set (D3) and reported as its own slice. |
| Simulator realism | An invented fact would corrupt fact recall and the hallucination metric. | Simulator chosen for honesty (5/5 on the not-in-ticket question, L2); transcripts spot-checked. |
| Residual personal data | Names in free text are not masked (D5). | Rule-based masking now; spot checks; no free text in logs. |
