# 04 · Modeling

_One section per component (AGENTS.md). Decisions are logged in [`decisions.md`](decisions.md); evaluation rows are in [`05_evaluation.md`](05_evaluation.md)._

> **CRISP-DM iteration.** Phase 1 ([`01_business_understanding.md`](01_business_understanding.md)) was written **after** Phases 2–3 and the model bake-off ([`model_selection.md`](model_selection.md)). Its problem statement, targets and risks therefore rest on EDA and bake-off evidence. The success targets were then accepted with three changes (decision B1). Logged in the change log of `decisions.md`.

## Shared infrastructure
- **LLM calls:** only through `src/llm.py`. Models per role come from `config.yaml` (L2):
  - generator: `deepseek/deepseek-v4.1-flash-1017`, reasoning off, temperature 0;
  - judge: `google/gemini-3.5-flash-lite`;
  - simulator: `qwen/qwen3.5-27b`.
- **Prompts:** `src/prompts/<component>.md`, each with a `version` header, loaded by `src/prompting.py`.
- **I/O schemas:** pydantic models in `src/schemas/`. Ticket fields come from `src/schemas/ticket_types.yaml`.
- **Eval helpers:** `src/eval/metrics.py` (metrics, bootstrap CIs, Cohen's κ), `src/eval/samples.py` (named val/drift samples) and `src/eval/run_log.py` (cost, latency and budget from `logs/llm_calls.jsonl`).

## C1 · Classifier

**Purpose:** predict the ticket class (bug / feature / task / idea, decision D1) and the Spark component from the user's text. This selects the field schema for C4–C6 and pre-fills `component`.

**Input:** `C1Input{summary, description}` in one of two modes (B1):
- **full** = summary + first 1,500 characters of the description;
- **summary-only** = summary. This is a proxy for the vague first user message.

The targets apply to *full*; *summary-only* is reported for reference.

**Output:** `C1Output{rationale, class, component[1–3, most likely first], confidence ∈ [0, 1]}` (`src/schemas/c1.py`).
- Components are the top 15 of TRAIN plus `other`, which together cover 96% of train issues.
- An issue's gold set = its Jira components, mapped to these 16 labels.
- A top-k hit = any of the first k predicted components is in the gold set.

**Variants**

| | Baseline (`src/components/classifier_baseline.py`) | LLM (`src/components/classifier.py`) |
|---|---|---|
| Class model | TF-IDF word 1–2 + char_wb 3–5 → `LogisticRegression(class_weight="balanced")`; C tuned on val (macro-F1) | One call to the generator; class definitions from `ticket_types.yaml`; prompt `c1_classifier/v1` |
| Component | One-vs-rest LogisticRegression over the 16 labels, ranked by probability; C tuned on val (top-1) | Ranked list (1–3) in the same call |
| Context | Trained on TRAIN | **Dynamic few-shot**: the k nearest TRAIN issues **per class** (TF-IDF cosine); k ∈ {0, 2, 4} tuned on val |
| Model calls | 0 | 1 per ticket, schema-validated (`json_schema` mode), one repair retry |

**Choices and alternatives**
- **Few-shot from TRAIN, chosen per class.** This guarantees idea examples in every prompt; zero-shot never predicted idea correctly in the bake-off.
  - Alternative: k nearest overall. Rejected because idea is 1.1% of train, so it would almost never be shown.
- **k tuned on a 325-item val subset** (100 per class + all 25 idea; it mirrors `classification_test`). The smallest k within 0.01 macro-F1 of the best is chosen, because it is cheaper.
  - Alternative: the full val (2,249). Rejected: about 7× the cost for little gain in precision on the rare classes.
- **Baseline trained on TRAIN only**, even for the final run, so it is comparable with the LLM, whose examples come only from TRAIN.
  - Alternative: refit on train + val. Rejected: it changes what the test result measures.
- **Test and drift are evaluated once**, after approval of the val results. `eval/eval_c1.py` refuses to run them without `--confirm-test` and `eval/c1_final_config.json`, and refuses a second run.

### C1 val results (tuning; `eval/results/c1_val_20261115T135541Z.json`)

Val only; test has not been touched. LLM spend $0.22 (1,950 calls + smoke run $0.02). Confusion matrices: `reports/figures/c1_{baseline,llm}_{full,summary}_val.png`.

**Tuning**

| Variant | Mode | Grid (val macro-F1) | Chosen |
|---|---|---|---|
| Baseline | full | C 0.1: 0.530 · 0.3: 0.563 · **1: 0.567** · 3: 0.561 · 10: 0.558 (all val, n = 2,249) | C = 1; component C = 10 (top-1 0.738; plateau from C = 3) |
| Baseline | summary | C 0.1: 0.484 · **0.3: 0.491** · 1: 0.490 · 3: 0.483 · 10: 0.481 | C = 0.3; component C = 3 |
| LLM | full | k 0: 0.459 · **2: 0.523** · 4: 0.477 (n = 325) | k = 2 per class (8 examples) |
| LLM | summary | k 0: 0.470 · 2: 0.456 · **4: 0.482** | k = 4 per class (16 examples) |

The differences between values of k (≤ 0.064) are within the bootstrap CIs (about ±0.06), and they are not monotonic. Few-shot examples help a little at best.

**Both variants on the same 325 val items** (100 per class, all 25 idea)

| Variant · mode | Macro-F1 [95% CI] | Accuracy | Idea recall [CI] | P/R bug · feature · task · idea | Component top-1 / top-3 | Latency | Cost / 100 calls |
|---|---:|---:|---:|---|---:|---:|---:|
| **Baseline · full** | **0.561** [0.49–0.62] | 0.597 | 0.28 [0.12–0.47] | .67/.73 · .47/.67 · .71/.47 · .88/.28 | **0.73 / 0.93** | 0.3 ms | $0 |
| LLM · full (k = 2) | 0.523 [0.46–0.59] | 0.585 | 0.20 [0.07–0.37] | .73/.75 · .47/.46 · .56/.64 · .56/.20 | 0.72 / 0.81 | p50 1.0 s, p95 2.3 s | $0.015 |
| Baseline · summary | 0.512 [0.45–0.57] | 0.585 | 0.16 [0.03–0.32] | .63/.72 · .50/.59 · .66/.55 · .44/.16 | 0.70 / 0.93 | < 0.1 ms | $0 |
| LLM · summary (k = 4) | 0.482 [0.42–0.54] | 0.541 | 0.16 [0.04–0.32] | .73/.66 · .44/.49 · .50/.57 · .50/.16 | 0.67 / 0.79 | p50 1.0 s, p95 2.0 s | $0.011 |

- **The baseline is at least as good as the LLM** on every Jira-based metric, at zero cost and about 3,000× lower latency. The macro-F1 CIs overlap, so the gap (0.04) is not significant at n = 325.
- **Component:** top-1 is similar for both (0.72–0.73). Top-3 is clearly better for the baseline (0.93 vs 0.81), because the LLM returns a single component for 62% of items and three for only 2%, so its top-3 is mostly a top-1.
- **Summary-only** costs both variants about 0.05 macro-F1. The vague first message is harder, as expected.
- **Against the targets (B2: macro-F1 ≥ 0.37, idea recall ≥ 0.40; component top-1 ≥ 0.60, top-3 ≥ 0.85):** both variants meet macro-F1 and component top-1. Neither meets idea recall (0.28 / 0.20). Only the baseline meets component top-3.

**Human ceiling** (same 40 val items, mode full, Jira type hidden; decision B2)

| On the 40 items | Macro-F1 vs Jira | Accuracy vs Jira | Agreement with the user (κ) |
|---|---:|---:|---:|
| User (human) | 0.370 [0.21–0.50] | 0.35 | — |
| Baseline · full | 0.522 | 0.525 | 38% (κ 0.16) |
| LLM · full (k = 2) | 0.560 | 0.575 | 50% (κ 0.31) |

The user labelled 16 of 40 items *task*: 6 of 10 Jira features and 5 of 10 Jira bugs. Both models agree with Jira more than the user does, and the LLM agrees with the user more than the baseline does. This suggests the models (especially the baseline) partly learn Spark's **filing conventions**, while the user applies the **class definitions**. The C1 class targets were set to the human ceiling (B2).

**How to read C1's scores.**
- **Jira types encode Spark's filing conventions, not only our class definitions.** "Error" here partly means "did not imitate the convention".
- **The task is ambiguous even for a person** (human vs Jira: 0.37).
- **So in the product, C1 is a suggestion the user confirms** (M1), and its errors are cheap: one click in the UI, not a wrong ticket.

### C1 error analysis: 10 worst val errors (LLM · full · k = 2)

Wrong predictions ranked by the LLM's stated confidence, with idea↔feature and bug→task forced in. "Baseline" is the baseline's prediction for the same item.

| Key | Jira (type) | LLM (conf.) | Baseline | Hypothesis |
|---|---|---|---|---|
| SPARK-21785 | idea (Wish) | feature (0.95) | feature | A concrete request ("Support create table from a file schema", with SQL syntax) filed as a Wish. The LLM follows the definition; **label convention**: outside users file feature requests as Wish. |
| SPARK-11882 | idea (Wish) | feature (0.90) | idea | A concrete design (`spark.scheduler.factory.<name>`), filed as a Wish in 2015. The user also says *feature*. Convention again; the baseline gets it from old-Wish vocabulary. |
| SPARK-15504 | idea (Wish) | feature (0.90) | idea | Phrased as a question ("Could … support …?"), a typical Wish of the MLlib era. Question form + an old API is the baseline's cue; the LLM reads the request, not the tone. |
| SPARK-44212 | bug (Bug) | task (1.00) | bug | A dependency upgrade for a CVE, which the definition lists under *task*. Spark files CVE upgrades that break integrations as Bug. **Definition vs convention**; the confidence of 1.0 is overconfident. |
| SPARK-31050 | bug (Bug) | task (0.90) | task | "Disable flaky KafkaDelegationTokenSuite". Spark mostly files test failures as Bug, but its few-shot neighbours (flaky-test tickets labelled task) pushed it to task. **Inconsistent labels in TRAIN** also leak in through the examples. |
| SPARK-32006 | bug (Bug) | task (0.90) | feature | A performance regression against Spark 2.4, described as a refactor ("create formatters once"). **Genuine model error**: the guide says a performance regression is a bug, and the prompt's bug definition does not say so. |
| SPARK-38063 | task (Task) | feature (0.97) | feature | A new SQL function (`split_part`) with a specification, filed as a Task, likely as planned work under an umbrella. Both models say *feature*: **label convention** for planned work. |
| SPARK-38318 | task (Task) | bug (0.97) | bug | A clear regression ("works in 3.1, fails in 3.2"), filed as a Task. **Label noise**: both models say *bug*; the user said *feature*. |
| SPARK-34214 | task (Task) | feature (0.95) | feature | "Expose regexp_extract_all to PySpark", API-parity work filed as a Task. **Convention**: parity work is planned as Tasks. |
| SPARK-34552 | feature (Improvement) | bug (0.95) | bug | Inconsistent metadata between two catalog APIs. Genuinely **ambiguous** (bug or improvement); a committer chose Improvement. |

**Pattern:**
- 8 of the 10 "errors" are cases where the prediction follows the definitions and Jira follows Spark's filing conventions or contains noise.
- 1 is a genuine model error (performance regression), and 1 is ambiguous.
- The LLM states 0.90–1.00 confidence on all 10, so its **confidence is not calibrated** and must not be used as a routing threshold without calibration.

**Iteration considered and rejected: prompt v2 tuned to the errors.**
- **Proposal:** a `c1_classifier/v2` with Spark's conventions added to the class definitions, e.g. "flaky-test fixes and CVE upgrades are bugs", "planned API-parity work is a task", "concrete requests from users may be Wishes".
- **Rejected (2026-11-15, user decision):**
  - 8 of the 10 worst errors are Jira filing conventions, not misreadings of the text.
  - Tuning the prompt to imitate them would **overfit val**: the conventions are inconsistent even within TRAIN (flaky-test tickets are labelled both bug and task).
  - It would also **contradict our own class definitions**, which are what the user sees and confirms in the app.
- **Kept:** `c1_classifier/v1` and the definitions in `ticket_types.yaml` unchanged.
- **Not pursued now, for the same reason:** adding "a performance regression is a bug" (the one genuine error), and asking the LLM for exactly 3 components.

### C1 proposed final configurations (for test and drift, after approval)

| Variant | Mode full | Mode summary |
|---|---|---|
| Baseline | class C = 1, component C = 10 | class C = 0.3, component C = 3 |
| LLM (`c1_classifier/v1`) | k = 2 per class | k = 4 per class |

Approved by the user on 2026-11-15 and frozen in `eval/c1_final_config.json`.

### C1 pipeline decision (M1)
- **In the app, C1 = the baseline.** It is free, takes 0.3 ms, and has the best component top-3 (0.93), with macro-F1 equal to or better than the LLM.
- **The UI** shows the predicted class **plus the second most likely class** (from the class probabilities), and the user confirms one.
- **Components:** the top 3 are pre-filled for the user to confirm.
- **The LLM variant** remains the evaluated alternative. It has a rationale and agrees more with the human, but it is not used in the pipeline.

### C1 test and drift results (final configs, evaluated once)
Results: `eval/results/c1_test_20261115T140317Z.json` and `c1_drift_20261115T140546Z.json`.
- **Sets:** `classification_test.jsonl` (324: 100/100/100/24) and the drift slice (303: 100 per class + all 3 idea issues of 2026).
- **Spend:** LLM $0.18. Confusion matrices: `reports/figures/c1_*_{test,drift}.png`.

**Test (both variants on the same 324 items)**

| Variant · mode | Macro-F1 [95% CI] | Accuracy | Idea recall [CI] | P/R bug · feature · task · idea | Component top-1 / top-3 |
|---|---:|---:|---:|---|---:|
| Baseline · full (M1) | 0.542 [0.47–0.61] | 0.614 | 0.17 [0.04–0.32] | .66/.76 · .50/.72 · .78/.47 · 1.00/.17 | 0.73 / **0.94** |
| LLM · full (k = 2) | **0.571** [0.51–0.63] | 0.657 | 0.17 [0.04–0.33] | .72/.78 · .60/.58 · .65/.73 · .57/.17 | **0.76** / 0.86 |
| Baseline · summary | 0.509 [0.45–0.57] | 0.580 | 0.17 [0.03–0.31] | .63/.72 · .50/.59 · .65/.53 · .44/.17 | 0.72 / 0.95 |
| LLM · summary (k = 4) | 0.537 [0.48–0.60] | 0.645 | 0.08 [0.00–0.22] | .75/.69 · .58/.63 · .62/.75 · .50/.08 | 0.77 / 0.84 |

LLM cost and latency on test: $0.016 per 100 calls (full) / $0.012 (summary); p50 1.06 s, p95 1.9–2.2 s. Baseline: $0, under 1 ms.

**Drift 2026** (same 303 items). Macro-F1 over 4 classes is pulled down by idea, which has only 3 items, so the 3-class value is the meaningful one.

| Variant · mode | Macro-F1 (4 classes) | **Macro-F1 (bug/feature/task) [CI]** | Accuracy | Component top-1 / top-3 |
|---|---:|---:|---:|---:|
| Baseline · full | 0.472 | 0.632 [0.58–0.69] | 0.627 | 0.64 / 0.93 |
| LLM · full | 0.520 | **0.697** [0.65–0.74] | 0.693 | 0.71 / 0.84 |
| Baseline · summary | 0.507 | 0.680 [0.63–0.73] | 0.667 | 0.63 / 0.91 |
| LLM · summary | 0.444 | 0.595 [0.54–0.65] | 0.581 | 0.70 / 0.82 |

**Against the targets** (mode full, test; B2):

| Target | Baseline | LLM |
|---|---|---|
| Macro-F1 ≥ 0.37 | met (0.542) | met (0.571) |
| Idea recall ≥ 0.40 | **not met** (0.17, CI 0.04–0.32) | **not met** (0.17) |
| Component top-1 ≥ 0.60 | met (0.73) | met (0.76) |
| Component top-3 ≥ 0.85 | met (0.94) | met (0.86) |

**What changed from val, and why the decision stands**
- **The ranking flipped:** on val the baseline led (0.561 vs 0.523); on test the LLM leads (0.571 vs 0.542). Both gaps are within the CIs (n ≈ 325), so the two variants are **not distinguishable on class quality**.
- **Component:** the baseline keeps the clearly better top-3 (0.94 vs 0.86); the LLM has a slightly better top-1.
- **Drift 2026, mode full:** the LLM generalises better (3-class 0.70 vs 0.63; CIs overlap slightly). The baseline's component top-1 drops from 0.73 to 0.64, probably because the Connect / Rust-client vocabulary of 2026 is new to the TF-IDF model. In summary-only mode it is the other way round.
- **M1 stays as decided on val.** Changing the choice because of test results would be test-set selection. M1's reasons still hold: free, under 1 ms, best component top-3, and errors are cheap because the user confirms the class.
- **Recorded as a consideration for a later iteration, decided on val or a new drift slice and not on test:** an LLM fallback when the baseline is uncertain, which might help on new vocabulary such as 2026's.
- **Idea recall (0.17) misses its target in both variants.** With 24 idea items the CI is wide (0.04–0.33).
  - **The top-2 display (M1) helps, but only partly.** Baseline top-2 recall on test is bug 0.93, feature 0.96, task 0.87 and **idea 0.42** (top-1: 0.17), roughly the human ceiling (0.40). Still, 58% of idea tickets are not in the top 2.
  - **Implication for the UI:** besides the two suggestions, the user must be able to pick any of the four classes.

## C2 · Duplicate finder

**Purpose:** show likely existing SPARK issues while the user writes a ticket (goal 2), and raise a "possible duplicate" alert. No LLM calls.

**Input:** draft `summary` and `description`, in mode full (summary + first 1,500 characters of the description) or summary-only. **Output:** `C2Output{candidates: top-5 {key, summary, url, score}, alert, alert_score}` (`src/schemas/c2.py`).

**Retrieval** (`src/retrieval/`, corpus-agnostic, reused by C3):
- `bm25.py`: sparse-matrix Okapi BM25;
- `dense.py`: sentence-transformers on CPU, with each model's own prefixes and cached corpus embeddings;
- `hybrid.py`: RRF, k = 60, over the top 100 of each ranking;
- `text.py`: tokenizer and Jira-key masking.

The component is `src/components/duplicate_finder.py`.

**Corpus and time correctness:**
- Index = the main dataset (14,989 issues).
- For each query, only issues created **before** it are candidates, and never the query itself (unit-tested).
- **Jira keys** (`SPARK-123`, `HIVE-45`, …) are masked as `<ISSUE>` in queries and docs.
- BM25 IDF uses the whole corpus, a documented approximation; in the app every indexed issue is older than the draft.

**Evaluation sets** (`data/eval/duplicates.jsonl`; selection on **train + val only**):
- 113 duplicate queries; 84 non-duplicate queries.
- A hit = any gold issue (`gold_all`); MRR = MRR@100.
- Test (35 duplicate + 16 non-duplicate queries) is locked until approval.
- Results: `eval/results/c2_embedders_20261115T145110Z.json` and `c2_variants_20261115T145643Z.json`.

**Embedder (L3):**
- `BAAI/bge-small-en-v1.5`, dense MRR 0.632, ahead of all-MiniLM-L6-v2 (0.570) and e5-small-v2 (0.547).
- Also best in summary-only mode (0.536).
- Query p50 14 ms on CPU; corpus encoding 197 s once, then cached.

**Variants** (train + val, 113 duplicate queries; recall curves in `reports/figures/c2_recall_trainval.png`):

| Variant · mode | MRR [95% CI] | R@1 | R@5 | R@10 | Not in top 100 | Latency p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 · full | 0.461 [0.38–0.54] | 0.37 | 0.56 | 0.69 | 16 | 1.1 / 1.6 ms |
| **dense · full** | **0.632** [0.55–0.71] | **0.56** | 0.72 | **0.79** | 11 | 11 / 35 ms |
| hybrid (RRF) · full | 0.569 [0.49–0.64] | 0.43 | **0.73** | 0.78 | 11 | 13 / 37 ms |
| BM25 · summary | 0.454 [0.38–0.54] | 0.36 | 0.58 | 0.65 | 17 | 0.8 / 1.0 ms |
| dense · summary | 0.536 [0.46–0.62] | 0.44 | 0.66 | 0.74 | 12 | 6 / 7 ms |
| hybrid · summary | 0.531 [0.45–0.61] | 0.42 | 0.67 | 0.75 | 10 | 7 / 8 ms |

- **Dense beats hybrid on MRR.** Hybrid matches dense at R@5 (0.73 vs 0.72) but loses at R@1 (0.43 vs 0.56): BM25 promotes lexically similar non-duplicates, such as other flaky-test tickets, to the top. MRR is the selection metric, so **dense** is chosen.
- **Summary-only** costs 0.10 MRR: a short first message finds fewer duplicates.
- **Targets (B1): met in mode full.** R@5 0.72 ≥ 0.60 and MRR 0.632 ≥ 0.45. False alarms ≤ 0.20 holds by construction of the threshold.

**Jira-key masking** (as requested):
- Only **7 of the 113** train+val duplicate queries cite a Jira key that their gold also cites.
- Sensitivity check: hybrid MRR in mode full is **0.571 with keys unmasked**, vs 0.569 masked.
- So the key shortcut is rare here, and masking costs nothing.

**Alert threshold:**
- **alert_score** = the dense cosine of the top-1 candidate.
- **Threshold:** the one that maximises alert recall subject to false alarms ≤ 0.20 on the 84 train+val non-duplicate queries, **chosen per mode**. Summary-only queries score lower cosines, so the full-mode threshold would leave summary-only with alert recall 0.27.

| Mode | Threshold | Alert recall | Alert precision* | False-alarm rate | Useful alert (alert + gold in top 5) |
|---|---:|---:|---:|---:|---:|
| full | 0.839 | 0.57 | 0.80 | 0.19 | 0.44 |
| summary | 0.821 | 0.40 | 0.75 | 0.18 | 0.34 |

\*The eval set is 57% duplicates, while real traffic is about 2% (EDA), so precision here is optimistic; the false-alarm rate is the operational number. In the app the top 5 are always shown; the alert only decides whether to highlight them.

### C2 error analysis: 10 worst misses (dense · full · train+val)
In all 10, the gold issue is not in the top 100 for any variant (except one where BM25 ranks it 58th).

| Query → gold | Hypothesis |
|---|---|
| SPARK-31928 "Flaky test: StreamingDeduplicationSuite…" → SPARK-31593 "Remove unnecessary streaming query progress update" | **Root-cause link, not the same text**: the flaky test is the symptom, the gold is the code change that caused it. Top-1 is another flaky-test ticket. |
| SPARK-32690 "Spark-32550 affects the performance of some cases" → SPARK-32550 | **A regression report about the gold change**, linked only through the cited key (written "Spark-32550"; the gold's own text never contains its key). A follow-up, not a duplicate. |
| SPARK-35108 "Pickle produces incorrect key labels for GenericRowWithSchema" → SPARK-34545 "PySpark Python UDF return inconsistent results…" | **Same root cause, different symptoms** (pickling vs UDF results); no shared wording. |
| SPARK-36440 "Spark3 fails to read hive table with mixed format" → SPARK-36197 "InputFormat of PartitionDesc is not respected" | **User symptom vs developer root-cause wording** ("mixed format" vs "PartitionDesc / InputFormat"). |
| SPARK-38218 "…wrong package on the downloads page… hadoop3.3 vs hadoop3.2" → SPARK-37445 "Update hadoop-profile" | **Terse task as gold** (one line). Top-1 SPARK-37068 "Confusing tgz filename for download" is plausibly an *unlinked* duplicate, so the label is incomplete. |
| SPARK-38514 "Download link on spark 3.2.1 for hadoop 3.2 is wrong" → SPARK-37445 | Same as above: same terse gold, and the same plausible unlinked top-1 (SPARK-37068). |
| SPARK-39551 "Add AQE invalid plan check" → SPARK-39447 "Only non-broadcast query stage can propagate empty relation" | **Gold has an empty description** and a narrow summary; the relation is "fixed by", not the same report. |
| SPARK-40706 "IllegalStateException when querying array values inside a nested struct" → SPARK-39854 "ColumnPruning … explode" | **Root-cause link.** Top-1 SPARK-37855 "IllegalStateException when transforming an array inside a nested struct" looks like an unlinked duplicate (**incomplete labels**). |
| SPARK-42049 "Improve AliasAwareOutputExpression" → SPARK-41793 "Incorrect result for window frames … large decimals" | **Likely a wrong or loose link:** no topical overlap. Top-1 SPARK-39397 "Relax AliasAwareOutputExpression…" is the topically right issue. |
| SPARK-44764 "Streaming Python process management improvement" → 3 tasks of the Spark Connect streaming-listener work | **Gold = sibling tasks under one umbrella**; the relation is "same project", not "same request". |

**Pattern:**
- Most misses are **relation links** (root cause, "fixed by", regression of, sibling tasks), not tickets that describe the same request. Text similarity cannot find them, and the user writing a new ticket would not know them.
- In 3 cases the top-1 is a plausible **unlinked duplicate**, so the measured recall is a lower bound.
- Not pursued: tuning on these cases would fit the link conventions, not duplicate detection.

### C2 proposed final configuration (for the one-time test run, after approval)

| Setting | Value |
|---|---|
| Variant | **dense** |
| Embedder | `BAAI/bge-small-en-v1.5` (L3) |
| Jira keys | masked |
| Alert threshold | full **0.839** · summary-only **0.821** (chosen on train+val) |

**Choices and alternatives:**
- **Hybrid** (the expected winner): rejected on MRR. It may be worth revisiting for C3 (documentation search), where exact identifiers such as config names matter more.
- **Re-ranking with an LLM:** out of scope (no LLM calls for C2).
- **One threshold for both modes:** rejected; summary-only alert recall would fall to 0.27.
Approved by the user on 2026-11-15 and frozen in `eval/c2_final_config.json`.

### C2 test results (final config, evaluated once; `eval/results/c2_test_20261115T145857Z.json`)
Dense · `BAAI/bge-small-en-v1.5` · Jira keys masked · per-mode thresholds from train+val.

| Mode | MRR [95% CI] | R@1 | R@5 | R@10 | Latency p50 | Alert recall | Alert precision | False alarms: 16 test queries | False alarms: all 100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full (0.839) | 0.604 [0.45–0.75] | 0.51 | **0.74** | 0.77 | 14 ms | 0.54 | 0.83 | **0.25** (4 / 16) | 0.20 |
| summary-only (0.821) | 0.469 [0.32–0.62] | 0.37 | 0.54 | 0.66 | 6 ms | 0.31 | 0.79 | 0.19 (3 / 16) | 0.18 |

- **Ranking generalises:** test MRR 0.604 (n = 35) vs 0.632 on train+val, with overlapping CIs. **R@5 0.74 ≥ 0.60** and **MRR 0.604 ≥ 0.45** (mode full): both targets met. In summary-only mode, R@5 is 0.54, below 0.60; summary-only is reported for reference.
- **False alarms, honestly:**
  - On the 16 untouched test non-duplicate queries: 0.25 (full), above the 0.20 target. One query moves this rate by 6 points (CI roughly 0.07–0.52).
  - On all 100 non-duplicate queries: 0.20 (full) / 0.18 (summary-only). This number is **optimistic**, because 84 of the 100 were used to choose the threshold.
  - Verdict: the false-alarm target is *borderline*. A stricter threshold would trade alert recall for fewer false alarms; it should be re-chosen only on new non-test data, not on test.
- **Pipeline:** decision M2 (below and in `decisions.md`).

### C2 pipeline decision (M2)
C2 runs **twice** in the dialogue:
1. **On the first user message**, in summary-only mode with threshold **0.821**: early warning before the user invests time.
2. **Before C6** (ticket composer), with the collected summary + description, in mode full with threshold **0.839**: a better-informed second check (MRR 0.604 vs 0.469 on test).

Candidates the user **dismissed** in the first pass are removed from the second pass, so the user is not asked twice about the same issue.

**Why a false-alarm rate of 0.20–0.25 is acceptable:**
- **The alert is non-blocking:** the user sees the candidates and can dismiss them with one click.
- **The two errors cost very different amounts:** a false alarm costs one click, while a missed duplicate costs a new Jira ticket that a committer has to triage and close as Duplicate.
