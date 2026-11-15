---
name: apache-jira-data
description: Work with Apache Jira (SPARK) data in this project — the REST API fetcher, Duplicate-link direction, Jira wiki markup cleaning and PII masking, and decisions D1–D5 (class mapping, idea source, date range/drift, splits/metrics, PII). Use when fetching, cleaning, splitting or querying issues, or building eval sets from Jira data.
---

# apache-jira-data

> Extracted from `src/data/*` and decisions D1–D5 of this project (2026-11-15). The raw data in `data/raw/` is
> never modified, and the processed data is not rebuilt unless the user asks.

## API (`src/data/fetch_jira.py`, `check_jira.py`)
- **Endpoint:** `https://issues.apache.org/jira/rest/api/2/search`, JQL, `startAt` / `maxResults=100`; `maxResults=0` returns only the total.
- **Fields:** `summary, description, issuetype, components, priority, status, resolution, created, resolutiondate, issuelinks, labels`. **Reporter and assignee are never requested.**
- **Politeness and robustness:**
  - at most 1 request per second;
  - exponential backoff on 429 / 5xx / network errors (1–32 s, honours `Retry-After`);
  - **resumable** via `<out>.checkpoint.json`, with already-seen keys skipped.
- **Docs:** `fetch_docs.py` (Spark 4.3.0 Markdown sources). `fetch_doc_tables.py` adds the rendered SQL function / config tables, which the Markdown includes only at site-build time (`{% include_api_gen %}`). This was a CRISP-DM iteration.

## Duplicate links (verified in EDA §5; `prepare.duplicate_maps`)
- **What the link means:** on issue X, `outwardIssue` Y means "X duplicates Y" (X is the duplicate, Y the original); `inwardIssue` Y means "X is duplicated by Y".
- **The eval treats the link as undirected:** the **later-created issue is the query**, the earlier one is gold, and the corpus is the issues created *before* the query (`DuplicateFinder.mask`, time-correct). In 61 of 182 pairs Jira's direction is opposite to this query direction.
- **Jira keys** (`SPARK-123`, `HIVE-45`) are masked as `<ISSUE>` in C2 and C3 queries and documents (`src/retrieval/text.mask_issue_keys`).

## Cleaning (`src/data/clean.py`)
- **Wiki markup → Markdown:** `{code}` / `{noformat}` blocks become ``` fences (code is protected while markup is converted), `{{mono}}` becomes `code`; headings, lists, tables, quotes, colour and panel tags are converted.
- **PII masking (D5):**
  - e-mails → `<EMAIL>`; Jira mentions and @user in prose → `<USER>` (not in code: annotations look the same);
  - URL credentials removed; URLs kept.
- **Summaries:** PII masking and whitespace only, because Jira does not render markup in summaries.

## Decisions D1–D5 (`reports/decisions.md`)

| | Decision |
|---|---|
| **D1** | Class mapping: bug = Bug; feature = New Feature, Improvement, Story; task = Task, Test, Documentation, Dependency upgrade; idea = Wish, Brainstorming. Sub-task and other types are excluded. |
| **D2** | idea = SPARK Wish (all-time) + Brainstorming; `wish_other.jsonl` is **never** used. |
| **D3** | Main set = created before 2026 (non-idea from 2020-01-01; idea with no lower bound); everything created in 2026 → `drift_2026.parquet`. |
| **D4** | No resampling; stratified, duplicate-aware 70/15/15 splits (**`splits.json` is frozen**, test hash in AGENTS.md); macro-F1; class weights allowed. |
| **D5** | PII masking as above. |

## Data facts worth remembering
- Main set: 14,989 issues; drift set: 3,567; doc chunks: 2,932 (2,034 Markdown + 898 one-entry reference).
- Only **3.4%** of bug descriptions contain all 4 structure elements (repro, expected, actual, version/env). This is the business baseline.
- The Jira `resolution` is post-hoc information. Store it as a hint, **never as a label**, and never feed it to a model.
