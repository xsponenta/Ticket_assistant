# Decision log

Decisions for CRISP-DM Data Preparation.
- Evidence: [`notebooks/eda.ipynb`](../notebooks/eda.ipynb), summarised in [`02_data_understanding.md`](02_data_understanding.md).
- Implementation: `src/data/` (see [`03_data_preparation.md`](03_data_preparation.md)).

| ID | Date | Decision (short) |
|---|---|---|
| D1 | 2026-11-15 | Issue type → class mapping; Sub-task and other types excluded |
| D2 | 2026-11-15 | Idea = SPARK Wish (all-time) + Brainstorming; `wish_other` not used |
| D3 | 2026-11-15 (amended same day) | Main = created before 2026 (non-idea from 2020-01-01, idea without lower bound); everything created in 2026 → drift set |
| D4 | 2026-11-15 | No resampling; stratified splits; macro-F1; class weights allowed |
| D5 | 2026-11-15 | PII masking: e-mails, Jira mentions, @user in prose, URL credentials; URLs kept |
| — | 2026-11-15 | Duplicate eval: Duplicate links treated as undirected (later issue = query, earlier = gold) |

## Change log

| Date | Change | Effect |
|---|---|---|
| 2026-11-15 | **D3 amended:** the 2026 cut-off applies to all classes, including idea. The 3 SPARK Wish issues created in 2026 moved from main to the drift set. | main 14,992 → 14,989; drift 3,564 → 3,567 |
| 2026-11-15 | **Splits regenerated once and re-frozen**, because main changed and the test split had not been used yet. Old test hash `759eb493…` (bug 806 / feature 1,149 / task 269 / idea 25) discarded. | New test hash `339455ee27a9ecde360fc82b99dc4f8475de09c2b00093744f2721b36a7e580a` (bug 806 / feature 1,149 / task 269 / idea 24) |
| 2026-11-15 | **CRISP-DM iteration:** Phase 1 (`01_business_understanding.md`) written after Phases 2–3 and the model bake-off, so problem statement, targets and risks use EDA and bake-off numbers; `src/schemas/ticket_types.yaml` created as the single source of truth for ticket fields. | Targets are proposals, pending adjustment by the user |
| 2026-11-15 | **Duplicate eval redefined:** links are undirected; query = later-created issue, gold = earlier issue. Identical summaries are still excluded. | duplicate queries 98 → 148 |

---

## D1 · Mapping of issue types to target classes — 2026-11-15

**Decision**

| Class | Jira issue types |
|---|---|
| bug | Bug |
| feature | New Feature, Improvement, Story |
| task | Task, Test, Documentation, Dependency upgrade |
| idea | Wish, Brainstorming |

All other types are excluded: **Sub-task**, Umbrella, Epic, Question, IT Help, Request, Github Integration, RTC, Planned Work, Blog - New Blog Request.

**Alternatives considered**
- (a) Core types only (Bug, New Feature, Improvement, Task, Wish). Rejected: task would have only 996 issues since 2020.
- (b) Sub-task → task. Rejected: task would become 47% of the data and mix fragments of features, bugs and upgrades.
- (c) Sub-task inherits its parent's class. Rejected: needs another download, and parents are often Umbrella or Epic.
- (d) Question as an extra "route elsewhere" class. Rejected: outside the four-class scope; only 161 issues.

**Evidence (EDA)**
- §1: Sub-task has 12,280 issues (39% of SPARK since 2020). Mapping it to task would make task the largest class.
- §2 / §4a: 55.8% of Sub-tasks have an empty description. Their summaries are pieces of larger work ("Upgrade X", "Support … for function Y"), so they are fragments rather than standalone tickets.
- §1: the types outside the mapping are 1.8% of issues. Test (798), Documentation (309) and Dependency upgrade (114) are non-functional work, which matches the user meaning of "task".
- §4a: Task alone is narrow (37.6% Structured Streaming); the added types broaden it.

**Effect:** 31,403 unique issues → 18,556 kept (12,847 excluded, of which 12,280 are Sub-tasks).

---

## D2 · Source of idea examples — 2026-11-15

**Decision**
- Idea = all SPARK Wish issues (`spark_wish_all.jsonl`, 158) + SPARK Brainstorming (7).
- `wish_other.jsonl` is **not used** for training or evaluation.

**Alternatives considered**
- (a) Mix `wish_other` with SPARK Wish and split randomly. Rejected: the test would measure project detection.
- (b) Train on `wish_other` with project names masked, test on SPARK Wish. Rejected: there is still a giveaway in style and vocabulary, and the training data comes from other domains.

**Evidence (EDA §4b)**
- 63% of `wish_other` issues name their own project. The top source-revealing terms are project names (guacamole, nifi, tika, cxf, camel, solr, calcite …), plus forum-style words like "thanks", "nice", "wish".
- Only 1.5% of non-SPARK Wishes mention Spark, against 72.8% of SPARK Wishes and 40% of all SPARK issues.
- 41 `wish_other` issues are SPARK issues that are also in `spark_wish_all.jsonl` (overlap).

**Effect:** idea has 162 issues in main (113 train / 25 val / 24 test), plus 3 issues created in 2026 in the drift set. It stays the smallest class (1.1% of main), which D4 handles.

---

## D3 · Date range — 2026-11-15

**Decision (as amended on 2026-11-15)**
- Main dataset = issues created 2020-01-01 to 2025-12-31. For idea there is **no lower bound**: all SPARK Wish history from 2014 is used.
- **Every issue created in 2026 goes to the drift set** (`data/processed/drift_2026.parquet`), for all classes.

**Amendment:**
- The first implementation read "idea: all-time" as having no upper bound either, and kept the 3 SPARK Wish issues created in 2026 in main.
- Corrected: D3 applies to all classes, so those 3 issues are now in the drift set.
- Splits were regenerated once and re-frozen before the test split was ever used (see Change log).

**Alternatives considered**
- (a) Everything up to the snapshot. Rejected: the late-2026 burst would dominate the bug class.
- (b) Train before 2026, test on 2026. Replaced by a separate drift set, so the main test set keeps the same distribution as training.
- (c) Cap issues per month or component. Rejected as arbitrary.

**Evidence (EDA §10)**
- 2026 Bug descriptions differ sharply from 2020–2025:
  - median length 114 words (vs 50–93 before);
  - Jira headings 11.6% (≤3.6% before);
  - root cause / proposed fix sections 11.4% (≤3.3%);
  - pull-request label 89% (72–78% in 2024–25);
  - Connect component 29.8% (≤13.4%).
- Monthly bug volume went from about 45 (2025) to 258 (Oct 2026) and 530 (first half of Nov 2026).
- 72% of SPARK Wishes are from before 2020 (EDA §4b), so a 2020 lower bound would leave only 49 ideas before 2026.

**Effect:** 18,556 → 14,989 main + 3,567 drift (bug 1,575 / feature 1,556 / task 433 / idea 3).

---

## D4 · Class imbalance — 2026-11-15

**Decision**
- No resampling (no up- or down-sampling, no synthetic examples).
- Splits are stratified by class (70/15/15, seed 42).
- The main metric is **macro-F1**; models may use class weights.

**Alternatives considered**
- (a) Cap bug and feature at 2–3k each. Rejected: discards data and distorts the real class proportions.
- (b) Generate extra idea/task tickets with an LLM. Rejected: synthetic artifacts and contamination risk.

**Evidence (EDA §1)**
- Even after D1–D3 the classes are imbalanced: main = feature 50.9%, bug 36.2%, task 11.9%, idea 1.1%.
- Macro-F1 weights idea and task equally with the large classes. Stratification keeps 25 idea issues in val and 24 in test.
- The classification eval set caps classes at 100 (idea: all 24), so per-class metrics are comparable.

---

## D5 · Masking personal data — 2026-11-15

**Decision**
- Rules applied to summaries and descriptions in `src/data/clean.py`:
  - e-mails → `<EMAIL>`
  - Jira mentions `[~user]` → `<USER>`
  - GitHub-style `@user` in prose → `<USER>`
  - credentials in URLs are removed
- URLs are otherwise kept unchanged.

**Implementation details**
- E-mails and Jira mentions are masked everywhere, including inside code blocks (configs and logs contain e-mails too).
- `@user` is masked only in prose (outside fenced and inline code) and skips known annotations and doc tags (`@Override`, `@since`, `@udf`, …).
- E-mail detection ignores `x@host` preceded by `/`, so URI authorities such as `spark://driver@host` and `abfss://container@account` are kept.
- URL credentials:
  - `scheme://user:password@` → `scheme://` for any scheme;
  - `https://token@` → `https://` for http(s)/ftp.

**Alternatives considered**
- (a) No masking. Rejected: data minimisation; the assistant should not reproduce user identities.
- (b) Named-entity recognition for person names. Rejected: many false positives on Spark CamelCase identifiers, for a rare problem.

**Evidence (EDA §8)**
- In SPARK descriptions: Jira mentions 0.4%, e-mails 0.1% (many placeholders), GitHub @mentions 10 issues once annotations are excluded, explicit names about 10 issues. Summaries contain none of these.
- URLs appear in 16% of descriptions, mostly github.com pull requests: useful context, not personal.

**Effect (main dataset):** 19 descriptions contain `<EMAIL>`, 94 contain `<USER>`, and 2 had URL credentials removed.
**Known gap:** names written freely in text ("Regards, Jane Doe") are not masked.

---

## Implementation choices made while applying D1–D5 (for review)

These were not specified in the brief; each is recorded here so it can be changed.

1. **Duplicate links:**
   - `duplicate_of` / `duplicated_by` are *lists*, because 13 issues duplicate more than one original.
   - They contain all linked keys, including keys outside the main dataset.
   - Direction follows EDA §5.
2. **Summaries** are PII-masked and whitespace-normalised, but Jira markup is *not* converted, because Jira does not render markup in summaries.
3. **Extra markup conversions** in `clean.py`, beyond the brief:
   - Jira lists (`#` / `*`) → Markdown lists. Otherwise a Jira `# step` becomes a Markdown H1 (799 descriptions have Jira `#` lists).
   - `bq.` → `>`, `||header||` table rows → Markdown header row, `!image.png!` → `![](image.png)`.
   - Editor artifacts (`{}`, `\{`, `{*}`) are removed.
   - An unclosed `{code}` runs to the end of the description (3 cases).
4. **Duplicate eval** (decided 2026-11-15):
   - A Duplicate link is treated as **undirected**. Query = the later-created issue of the pair, gold = the earlier one, because a user writing a new ticket must find the existing one.
   - Of 182 linked pairs in main, 61 have the Jira "duplicate" on the *earlier* issue; their direction is flipped for retrieval.
   - Identical normalised summaries are still excluded (25 pairs). That leaves 148 queries, 5 of which link to several earlier issues (`gold` = oldest, `gold_all` = all).
   - Queries come from all splits (field `split`), because duplicate retrieval is not trained on the classification split.
   - Non-duplicate queries are issues with no Duplicate link in either direction, not resolved as Duplicate, created ≥ 2020-04-01.
5. **Scope candidates** are drawn from the frozen test split. The Not A Problem/Invalid bucket had only 23 eligible test issues, so 2 come from val (field `split`).
6. **Labelling CLI:**
   - Candidates are shown in a fixed shuffled order (seed 42), because the file is grouped by resolution bucket.
   - The resolution hint is hidden unless `--show-hint` is used, to avoid biasing labels.
7. **Doc chunks:**
   - `{% highlight %}` blocks become ``` fences (not deleted).
   - `{{site.*}}` variables are filled from the release's `_config.yml`.
   - Kramdown TOC markers and bare `<div>` wrapper lines are removed.
   - `README.md` and `404.md` are skipped.
   - Tokens are counted with tiktoken `cl100k_base`, as a proxy for the model's tokenizer.

---

## L1 · Shared LLM client (`src/llm.py`) — 2026-11-15

**Decision**
- All LLM calls go through `src/llm.py`: OpenRouter via the openai SDK.
- Disk cache keyed by the full request (model, messages, temperature, max_tokens, response format / schema).
- Exponential backoff on 429 / 5xx / timeouts / connection errors. A 200 response without choices is retried too.
- Structured output depends on what the model supports (from OpenRouter `/models`):
  - `json_schema` if `structured_outputs` is supported;
  - otherwise `json_object` plus the schema in the prompt;
  - otherwise the schema in the prompt only.

  The reply is always validated with pydantic, with one repair retry.
- One JSON log line per call. Langfuse tracing is optional.
- Thread-safe: one shared client, atomic cache writes (temp file + `os.replace`), locked log appends.

**Choices made with the user**
- `temperature=None` uses the role default from `config.yaml` (generator 0, judge 0, simulator 0.7). The judge is always forced to 0. Alternative rejected: a fixed function default of 0, which would make the config defaults dead.
- Ruff is applied to new and changed files only. Alternative rejected: reformatting `src/data/` now. That code has 102 findings, mostly long lines, left for a separate clean-up.
- `max_tokens` is optional and part of the cache key.

**Other choices**
- `strict: false` in `json_schema` mode, because pydantic schemas are not always strict-compatible; validation happens client-side anyway.
- Cache hits are logged with `cost: 0` and the token counts of the original call.
- The cache also stores the full request, so prompts can be inspected; prompts are not written to the log.
- `scripts/list_models.py` excludes moving `~provider/...-latest` aliases: evals need a model that does not change underneath them.
- It prints rule-based candidates only; the user chooses the models.

**Evidence:** `tests/test_llm.py`, 15 tests with a mocked HTTP transport:
- cache, retries, 400 not retried, max attempts;
- json_schema / json_object / prompt modes, repair, config errors;
- temperature rules, max_tokens;
- 20 concurrent calls, repeated 30 times without a failure.

---

## L2 · Model choice per role — 2026-11-15

**Decision** (confirmed by the user after the val bake-off, `reports/model_selection.md`)

| Role | OpenRouter model | Reasoning (`config.yaml` → `reasoning.<role>`) |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017` | `{effort: none}` (off) |
| judge | `google/gemini-3.5-flash-lite` | `{effort: minimal}`: reasoning is mandatory for this model, and minimal is its lowest effort |
| simulator | `qwen/qwen3.5-27b` | `{enabled: false}` (off) |

The embedder (C2, local model) is not chosen yet.

**Evidence** (`eval/results/model_bakeoff_20261115T132437Z.json`; val only: 40 classification items, 10 bugs, 5 dialogues; 10 configs; $1.25 total)
- **Generator:**
  - extraction: 100% first-try valid, 0 possibly-invented fields;
  - simulator: 5/5;
  - latency p50 1.0 s / p95 2.9 s; $0.016 per 100 calls.
  - It is the cheapest config that meets the generator rule: macro-F1 ≥ best − 0.05, extraction first-try valid ≥ 90%, ≤ 1 possibly-invented field.
  - Reasoning as served (high) gives the same macro-F1 (0.396 vs 0.393) and the same extraction quality, at about 1.8× the cost.
- **Judge:**
  - extraction: 100% first-try valid, 0 possibly-invented fields, 100% grounded;
  - simulator: 5/5;
  - latency p95 1.9 s; $0.058 per 100 calls;
  - different provider from the generator.
- **Simulator:**
  - in character in 100% of replies; honest on the not-in-ticket question in 5/5 dialogues; $0.056 per 100 calls;
  - a different model family from the generator.

**Rule overrides**
- **Judge: the rule was overridden.** The approved rule (strongest config by macro-F1, from a different provider) picked `qwen/qwen3.5-9b`.
  - That pick rests only on the highest macro-F1 (0.44). This is noise: n = 40, the CI 0.32–0.55 overlaps every config, and classification does not separate the models (no config ever predicted *idea* correctly).
  - qwen3.5-9b also has the most possibly-invented extraction fields (4), which disqualifies it as a judge of factual grounding.
  - Gemini 3.5 flash-lite was chosen for groundedness and consistency instead.
- **Calibration caveat:** the judge is a "lite" model and no strong-tier model was in the bake-off.
  - As AGENTS.md requires, the judge must be calibrated against human scores before its numbers are reported, with agreement stated.
  - If agreement is low, switch to a strong-tier judge (e.g. `anthropic/claude-fable-5.2`), still from a different provider than the generator. Log that as an update to L2.
- **Simulator: the cheapest candidate was not taken.** The rule's pick, `qwen/qwen3.5-9b` (in character 93%, Q3 honest 4/5, $0.0046 per 100 calls), invented one fact ("I am running this locally"). `qwen/qwen3.5-27b` with reasoning off was chosen instead, because an invented fact would corrupt the end-to-end fact-recall and hallucination metrics. The cost difference is about $0.05 per 100 calls.

**Alternatives considered:** the other 7 bake-off configs (glimpse, seed-2-1-turbo and qwen3.5-27b as served or with reasoning minimised; qwen3.5-9b).
- Configs that reason as served cost 4–7× more and were 1.3–6× slower at p50, with no quality gain.
- seed-2-1-turbo had a p95 of 139 s as served.

**Measurement notes**
- **Parser bug:** a bug in `src/llm.py` (code fences inside JSON values) was found and fixed during the bake-off. All results above come from the corrected rerun.
- **Simulator checks** were revised (v2) after reading the v1 transcripts and before choosing; the reasons are stated in `reports/model_selection.md`.
- **OpenRouter metadata:** the reasoning metadata from OpenRouter is unreliable, so every role sets `reasoning` explicitly in `config.yaml`.

---

## B1 · Success targets accepted, with three changes — 2026-11-15

**Decision:** the targets in `reports/01_business_understanding.md` are accepted, with these changes from the user:

1. **C4 (gap detector) is evaluated on an ablation set:** rich val/test tickets with 1–2 required fields removed, where gold = the removed fields. Simulated dialogues are used **for end-to-end evaluation only**.
   - Why: gold is exact and needs no simulator or judge, so a C4 error cannot be confused with a simulator error.
   - Consequence applied: C5 (question generator) was also tied to the simulated dialogues. It now uses the same ablation set (do the questions target the removed fields?), so simulated dialogues stay end-to-end only. The user can revert this.
2. **C1 is reported in two input modes:**
   - **full** (summary + description): targets apply here;
   - **summary-only**: a proxy for the vague first message a user types in the app, reported for reference.
3. **The C1 targets are provisional until a human-ceiling check:**
   - 40 val issues, 10 per class, seed 7, drawn from the 325-item C1 LLM val subset (`src/eval/samples.py`) and disjoint from the bake-off sample;
   - labelled by the user without seeing the Jira type (`python -m src.eval.human_label_cli` → `data/eval/human_ceiling_val.jsonl`);
   - if the user's macro-F1 against the Jira labels is below the C1 target, the target becomes the user's score, and the report says so.

**Alternatives:** evaluating C4 and C5 on simulated dialogues (rejected: gold depends on the simulator); using one input mode for C1 (rejected: the app sees vague first messages, not finished descriptions).

**Evidence:**
- **Bake-off:**
  - no model ever predicted *idea* correctly;
  - 18 of 40 val items were wrong for every configuration;
  - 82% of idea predictions went to *feature*.
- **Contributing guide:** "Bug, Improvement and New Feature are generally the only types used" in Spark.
- **Conclusion:** the Jira labels may not be learnable to 0.60 macro-F1, and a human ceiling shows what is achievable.

---

## B2 · C1 class targets set to the human ceiling — 2026-11-15

**Decision:** applying the rule agreed in B1, the C1 class targets become the user's own agreement with the Jira labels:
- **macro-F1 ≥ 0.37** (was 0.60);
- **idea recall ≥ 0.40** (was 0.50).

The component targets (top-1 ≥ 0.60, top-3 ≥ 0.85) are unchanged.

**Evidence** (`data/eval/human_ceiling_val.jsonl`; `eval/results/c1_val_20261115T135541Z.json` → `human_ceiling`; 40 val items, 10 per class, Jira type hidden)
- **The user against Jira:** macro-F1 0.370 (95% CI 0.21–0.50), accuracy 0.35, idea recall 0.40 (idea precision 1.0).
- **Where the user and Jira disagree:** the user labelled 16 of 40 items *task*, including 6 of 10 Jira *features* and 5 of 10 Jira *bugs*.
- **The models on the same 40 items:** baseline 0.52, LLM 0.56 macro-F1. Agreement with the user: LLM 50% (κ 0.31), baseline 38% (κ 0.16).

**Interpretation:** the Jira type records Spark's filing conventions, not only the class definitions:
- committers file planned API work as Task and test fixes as Bug;
- outside users file concrete feature requests as Wish.

The models learn some of these conventions from TRAIN; a person reading the definitions does not.

**Caveats:**
- n = 40 with a wide CI; one annotator; about 10 s per item (40 items in 6.5 min).
- The macro-F1 target is now below both models' val scores, so it no longer constrains the choice.
- Possible follow-ups, for the user to decide: a second annotator or a slower re-labelling pass; or evaluating C1 against an adjudicated, definition-based gold label instead of the Jira type.

**Alternatives:** keeping 0.60 / 0.50 as stretch targets (not chosen: B1 fixed the rule in advance).

---

## M1 · C1 in the app: baseline, with user confirmation — 2026-11-15

**Decision:**
- **C1 in the app is the baseline:** TF-IDF word 1–2 + char 3–5 → LogisticRegression(class_weight="balanced"); C = 1 for mode full, 0.3 for summary-only; components one-vs-rest LR (C = 10 / 3).
- **The UI** shows the predicted class plus the second most likely class, and the **user confirms** one. The top-3 components are pre-filled for confirmation.
- **The LLM variant** (`c1_classifier/v1`, few-shot k = 2 / 4) stays as the evaluated alternative and is not used in the pipeline.

**Evidence** (val, 325 items, mode full; `reports/04_modeling.md`, C1):

| | Baseline | LLM |
|---|---:|---:|
| Macro-F1 | 0.561 | 0.523 (CIs overlap) |
| Component top-1 / top-3 | 0.73 / 0.93 | 0.72 / 0.81 |
| Latency | 0.3 ms | p50 1.0 s |
| Cost per 100 calls | $0 | $0.015 |

- Human ceiling: 0.37 vs Jira. The task is ambiguous for a person, so C1 is a suggestion and its errors cost one click.

**Alternatives:**
- LLM as the default: rejected. It is not better against Jira, it costs latency and money, and its confidence is uncalibrated (0.90–1.00 on its worst errors).
- A hybrid (baseline, plus the LLM when the baseline is uncertain): not evaluated; possible later.
- Prompt v2 imitating Jira conventions: rejected (see `04_modeling.md`, "Iteration considered and rejected").

**Test confirmation (evaluated once, 2026-11-15):** on `classification_test` (n = 324, mode full):
- macro-F1: baseline 0.542 [0.47–0.61], LLM 0.571 [0.51–0.63]. The ranking is the reverse of val, but within the CIs.
- component top-3: baseline 0.94, LLM 0.86.
- drift 2026 (3-class): baseline 0.632, LLM 0.697.
- idea recall: 0.17 for both (target 0.40 not met). The baseline's top-2 contains idea for 0.42 of idea tickets, so the UI must also let the user pick any of the four classes, not only the two suggestions.

**M1 is not changed** because of test or drift results: that would be test-set selection. An LLM fallback for uncertain or new-vocabulary tickets is noted as a later iteration, to be decided on val or a new drift slice.

---

## L3 · Embedder for retrieval (C2, later C3) — 2026-11-15

**Decision:** `models.embedder = BAAI/bge-small-en-v1.5`.
- Runs locally with sentence-transformers on CPU, with its documented query prefix ("Represent this sentence for searching relevant passages: ") and no passage prefix.
- The corpus embeddings are cached in `data/processed/embeddings/` (23 MB, gitignored), so the app only encodes the query.

**Evidence** (`eval/results/c2_embedders_20261115T145110Z.json`): dense variant; 113 train+val duplicate queries; time-correct corpus (issues created before the query, never the query itself); Jira keys masked as `<ISSUE>`.

| Model | MRR full [95% CI] | R@1 / R@5 / R@10 full | MRR summary-only | Query p50 (CPU) | Corpus encoding |
|---|---:|---:|---:|---:|---:|
| **BAAI/bge-small-en-v1.5** | **0.632** [0.55–0.71] | 0.56 / 0.72 / 0.79 | **0.536** | 14 ms | 197 s |
| sentence-transformers/all-MiniLM-L6-v2 | 0.570 [0.48–0.65] | 0.49 / 0.67 / 0.71 | 0.461 | 7 ms | 60 s |
| intfloat/e5-small-v2 | 0.547 [0.46–0.63] | 0.45 / 0.68 / 0.73 | 0.497 | 13 ms | 209 s |

- **Selection rule:** best MRR in mode full (a tie within 0.01 goes to the faster model).
- **Ranking:** bge-small is best in both modes. Its CI overlaps MiniLM's, but its point estimate is 0.06 higher, and the latency difference (7 ms) does not matter for a ticket form.

**Alternatives:**
- MiniLM: 3× faster corpus encoding, lower MRR.
- e5-small: lowest MRR with its documented "query:" / "passage:" prefixes. Its symmetric "query:" / "query:" convention was not tested.
- Larger embedders and API embeddings: out of scope (local, CPU, laptop).

---

## M2 · C2 in the app: two passes, dismissed candidates removed — 2026-11-15

**Decision:**
- **First pass:** C2 runs on the **first user message** in summary-only mode, alert threshold **0.821**.
- **Second pass:** it runs again **before C6**, on the collected summary + description, in mode full, threshold **0.839**.
- **Dismissed candidates:** a candidate the user dismissed in the first pass is removed from the second pass's results.
- **Configuration:** dense retrieval, `BAAI/bge-small-en-v1.5` (L3), Jira keys masked (`eval/c2_final_config.json`).

**Why:**
- **First pass:** most value comes from warning early, before the user spends turns on a ticket that already exists.
- **Second pass:** the first message is short; once the description exists, retrieval is much better (test MRR 0.604 full vs 0.469 summary-only; R@5 0.74 vs 0.54).
- **Removing dismissed candidates:** asking about a dismissed candidate again is noise.

**Evidence** (test, evaluated once, `eval/results/c2_test_20261115T145857Z.json`):

| | Mode full | Summary-only |
|---|---:|---:|
| MRR | 0.604 [0.45–0.75] | 0.469 |
| R@5 | 0.74 | 0.54 |
| Alert recall | 0.54 | 0.31 |
| False alarms (16 test queries) | 0.25 | 0.19 |
| False alarms (all 100, optimistic) | 0.20 | 0.18 |

**Alternatives:**
- Only the first pass (rejected: misses what the description adds).
- Only the second pass (rejected: the warning comes too late).
- A single threshold for both modes (rejected on train+val: summary-only alert recall would be 0.27).

**Why 0.20–0.25 false alarms is acceptable:** the alert is non-blocking (the user dismisses it with one click). A false alarm costs one click; a missed duplicate costs a new Jira ticket for committers to triage.

**Open point:** the full-mode false-alarm rate on the 16 test queries (0.25) is above the 0.20 target. One query moves it by 6 points. Re-check the threshold on new non-test data before tightening it.

---

## Change log addition — 2026-11-15: CRISP-DM iteration (Data Preparation bug found in Modeling, C3)

| Date | Change | Effect |
|---|---|---|
| 2026-11-15 | **The doc corpus missed the generated reference tables.** `docs/sql-ref-functions-builtin.md` (48 tags) and `docs/configuration.md` (2) include the SQL built-in function tables and the runtime/static SQL config tables with `{% include_api_gen %}` at site-build time. `chunk_docs.py` stripped Liquid tags, so the reference was lost. Found because C3 could not confirm requests such as "Support json_array_length". | `src/data/fetch_doc_tables.py` stores the rendered 4.3.0 pages in `data/raw/docs_generated/`. `chunk_docs.py` adds **111 chunks** (functions 55, SQL configs 56) on `<page>__generated` pages. The **2,034 existing chunks are unchanged** (ids and texts verified), so the scope labels' supporting-chunk ids stay valid. C3 dev is rerun on the new corpus. |
| 2026-11-15 | **Iteration 2: one chunk per reference entry.** On the corpus above, dev accuracy stayed 0.300 (dense k=8; `c3_verdict_20261115T152008Z.json`): e.g. `json_array_length` sits in a 40-entry list chunk, and dense retrieval returned other list chunks instead. A no-LLM check showed that one-entry chunks put it into the dense and hybrid top 5 (BM25 still misses). Alternatives: keep list chunks (reference stays unfindable); smaller lists of ~10 entries (still dilutes one entry). | `chunk_docs.py` (`entry_chunks`) emits the reference as **898 one-entry chunks** (`title > heading` + one line); the 2,034 Markdown chunks are unchanged (verified). Corpus 2,932 chunks. **User decision: this is the last corpus iteration.** After this dev rerun, whatever the accuracy: evidence review → 45 calibration pairs → test. No further tuning on the 30 dev items. The write-up shows all three corpus versions. |

**C3 label semantics** (user clarification, same day):
- **What the label means:** `already_supported` in the scope labels means "I know Spark can do this today", sometimes from the user's own Spark knowledge, not only from the chunks shown. 23 of the 42 `already_supported` labels have no supporting chunk.
- **Decision:** C3 stays **docs-grounded**. The assistant must not claim "already supported" without a citation, so there is no relabelling and no answering from model knowledge.
- **Added evidence:** for the `already_supported` labels without a chunk, the user reviews the hybrid top 5 of the new corpus and may add a supporting chunk. This adds evidence; it does not change labels. It is stored separately (`data/eval/scope_evidence_added.jsonl`).
- **Reporting:** C3 is reported on all items and separately on "docs-evidenced" (a supporting chunk exists) and "knowledge-based" (none).
