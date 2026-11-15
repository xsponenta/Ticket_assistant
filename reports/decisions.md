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

**Correction to the C3 label semantics** (user, 2026-11-15; supersedes "I know Spark can do this today" above):
- **Who labelled:** the 80 scope labels come from **a single non-expert annotator** (the user is not a Spark expert). Some `already_supported` labels, especially those without a supporting chunk, are **educated guesses, not verified knowledge**.
- **Consequence:** the **knowledge-based** subset (no supporting chunk) is treated as **noisy labels**, not as ground truth the system failed. The **docs-evidenced** subset stays the primary C3 measure. Labels are still not changed.
- **Finding that limits the docs-evidenced subset too** (inspection, `eval/results/c3_compare_20261115T161018Z.json`; `label_cli` reproduces all 80 stored BM25 top-5 lists exactly, so ids and texts are what was shown):
  - `label_cli` showed 280-character chunk previews and did not define "supporting chunk". In practice the chosen chunk is the most related of the 5 shown, not a chunk that shows the capability.
  - In dev, none of the 12 docs-evidenced `already_supported` evidence chunks states the requested capability: 4 are on-topic (Spark Connect, RDD caching, Maven build), 8 are unrelated. For example, SPARK-31008 `json_array_length` was evidenced with a cloud-integration "Further reading" chunk (the function reference was not in the corpus then).
  - So "docs-evidenced" means "the annotator found a related doc", and this subset is also agreement with a noisy annotator. It is reported as the more reliable of the two subsets, with this caveat.
- **Same pattern in judge calibration:** the user's "supports / relevant" means "on-topic". The judge's means "states it" (see L2 update below).

## L2 update — 2026-11-15: C3 judges fail calibration

| Judge (`google/gemini-3.5-flash-lite`) | n | Human yes | Judge yes | Agreement | κ human vs judge | Repeat agreement (κ) |
|---|---:|---:|---:|---:|---:|---:|
| citation support (`judge_citation_support/v1`) | 30 | 22 | 10 | 0.40 | **−0.04** | 0.87 (0.68) |
| chunk relevance (`judge_chunk_relevance/v1`) | 14* | 10 | 7 | 0.36 | **−0.29** | 0.93 (0.86) |

\*1 of the 15 relevance pairs is unlabelled. Source: `eval/results/c3_judge_calibration_20261115T160918Z.json`.

- **Rule applied (B1/L2):** κ < 0.6, so **both judges are uncalibrated**. The citation-support rate and the retrieval-variant selection (relevance@5) are reported as **uncalibrated proxies**.
- **Diagnosis:** the disagreement is a **definition mismatch, not judge noise**. The judge is self-consistent (repeat agreement 0.87 / 0.93).
  - On `already_supported` citations, human and judge agree on 4 of 5.
  - On the other verdicts ("the docs do not show X", citing the closest related chunk), they agree on 8 of 25: the human says "supports" 18 times, the judge 5.
  - Flipping the two likely labelling slips (SPARK-31008 #436, SPARK-48643 #220) leaves κ at 0.04 / −0.14.
- **Fallback (L2), proposed and not applied:** a strong-tier judge from a provider other than the generator (DeepSeek). The cost is below; reasoning tokens are an assumption (300–800 per call, as these models reason by default).

| Candidate (`scripts/list_models.py --tier strong`) | $/1M in / out | 45 calibration pairs | + dev 55 + test ≈ 100 citations (≈ 200 calls) |
|---|---:|---:|---:|
| `anthropic/claude-fable-5.2` (L2's example) | 8 / 40 | ≈ $0.8–1.7 | ≈ $3.6–7.6 |
| `sakana/fugu-ultra-v2` | 5 / 30 | ≈ $0.6–1.3 | ≈ $2.5–5.5 |
| `meta/muse-wonder` | 4 / 20 | ≈ $0.4–0.9 | ≈ $1.8–3.8 |

- **Recommendation:** do not switch. A stronger judge applying the same question would still read "support" as "states it", so it is unlikely to reach κ ≥ 0.6 against these labels. The C3 decision rests on accuracy and the deterministic `doc_reference` grounding check. If wanted: run one candidate on the 45 calibration pairs only (≤ $1.7) and adopt it only if κ ≥ 0.6.

**Resolution (user, 2026-11-15):**
- **No strong-tier judge.** The L2 fallback is not applied.
- **The disagreement is a criterion mismatch.** For "the docs do not show X" answers, the annotator counted the closest related chunk as support; the judge required the chunk to state the claim.
- **Adopted definition:** the judge's stricter reading is what the product needs (no claim without evidence), so it is the definition of citation support from now on.
- **Annotation limitation:** the annotator's labels used a looser criterion. This also applies to the supporting chunks and relevance labels.
- **κ values are kept as measured,** and judge numbers stay uncalibrated proxies.
- **Rule for the remaining judges (C5, C6, e2e), added to AGENTS.md:**
  - the rubric, with explicit edge cases (absence claims, partial support, paraphrase), goes in the judge prompt and is shown on screen in the calibration CLI;
  - deterministic metrics are preferred; a judge is used only where nothing deterministic works.

## M3 · C3 is precision-oriented — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| The assistant tells the user "already supported" **only** when C3's verdict is `already_supported` **and** `doc_reference` is grounded in the retrieved chunks (deterministic check). Every other outcome (other verdict, ungrounded reference, generation failure) lets the user continue to a ticket. **Precision of `already_supported`** is the key C3 metric; accuracy and macro-F1 are secondary. | (1) Show every C3 verdict as advice, also for ND/OOS/II. (2) Stop the user on any `already_supported`, grounded or not. (3) Optimise accuracy. | A false `needs_development` costs one unnecessary ticket. A false `already_supported` wrongly stops the user, so it is the expensive error. Test (`c3_test_20261115T161845Z.json`): precision 0.625 (5/8) [0.25–0.88], all 8 claims grounded. 2 of the 3 wrong claims are defensible by the 4.3.0 docs (labels judged older proposals). Known limitation: the grounding check accepts generic references (e.g. "pyspark"). |

## E1 · C4/C5 ablation eval set — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| Gold "which fields are missing" comes from **rich real tickets with the text of 1–2 required fields deleted** (`data/eval/gap_ablation.jsonl`; dev = 58 val tickets, test = the 60 simulator candidates; 303 / 301 items). Deleted passages are the verbatim quotes of a generator extraction (`ablation_extract/v2`), located deterministically. Spot check: the 10 spot-check extractions (`eval/results/gap_spotcheck_20261115T164526Z.md`) were reviewed by the assistant, not confirmed by the user: no quote assigned to the wrong field; 2 doubtful values (SPARK-33121 environment says "Java API" for Scala code in a ```java fence; SPARK-52965 environment quotes a sentence about the failure) (corrected 2026-11-15; an earlier version of this entry wrongly said the user had confirmed it). | Hand-written incomplete requests (small, unrealistic); a judge deciding completeness (not deterministic). | Real ticket language, exact gold by construction, deterministic metrics (AGENTS judge rule). |
| **Overlap rule:** when deleting *f* also removes part of another field *g*, *g* is left out of scoring for that variant. | Strict: a field that shares text with another is not deletable. That left ≈ 199 / 180 items, and 49 of 118 tickets (mostly ideas and features) gave only the original. | **No half-deleted field is ever scored**, and the set keeps its size and its class balance (user decision). |
| **Title rule:** text is never deleted from the title; a field quoted in the title is not deletable. | Delete from the title too, leaving an empty "Summary:" (28 cases). | **A real conversation always starts with a title** (user decision). |
| Fields the extraction marked `assumed` or could not ground are excluded from scoring (55 field slots). | Count assumed as present or as missing. | Their gold is uncertain. |
| Extraction iteration: v1 left quotes out (23% of tickets failed validation), and one ticket produced a 131k-token runaway ($0.07). For v2, all keys are required with `quotes` first, and new LLM calls are capped (`max_tokens`: extraction 4,000, C4 3,000, C5 600). | Drop the failed tickets (biases the set toward easy tickets). | 118 / 118 extracted with v2. |
| **C4 status `unknown`** (user decision): set only when the user was asked and later said they don't know. C5 never asks about it; C6 will render it as "Unknown (reporter)"; metrics count it as resolved. Evaluated by the `unknown_<f>` variants. | Treat "don't know" as missing (C5 would re-ask). | Re-asking a question the user already said they can't answer is the worst dialogue error. |
| C4 prompt `c4_gap/v1 → v2` (smoke fix on 20 dev items, **not** the one tuning revision): v1 copied stack traces into `value`/`evidence` (3 of 20 outputs cut off at 3,000 tokens) and left `evidence` empty for 20 confirmed fields. v2 makes all `FieldState` keys required with `evidence` first, and asks for short quotes and one-sentence values. | Raise `max_tokens`. | 0 failures, grounding 1.0, half the cost. Dev results are reported for v2 only. |
| No C4 tuning revision for the deleted-field over-crediting pattern (137 of 173 deleted fields resolved). | A rule like "never confirm a field from another field's passage". | Evidence sources: another field's passage 58, unquoted text 45, title 33. Much of this is gold leakage, so such a rule would fit the gold's artifacts, not reality. Proposed instead: a small human audit before test. |

## M4 · `assumed` fields are never accepted silently — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| Fields C4 marks `assumed` are **never accepted silently**. C6 lists them under **"Assumptions to confirm"**, and the UI asks the user to confirm or correct each one before the ticket is final. C5 keeps asking only about `missing` fields. | (1) Treat `assumed` as confirmed (inferred values would reach Jira unchecked). (2) Treat `assumed` as missing (C5 would ask questions whose answer the user already implied, costing turns). | An assumption is shown with its inferred value, so the user corrects it in one click instead of answering an open question. That makes it acceptable in the product for C4 to lean toward `assumed` rather than `missing`: on dev, 56 of 173 deleted fields and 28 of 501 natural gaps were marked `assumed`. The "missing + assumed" view (F1 0.867) is the operational one for "nothing reaches the ticket unconfirmed". `confirmed` on absent information remains the costly C4 error (measured by the audit). |

## M5 · C6 and pipeline design — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| **C6 split:** the LLM writes only the title, labels and field texts. Code assembles the ticket: jira_type from YAML, the confirmed component, "Unknown (reporter)", "_Not provided_" for required missing fields, the "Assumptions to confirm" section, and no priority / fix version. | The LLM writes the whole Markdown body. | The hard rules hold by construction instead of depending on the prompt; they are still measured (dev: 1.000 on every rule check). |
| **C6 eval metric fix** (after the 20-item smoke run, before dev): the invented-token check covers the title and **confirmed** fields only; fence markers are stripped; backticked tokens have no whitespace; there is a generic Spark noun list. Grounding is reported for confirmed and assumed values separately. | Keep the first version (14% invented tokens, mostly false positives). | Assumed fields carry C4's inference on purpose (M4); the rest were measurement artefacts. A measurement fix, not tuning: C6 and its prompt were unchanged. |
| **Pipeline question loop** continues only while a **required** field is missing (max 4 turns; "skip" stops it with no extra C4 call). | Ask until every class field is resolved. | Optional fields would cost the user up to 4 extra turns (found by the pipeline tests). C5 still asks about optional fields in the same turn as a required one. |
| **Assumption confirmation re-renders deterministically** (no second C6 call). Corrections are appended to the conversation and become confirmed fields. | Recompose with C6. | No new LLM text, so a confirmed ticket does not change elsewhere; no cost; cannot fail. |
| **C1 in the UI:** top-2 classes with probabilities (M1). The component is pre-filled with the **top-1**, and the top 3 are shown as suggestions. | Pre-fill all top 3 (M1 wording). | SPARK issues usually have one component; pre-filling three invites over-tagging. A refinement of M1. |
| **Graceful failure:** a failed step is recorded in the trace and `last_error`, the stage is kept, and `retry()` reruns the segment. The UI shows a message and a Retry button; the driver stops. | Let exceptions propagate. | The session survives provider errors (user decision). |

## M6 · UX fixes from the user's manual run — 2026-11-15
No evaluated prompt or config changed.

| Decision | Why |
|---|---|
| **C2 pass 1 never alerts.** Its candidates are shown as "Related issues you may want to check"; the warning banner appears only for pass 2 (full description, threshold 0.839). | The first message is short, and summary-only false alarms were 18–25% on test (M2). An alert at that point mostly cries wolf. |
| **The component confirmed in the UI always wins:** after every C4 call, `component` is set to `confirmed` with the user's value. | C4 re-reads the component from the text and could show a different one; the user's confirmation is final (C6 already used the confirmed value; the field table now agrees). |
| **Field table:** a missing *optional* field shows a grey "not provided" (red "missing" only for required ones); the `labels` row is hidden unless set. | A missing optional field is not an error; the red badge suggested one. |
| **Title icon 🐞** instead of 🎫. | 🎫 renders as "LIVE CONCERT TICKET" in macOS text-to-speech and tooltips. |

Tests: `tests/test_pipeline.py::test_m6_pass1_never_alerts_and_confirmed_component_wins`; UI checked with `streamlit.testing.AppTest`.

## E2 · End-to-end evaluation with a simulated user — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| **Hidden tickets:** the 60 test `simulator_candidates` (15 per class). Gold fields = the ablation extractions (`gap_extractions.jsonl`, confirmed and grounded required fields of the gold class). Smoke: 5 val tickets. | New hand-written scenarios. | Real ticket language with an existing, spot-checked gold. These test tickets are used only here and in the ablation test. |
| **Simulated user** (role simulator, `qwen/qwen3.5-27b`, reasoning off). The opener is written from the **summary only** (≤ 20 words; a deterministic leak check against the description, one regeneration). Answers: only what is asked, from the hidden ticket, "I don't know" otherwise. | Replaying the original description as the first message. | A real first message is vague; replaying the description would make every dialogue trivially complete. |
| **`sim_user` v1 → v2** after the smoke run: v1 referred to "the ticket" / "my ticket" (3 of 8 answers). v2 frames the hidden text as "what you know" and forbids mentioning a ticket, Jira or notes. A deterministic `META_RE` check was added. | Keep v1. | A user without a ticket cannot cite one; meta mentions broke the role. After v2: 1 meta mention in 9 answers (an echo of the ticket's own words). |
| **Simulator checks refined on the smoke transcripts** (scoring only): a broader "don't know" detector ("I don't have the …", "not available"); "answers when present" fails only on a pure "don't know", since a partial answer ("I don't know the version, but I built it with Maven") is correct behaviour. | Count any "don't know" phrase as a refusal. | The first version mislabelled correct partial answers. |
| **Two policies:** auto (C1's top-1 class) and user-corrects (the simulated user confirms the gold class: the intended UX, M1). Both: top-1 component, dismiss nothing, continue on the scope stop, accept the assumptions. Policy auto runs first; corrects reuses its cache, so **latency and cost come from auto only**. | One policy. | auto measures C1's real cost to the dialogue; corrects measures the product as designed. |
| **Field text recall** is compared with the gold extraction's concise `value` (primary) and with its verbatim quotes (secondary, stricter: quotes are often whole code blocks). The match is lexical (no stemming). | Quotes only. | Quotes made recall structurally low (0.40–0.45 on smoke) even for correct fields. |
| Code at **commit `d4c9892`** (recorded in `eval/e2e_final_config.json`; M6 fixes in `9dc7e65`); the test run checks that HEAD matches. | — | Reproducibility. |

## M7 · A failed C3 check continues to the ticket (post-test robustness fix) — 2026-11-15

| Decision | Alternatives | Why |
|---|---|---|
| If the C3 call fails (e.g. `already_supported` without a `doc_reference`, rejected twice by the validator), the pipeline records the error in the trace and `state.c3 = {failed, error}`, keeps `last_error` empty and **continues to C2 pass 2 and C6**. The UI notes "the documentation check failed, so we continue to the ticket". | Stop and ask the user to retry (the original graceful-failure behaviour): the retry hits the same cached failure. | C3 is advisory: under M3 every outcome except a grounded `already_supported` means "continue". In the e2e test, this failure was the only reason a dialogue produced no ticket (1 of 60 per policy). |
| **Status: post-test fix**, approved by the user after the e2e test. The test numbers (`e2e_test_20261115T181923Z.json`) are **not** replaced. A separate, labelled post-test rerun of only SPARK-19469 and SPARK-3833 (`eval/results/e2e_posttest_20261115T182617Z.json`, commit `99d72b9`) gives completion 2/2 under both policies; field recovery is 1.0 (corrects) and 0.0 (auto, wrong class). | Rerun the whole test. | Rerunning the test after a fix would turn the test set into a tuning set. |

Test: `tests/test_pipeline.py::test_m7_failed_scope_check_continues_to_the_ticket`.
