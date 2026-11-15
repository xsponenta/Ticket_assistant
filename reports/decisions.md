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
