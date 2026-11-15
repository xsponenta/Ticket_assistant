# Model selection: bake-off on val data

_Run 2026-11-15T13:24:37+00:00 · git `87b1ed8-dirty` · `scripts/model_bakeoff.py` · results `eval/results/model_bakeoff_20261115T132437Z.json` · total cost $1.0923. Val split only; no test item was used._

Prompts: `bakeoff_classification/v1`, `bakeoff_extraction/v1`, `bakeoff_simulator/v1`. Items: 40 classification (10 per class, seed 42), 10 extraction (richest val bugs), 5 simulator dialogues × 3 questions.

## Configurations

| Config | Provider | $/1M in | $/1M out | Reasoning as served | Reasoning in this run |
|---|---|---:|---:|---|---|
| `qwen/qwen3.5-9b` | qwen | 0.023 | 0.033 | off | as served |
| `deepseek/deepseek-v4.1-flash-1017` | deepseek | 0.150 | 0.600 | default-on (high) | as served |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | deepseek | 0.150 | 0.600 | default-on (high) | {"effort": "none"} |
| `elorian/glimpse` | elorian | 0.600 | 3.000 | off | as served |
| `elorian/glimpse@reasoning-min` | elorian | 0.600 | 3.000 | off | {"enabled": false} |
| `qwen/qwen3.5-27b` | qwen | 0.260 | 2.600 | off | as served |
| `qwen/qwen3.5-27b@reasoning-min` | qwen | 0.260 | 2.600 | off | {"enabled": false} |
| `bytedance-seed/seed-2-1-turbo` | bytedance-seed | 0.500 | 2.500 | off | as served |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | bytedance-seed | 0.500 | 2.500 | off | {"enabled": false} |
| `google/gemini-3.5-flash-lite` | google | 0.300 | 2.500 | mandatory (minimal) | as served |

## Classification (n = 40, 10 per class)

| Config | Accuracy | Macro-F1 | 95% CI (bootstrap) | First-try valid | Repairs | Failures |
|---|---:|---:|---|---:|---:|---:|
| `qwen/qwen3.5-9b` | 0.500 | **0.440** | 0.32–0.55 | 100% | 0% | 0 |
| `deepseek/deepseek-v4.1-flash-1017` | 0.450 | **0.396** | 0.27–0.51 | 100% | 0% | 0 |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | 0.450 | **0.393** | 0.27–0.50 | 100% | 0% | 0 |
| `elorian/glimpse` | 0.450 | **0.394** | 0.26–0.50 | 100% | 0% | 0 |
| `elorian/glimpse@reasoning-min` | 0.425 | **0.359** | 0.23–0.47 | 100% | 0% | 0 |
| `qwen/qwen3.5-27b` | 0.425 | **0.368** | 0.24–0.48 | 98% | 2% | 0 |
| `qwen/qwen3.5-27b@reasoning-min` | 0.450 | **0.395** | 0.27–0.51 | 85% | 15% | 1 |
| `bytedance-seed/seed-2-1-turbo` | 0.425 | **0.374** | 0.25–0.48 | 100% | 0% | 0 |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | 0.450 | **0.395** | 0.27–0.51 | 100% | 0% | 0 |
| `google/gemini-3.5-flash-lite` | 0.425 | **0.386** | 0.25–0.50 | 100% | 0% | 0 |

## Bug-field extraction (n = 10)

Grounding check (no LLM): a confirmed field is *possibly invented* if < 60% of its content words occur in the input, or if `environment` is confirmed although the input has no version/environment mention (EDA `version_env` regex).

| Config | First-try valid | Repairs | Failures | Confirmed fields | Grounded-confirmed | Possibly invented |
|---|---:|---:|---:|---:|---:|---:|
| `qwen/qwen3.5-9b` | 100% | 0% | 0 | 49 | 92% | **4** |
| `deepseek/deepseek-v4.1-flash-1017` | 100% | 0% | 0 | 48 | 100% | **0** |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | 100% | 0% | 0 | 48 | 100% | **0** |
| `elorian/glimpse` | 100% | 0% | 0 | 49 | 98% | **1** |
| `elorian/glimpse@reasoning-min` | 100% | 0% | 0 | 50 | 94% | **3** |
| `qwen/qwen3.5-27b` | 90% | 10% | 0 | 49 | 100% | **0** |
| `qwen/qwen3.5-27b@reasoning-min` | 70% | 30% | 2 | 40 | 95% | **2** |
| `bytedance-seed/seed-2-1-turbo` | 100% | 0% | 0 | 50 | 98% | **1** |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | 90% | 10% | 0 | 49 | 98% | **1** |
| `google/gemini-3.5-flash-lite` | 100% | 0% | 0 | 46 | 100% | **0** |

## Simulated user (n = 5 dialogues × 3 questions)

Q3 asks for information that is **not** in the hidden ticket (cluster size, executor memory). In character = a reply passes every check that applies to it. Q3 honest = admits not knowing (or answers only with ticket-grounded facts) and invents no number.

_Simulator checks v2, revised after reading the v1 transcripts and before choosing models: (1) the Q1 'volunteered' check no longer counts Spark versions, because in 3 of the 5 tickets the expected behaviour itself is a version regression (every model failed v1 on those 3); (2) Q3 honesty also accepts phrasings like "I don't have those details" and answers grounded in the ticket (local run, single node, Docker, spark-shell)._

| Config | In character | Q3 honest | no_ai_mention | brief | first_person | no_ticket_dump | no_volunteered_env | honest_about_unknown | no_invented_number | Failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen/qwen3.5-9b` | 93% | 4/5 | 100% | 100% | 100% | 100% | 100% | 80% | 100% | 0 |
| `deepseek/deepseek-v4.1-flash-1017` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `elorian/glimpse` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `elorian/glimpse@reasoning-min` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `qwen/qwen3.5-27b` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `qwen/qwen3.5-27b@reasoning-min` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `bytedance-seed/seed-2-1-turbo` | 93% | 4/5 | 100% | 100% | 100% | 100% | 100% | 80% | 100% | 0 |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| `google/gemini-3.5-flash-lite` | 100% | 5/5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |

## Latency and cost (calls actually paid for, incl. repairs)

| Config | Calls | p50 ms | p95 ms | Completion tok | Reasoning tok | Total $ | $ / 100 calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| `qwen/qwen3.5-9b` | 65 | 1247 | 5101 | 11,576 | 4,235 | 0.0030 | 0.0046 |
| `deepseek/deepseek-v4.1-flash-1017` | 65 | 1335 | 10333 | 30,163 | 22,769 | 0.0189 | 0.0291 |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | 65 | 1023 | 2938 | 8,052 | 0 | 0.0105 | 0.0162 |
| `elorian/glimpse` | 65 | 1812 | 23226 | 63,233 | 55,815 | 0.2177 | 0.3349 |
| `elorian/glimpse@reasoning-min` | 65 | 851 | 3357 | 8,113 | 0 | 0.0510 | 0.0784 |
| `qwen/qwen3.5-27b` | 67 | 10446 | 72646 | 92,985 | 88,502 | 0.2410 | 0.3597 |
| `qwen/qwen3.5-27b@reasoning-min` | 74 | 1789 | 14489 | 9,830 | 0 | 0.0414 | 0.0559 |
| `bytedance-seed/seed-2-1-turbo` | 65 | 13764 | 139402 | 150,530 | 141,752 | 0.4120 | 0.6339 |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | 66 | 2341 | 10108 | 8,809 | 0 | 0.0591 | 0.0895 |
| `google/gemini-3.5-flash-lite` | 65 | 948 | 1928 | 6,631 | 0 | 0.0377 | 0.0580 |

## Reasoning as served vs minimised

| Config | Macro-F1 | Extraction first-try | Possibly invented | p50 ms | Reasoning tok | $ / 100 calls |
|---|---:|---:|---:|---:|---:|---:|
| `deepseek/deepseek-v4.1-flash-1017` | 0.396 | 100% | 0 | 1335 | 22,769 | 0.0291 |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | 0.393 | 100% | 0 | 1023 | 0 | 0.0162 |
| `elorian/glimpse` | 0.394 | 100% | 1 | 1812 | 55,815 | 0.3349 |
| `elorian/glimpse@reasoning-min` | 0.359 | 100% | 3 | 851 | 0 | 0.0784 |
| `qwen/qwen3.5-27b` | 0.368 | 90% | 0 | 10446 | 88,502 | 0.3597 |
| `qwen/qwen3.5-27b@reasoning-min` | 0.395 | 70% | 2 | 1789 | 0 | 0.0559 |
| `bytedance-seed/seed-2-1-turbo` | 0.374 | 100% | 1 | 13764 | 141,752 | 0.6339 |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | 0.395 | 90% | 1 | 2341 | 0 | 0.0895 |

## Extraction examples (first 3 of the 10 bugs, side by side)

✓ = confirmed, — = missing, ⚠ = possibly invented (grounding check). Values cut to 160 characters; full outputs in `eval/results/model_bakeoff_20261115T132437Z.json`.

### SPARK-46706

<details><summary>Input given to the models (first 800 characters)</summary>

````text
percentile_approx regression since Spark 2.4
Originally reported in SPARK-40499, I'm opening a new issue as that original one was closed. It's not entirely clear if this regression exists on HEAD, but I haven't seen any changes that I would expect to address this. Here's what I reported in the other ticket.

---

Chiming in, I'm currently hitting a similar issue while doing upgrades from Spark 2.4 to Spark 3.1.

In our case, we have an application with two queries that take `percentile_approx` of a fairly large dataset and reduce to only a few rows (reading 37 billion rows and aggregating to ~100 and ~7000 rows, with different groupBy keys respectively). This roughly what the query looks like:

```java
select
    col1,
    percentile_approx(col2, 0.95) as q_95,
    percentile_approx(col2, 
````

</details>

**summary**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | percentile_approx regression since Spark 2.4 |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | percentile_approx regression since Spark 2.4 |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | percentile_approx regression since Spark 2.4: shuffle read stage drastically slower on Spark 3.1 compared to Spark 2.4 |
| `elorian/glimpse` | ✓ | percentile_approx regression since Spark 2.4 |
| `elorian/glimpse@reasoning-min` | ✓ | percentile_approx regression since Spark 2.4 |
| `qwen/qwen3.5-27b` | ✓ | percentile_approx regression since Spark 2.4 |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | percentile_approx regression since Spark 2.4 |
| `bytedance-seed/seed-2-1-turbo` | ✓ | percentile_approx regression since Spark 2.4 |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | percentile_approx regression since Spark 2.4 |
| `google/gemini-3.5-flash-lite` | ✓ | percentile_approx regression since Spark 2.4 |

**steps_to_reproduce**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as q_99, percentile_approx(col2, 0.99) - percentile_approx(col2, 0.95) as q_d… |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Run a query aggregating a large dataset with percentile_approx, e.g.: ```sql select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) … |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as q_99, percentile_approx(col2, 0.99) - percentile_approx(col2, 0.95) as q_d… |
| `elorian/glimpse` | ✓ | Run a large aggregation query such as: sql select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as q_99, percentile_approx(col2, 0… |
| `elorian/glimpse@reasoning-min` | ✓ | Run a query aggregating a large dataset (37 billion rows) using `percentile_approx` with groupBy, then join the result back to the source using a broadcast hin… |
| `qwen/qwen3.5-27b` | ✓ | Run query on 37 billion rows upgrading from Spark 2.4 to Spark 3.1: ```sql select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as… |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as q_99, percentile_approx(col2, 0.99) - percentile_approx(col2, 0.95) as q_d… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Run a SQL aggregation query with multiple percentile_approx calls on a large dataset (e.g., 37 billion rows) grouped by a key column. Example query: ```sql sel… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Run a query that groups by a column and computes multiple percentile_approx aggregations on a large dataset (37 billion rows, aggregating to ~100 rows), then u… |
| `google/gemini-3.5-flash-lite` | ✓ | select col1, percentile_approx(col2, 0.95) as q_95, percentile_approx(col2, 0.99) as q_99, percentile_approx(col2, 0.99) - percentile_approx(col2, 0.95) as q_d… |

**expected_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | Shuffle read stage should take approximately 15 minutes (similar to Spark 2.4). |
| `deepseek/deepseek-v4.1-flash-1017` | — |  |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Shuffle read stage should perform similarly to Spark 2.4 (15 minutes) |
| `elorian/glimpse` | ✓ | No performance regression: shuffle read should remain comparable to Spark 2.4 (about 15 minutes), not become drastically slower. |
| `elorian/glimpse@reasoning-min` | ✓ | Shuffle read stage performance should be comparable to Spark 2.4 (approx. 15 minutes). |
| `qwen/qwen3.5-27b` | ✓ | shuffle read stage takes 15 minutes (similar to Spark 2.4) |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | Shuffle read stage should take roughly 15 minutes (similar to Spark 2.4 performance). |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Shuffle read performance for percentile_approx aggregations should be comparable to Spark 2.4 (around 15 minutes for the 37 billion row test case aggregating t… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Shuffle read stage performance should be comparable to Spark 2.4 (around 15 minutes for the shuffle read stage with default precision 10000). |
| `google/gemini-3.5-flash-lite` | — |  |

**actual_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | Shuffle read stage takes 5.7 hours (with precision 100) or exceeds 15 hours (with default precision 10000), compared to 15 minutes in Spark 2.4. |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Shuffle write is roughly the same time and size, but shuffle read is drastically slower: 15 minutes on Spark 2.4 vs 5.7 hours on Spark 3.1 after reducing perce… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Shuffle read stage takes 5.7 hours on Spark 3.1 (after reducing percentile_approx precision from default 10000 to 100); at default precision the stage exceeded… |
| `elorian/glimpse` | ✓ | Shuffle read is drastically slower: 15 minutes on Spark 2.4 vs 5.7 hours on Spark 3.1 after reducing percentile_approx precision to 100; at default precision 1… |
| `elorian/glimpse@reasoning-min` | ✓ | Shuffle read stage is drastically slower in Spark 3.1 compared to Spark 2.4. In Spark 2.4, shuffle read took 15 minutes. In Spark 3.1, it took 5.7 hours (with … |
| `qwen/qwen3.5-27b` | ✓ | shuffle read stage takes 5.7 hours on Spark 3.1 (exceeding 15 hours with default precision) |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | Shuffle read stage is drastically slower, taking 5.7 hours on Spark 3.1 (with precision reduced to 100) or exceeding 15 hours (with default precision 10000). |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Shuffle read stage for percentile_approx aggregations is drastically slower in Spark 3.1 compared to Spark 2.4: - Spark 2.4: 15 minutes for shuffle read (396 t… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Shuffle read stage is drastically slower in Spark 3.1: 5.7 hours even with precision reduced from the default 10000 to 100; at default precision the stage exce… |
| `google/gemini-3.5-flash-lite` | ✓ | The shuffle read is drastically slower on Spark 3.1 compared to Spark 2.4, increasing from 15 minutes to 5.7 hours (and exceeding 15 hours when left at default… |

**environment**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ⚠ ✓ | Spark 2.4 and Spark 3.1 (and 3.2/3.3 mentioned), Java API, deployment environment not explicitly specified (inferred production cluster based on data size and … |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Spark 2.4 and Spark 3.1; SQL |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Spark 2.4 and Spark 3.1; SQL |
| `elorian/glimpse` | ✓ | Spark 2.4 and Spark 3.1; SQL; deployment not specified. |
| `elorian/glimpse@reasoning-min` | ⚠ ✓ | Spark 2.4 vs Spark 3.1 (upgrading from 2.4 to 3.1). API language: SQL/Java. Deployment: Not explicitly stated, but implies a cluster environment with AQE enabl… |
| `qwen/qwen3.5-27b` | ✓ | Spark 2.4 to Spark 3.1, SQL API |
| `qwen/qwen3.5-27b@reasoning-min` | ⚠ ✓ | Spark 2.4 and Spark 3.1; API language: SQL (via Java/Scala context); Deployment: Not explicitly stated (mentions broadcast and shuffle, implying a cluster envi… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Spark versions: 2.4 (baseline), 3.1 (regression); API language: SQL |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Spark versions: 2.4, 3.1; API: SQL; deployment not specified. |
| `google/gemini-3.5-flash-lite` | ✓ | Spark 2.4 to Spark 3.1, Java API |

### SPARK-44339

<details><summary>Input given to the models (first 800 characters)</summary>

````text
spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have [SELECT] privilege on [<database>/<hive table>] when reads hive view
*Problem statement*

A hive view is created using beeline to restrict the users from accessing the original hive table since the data contains sensitive information.

For illustration purpose, let's consider a sensitive table as emp_db.employee with columns id, name, salary created through beeline by user '*userA*'

```java
create external table emp_db.employee (id int, name string, salary double) location '<hdfs_path>'
```

A view is created using beeline by the same user '*userA*'

```java
ate view empview_db.emp_v  as select id,name from emp_db.employee'
```

Fro
````

</details>

**summary**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | spark3-shell errors with org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not … |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `elorian/glimpse` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `elorian/glimpse@reasoning-min` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `qwen/qwen3.5-27b` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `qwen/qwen3.5-27b@reasoning-min` | error | LLMOutputError: BugExtraction validation failed after one repair: 1 validation error for BugExtraction Input should be a valid dictionary or instance of BugExt… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | spark3-shell throws org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does not have [SELECT] pr… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied: user [AD user] does not have … |
| `google/gemini-3.5-flash-lite` | ✓ | spark3-shell errors org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table <hive_table_name>. Permission denied when reads hive view |

**steps_to_reproduce**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | 1. ssh to edge node where beeline is available using *userB* 1. Try executing following queries 1. select * from emp_db.employee *;* 1. desc formatted empview_… |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | 1. As userA via beeline: create external table emp_db.employee (id int, name string, salary double) location '<hdfs_path>' 2. As userA via beeline: create view… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | 1. ssh to edge node where beeline is available using userB 2. Try executing following queries - select * from emp_db.employee; - desc formatted empview_db.emp_… |
| `elorian/glimpse` | ✓ | 1. As userA, create the external table via beeline: `create external table emp_db.employee (id int, name string, salary double) location '<hdfs_path>'`. 2. As … |
| `elorian/glimpse@reasoning-min` | ✓ | 1. Create external table emp_db.employee and view empview_db.emp_v via beeline as userA. 2. Grant userB SELECT permission on empview_db.emp_v via Ranger. 3. As… |
| `qwen/qwen3.5-27b` | ✓ | 1. Create table emp_db.employee and view empview_db.emp_v via beeline. 2. Define Ranger policy for userB on empview_db.emp_v with SELECT permission. 3. SSH to … |
| `qwen/qwen3.5-27b@reasoning-min` | error | LLMOutputError: BugExtraction validation failed after one repair: 1 validation error for BugExtraction Input should be a valid dictionary or instance of BugExt… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | 1. As userA via beeline: - Create external table: `create external table emp_db.employee (id int, name string, salary double) location '<hdfs_path>'` - Create … |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | 1. Create external table emp_db.employee (id int, name string, salary double) via beeline as userA. 2. Create view empview_db.emp_v as select id,name from emp_… |
| `google/gemini-3.5-flash-lite` | ✓ | 1. ssh to edge node where beeline is available using userB 2. Try executing following queries: - select * from emp_db.employee; - desc formatted empview_db.emp… |

**expected_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | The query should work fine, similar to when executed via beeline, as the user has SELECT permission on the view. |
| `deepseek/deepseek-v4.1-flash-1017` | — |  |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | — |  |
| `elorian/glimpse` | — |  |
| `elorian/glimpse@reasoning-min` | ✓ | The query should work fine without any issues, similar to how it works in beeline. |
| `qwen/qwen3.5-27b` | ✓ | let '*userB*' to access database - empview_db and table - emp_v with SELECT permission |
| `qwen/qwen3.5-27b@reasoning-min` | error | LLMOutputError: BugExtraction validation failed after one repair: 1 validation error for BugExtraction Input should be a valid dictionary or instance of BugExt… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | UserB with SELECT privilege on Hive view empview_db.emp_v should be able to access the view (e.g., retrieve its schema) in spark3-shell without needing SELECT … |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | — |  |
| `google/gemini-3.5-flash-lite` | — |  |

**actual_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Beeline queries select * from emp_db.employee and desc formatted empview_db.emp_v work fine. In spark3-shell, spark.table("empview_db.emp_v").schema fails with… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |
| `elorian/glimpse` | ✓ | Running `spark.table("empview_db.emp_v").schema` in spark3-shell fails with `org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveExc… |
| `elorian/glimpse@reasoning-min` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |
| `qwen/qwen3.5-27b` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |
| `qwen/qwen3.5-27b@reasoning-min` | error | LLMOutputError: BugExtraction validation failed after one repair: 1 validation error for BugExtraction Input should be a valid dictionary or instance of BugExt… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Running `spark.table("empview_db.emp_v").schema` in spark3-shell as userB throws org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.Hiv… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |
| `google/gemini-3.5-flash-lite` | ✓ | org.apache.spark.sql.AnalysisException: org.apache.hadoop.hive.ql.metadata.HiveException: Unable to fetch table employee. Permission denied: user [userB] does … |

**environment**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | Spark version 3.3.0.3.3.7180.0-274, API language Scala, deployment YARN |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Spark version 3.3.0.3.3.7180.0-274; Scala version 2.12.15; Java 1.8.0_181; spark3-shell --deploy-mode client; master = yarn. |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Spark version 3.3.0.3.3.7180.0-274; API language Scala; deployment YARN (master = yarn) |
| `elorian/glimpse` | ✓ | Spark 3.3.0.3.3.7180.0-274; spark3-shell using Scala 2.12.15 (Java 1.8.0_181); deployment: YARN client (`--deploy-mode client`, master = yarn). |
| `elorian/glimpse@reasoning-min` | ✓ | Spark version 3.3.0.3.3.7180.0-274, Scala 2.12.15, Java 1.8.0_181, deployment mode: client (master = yarn) |
| `qwen/qwen3.5-27b` | ✓ | Spark version 3.3.0.3.3.7180.0-274, Scala, YARN (client mode) |
| `qwen/qwen3.5-27b@reasoning-min` | error | LLMOutputError: BugExtraction validation failed after one repair: 1 validation error for BugExtraction Input should be a valid dictionary or instance of BugExt… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Spark 3.3.0.3.3.7180.0-274, Scala API, YARN deployment (client mode) |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Spark 3.3.0.3.3.7180.0-274, Scala 2.12.15, spark3-shell, YARN deploy mode client, with Hive and Ranger for authorization. |
| `google/gemini-3.5-flash-lite` | ✓ | Spark version 3.3.0.3.3.7180.0-274, Scala version 2.12.15, Java 1.8.0_181, YARN deployment mode |

### SPARK-52965

<details><summary>Input given to the models (first 800 characters)</summary>

````text
[SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation
A gRPC connection failure occurs when executing a PySpark DataFrame action that involves a complex, dynamically generated schema transformation. The Spark Connect server terminates the connection, leading to an `Encountered end-of-stream mid-frame` error.
The issue is reproducible in a minimal Docker environment and persists even after eliminating network factors and increasing gRPC message size limits, indicating a potential core issue rather than a configuration problem.

Steps to Reproduce
This issue can be fully reproduced locally using the following Docker setup.
*1. Build the Docker Image*
Use the following `Dockerfile` to create the test environment.

```java
# Dockerfile
FROM apache/spa
````

</details>

**summary**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | gRPC connection failure "Encountered end-of-stream mid-frame" when executing a PySpark DataFrame action involving a complex, dynamically generated schema trans… |
| `elorian/glimpse` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `elorian/glimpse@reasoning-min` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `qwen/qwen3.5-27b` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `bytedance-seed/seed-2-1-turbo` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |
| `google/gemini-3.5-flash-lite` | ✓ | [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation |

**steps_to_reproduce**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | 1. Build Docker image using provided Dockerfile (apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu). 2. Run Spark Connect server with maxInboundMessageSize=… |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Build a Docker image from `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` with `python3-pip`; run the Spark Connect server with `spark-submit --class or… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Build Docker image from apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu; run SparkConnectServer with spark.connect.grpc.maxInboundMessageSize=104857600; e… |
| `elorian/glimpse` | ✓ | 1. Build a Docker image from apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu. 2. Start the Spark Connect server in Docker with spark.connect.grpc.maxInbou… |
| `elorian/glimpse@reasoning-min` | ✓ | 1. Build Docker image from `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu`. 2. Run Spark Connect server with `spark.connect.grpc.maxInboundMessageSize=1… |
| `qwen/qwen3.5-27b` | ✓ | 1. Build Docker image: `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` 2. Run Server: `spark-submit --class org.apache.spark.sql.connect.service.SparkCo… |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | 1. Build Docker image using provided Dockerfile (apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu). 2. Run Spark Connect server: docker run -d --name spark… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | 1. Build a Docker image using the provided Dockerfile (based on apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu, with python3-pip installed). 2. Start a S… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | 1. Build a Docker image from apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu with python3-pip installed. 2. Start a Spark Connect server container on port… |
| `google/gemini-3.5-flash-lite` | ✓ | 1. Build the Docker image using apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu. 2. Run the Spark Connect server in a container. 3. Run the PySpark Client… |

**expected_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | The `final_agg.show()` command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `elorian/glimpse` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `elorian/glimpse@reasoning-min` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `qwen/qwen3.5-27b` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `bytedance-seed/seed-2-1-turbo` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |
| `google/gemini-3.5-flash-lite` | ✓ | The final_agg.show() command should execute successfully without any gRPC or network-related errors, printing the transformed DataFrame to the console. |

**actual_behavior**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | The command fails with a gRPC error: 'Encountered end-of-stream mid-frame'. Client error: pyspark.errors.exceptions.connect.SparkConnectGrpcException with stat… |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | `final_agg.show()` fails with client-side `pyspark.errors.exceptions.connect.SparkConnectGrpcException`: `StatusCode.INTERNAL`, details `Encountered end-of-str… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | final_agg.show() fails with client-side: pyspark.errors.exceptions.connect.SparkConnectGrpcException: <_InactiveRpcError of RPC that terminated with: status = … |
| `elorian/glimpse` | ✓ | final_agg.show() fails. Client error: pyspark.errors.exceptions.connect.SparkConnectGrpcException with StatusCode.INTERNAL and details 'Encountered end-of-stre… |
| `elorian/glimpse@reasoning-min` | ✓ | The `final_agg.show()` command fails with `SparkConnectGrpcException: Encountered end-of-stream mid-frame` (StatusCode.INTERNAL). Server logs show `WARN NettyS… |
| `qwen/qwen3.5-27b` | ✓ | The `final_agg.show()` command fails with `SparkConnectGrpcException: ... Encountered end-of-stream mid-frame`. Server logs show `WARN NettyServerStream: Excep… |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | Client-Side Error: pyspark.errors.exceptions.connect.SparkConnectGrpcException: <_InactiveRpcError of RPC that terminated with: status = StatusCode.INTERNAL de… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | The `final_agg.show()` command fails with a gRPC connection error: - Client-side: `pyspark.errors.exceptions.connect.SparkConnectGrpcException` with status `St… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | final_agg.show() fails with a gRPC INTERNAL error 'Encountered end-of-stream mid-frame'. Client-side: SparkConnectGrpcException with StatusCode.INTERNAL and th… |
| `google/gemini-3.5-flash-lite` | ✓ | pyspark.errors.exceptions.connect.SparkConnectGrpcException: <_InactiveRpcError of RPC that terminated with: status = StatusCode.INTERNAL details = "Encountere… |

**environment**

| Config | Status | Value |
|---|---|---|
| `qwen/qwen3.5-9b` | ✓ | Spark version: 4.0.0; API language: Python (PySpark); Deployment: Docker container (local simulation of same-pod scenario). |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ | Spark 4.0.0 Docker image `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu`; PySpark client via `pyspark --remote sc://localhost:15002`; local Docker conta… |
| `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | ✓ | Spark 4.0.0 (apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu), PySpark client via Spark Connect (pyspark --remote sc://localhost:15002), local Docker cont… |
| `elorian/glimpse` | ✓ | Spark 4.0.0 (apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu); PySpark/Spark Connect; Spark Connect server run in Docker, client in the same container via… |
| `elorian/glimpse@reasoning-min` | ✓ | Spark 4.0.0 (apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu), PySpark API, Docker deployment (local container, client and server in same container via lo… |
| `qwen/qwen3.5-27b` | ✓ | Spark 4.0.0, PySpark (Python), Docker (local), Spark Connect (gRPC), Java 17 (also tested Java 21) |
| `qwen/qwen3.5-27b@reasoning-min` | ✓ | Spark version: 4.0.0 (from image apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu). API language: Python (PySpark). Deployment: Local (Docker container, cl… |
| `bytedance-seed/seed-2-1-turbo` | ✓ | Spark version: 4.0.0; API language: Python (PySpark); Deployment: Local Docker environment (Spark Connect server and PySpark client running in the same contain… |
| `bytedance-seed/seed-2-1-turbo@reasoning-min` | ✓ | Spark 4.0.0, Python (PySpark) API, Spark Connect deployment in Docker (client and server in same container connecting via localhost), base image apache/spark:4… |
| `google/gemini-3.5-flash-lite` | ✓ | Spark 4.0.0, Python, Docker container |

## Proposal (rule-based; final choice is yours)

- **Generator:** among configs with macro-F1 ≥ best − 0.05, extraction first-try valid ≥ 90% and possibly invented ≤ 1, the cheapest per 100 calls.
- **Judge:** the strongest config (macro-F1, then extraction first-try valid) from a *different provider* than the generator.
- **Simulator:** the cheapest config with in-character ≥ 90% and Q3 honest ≥ 4/5.

| Role | Proposed config | Pool that met the rule |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017@reasoning-min` | `deepseek/deepseek-v4.1-flash-1017`, `deepseek/deepseek-v4.1-flash-1017@reasoning-min`, `elorian/glimpse`, `bytedance-seed/seed-2-1-turbo@reasoning-min` |
| judge | `qwen/qwen3.5-9b` | different provider than the generator |
| simulator | `qwen/qwen3.5-9b` | `qwen/qwen3.5-9b`, `deepseek/deepseek-v4.1-flash-1017`, `deepseek/deepseek-v4.1-flash-1017@reasoning-min`, `elorian/glimpse`, `elorian/glimpse@reasoning-min`, `qwen/qwen3.5-27b`, `qwen/qwen3.5-27b@reasoning-min`, `bytedance-seed/seed-2-1-turbo`, `bytedance-seed/seed-2-1-turbo@reasoning-min`, `google/gemini-3.5-flash-lite` |

## Review and recommendation (hand-written, 2026-11-15)

_This section is written by hand and inserted with `--review reports/model_selection_review.md`. The tables above are generated._

### What changed between runs
1. **Parser bug in `src/llm.py`, now fixed.**
   - The bug: valid JSON replies were rejected when a field value contained a Markdown code block, e.g. `"steps_to_reproduce": "```python …```"`. The parser extracted the inner code block instead of the JSON.
   - Effect on the first full run: extraction validity was understated (e.g. seed-2-1-turbo 30% → 100% first-try valid), and 6 of the 7 failures were caused by this bug (the seventh was a reply that wasn't a JSON object).
   - All first replies were re-parsed from the cache. The rerun cost $0.008. Regression tests were added in `tests/test_llm.py`.
2. **Simulator checks revised after reading the transcripts (v1 → v2).** The automatic checks were changed *after* reading the v1 transcripts and *before* any model was chosen. Two v1 checks measured the heuristic, not the models:
   - **Q1 "volunteered version".** In v1 it counted any Spark version in the answer to Q1 (expected vs actual behaviour). In 3 of the 5 tickets, the expected behaviour itself is a version regression ("percentile_approx regression since Spark 2.4"), so naming the version is the honest answer. Every configuration failed v1 on exactly those 3 tickets (40% pass rate for all 10), which capped all of them at 80% in character. **v2** counts only environment details that were not asked for (Python/Java/Scala versions, YARN, Kubernetes, EMR, …), not Spark versions.
   - **Q3 "admits not knowing".** The v1 phrase list missed honest answers such as "I don't have information about the number of nodes" and "I don't have those details". It also counted ticket-grounded answers as dishonest (e.g. "I ran it locally in spark-shell" when the ticket says so). **v2** accepts these phrasings, and accepts local / single-node / Docker / spark-shell answers **only if the ticket mentions them**. Invented numbers still fail.

   v2 is not lenient across the board: qwen3.5-9b still fails Q3 on SPARK-51533 because "I am running this locally" is not in its ticket. The one remaining miss for seed-2-1-turbo (as served) is a false negative of the v2 phrase list. All transcripts are in the transcripts file, with the checks each reply failed.
3. **Total bake-off spend:** $1.25 (smoke runs $0.15 + full run $1.09 + rerun $0.008).

### Findings
- **Classification does not separate the models.**
  - Macro-F1 ranges from 0.36 to 0.44, and all 95% CIs overlap.
  - No configuration ever predicted *idea* correctly: 82 of the 100 idea predictions across configs went to *feature*.
  - 18 of the 40 items are wrong for every configuration.

  This is a problem with the label definition for C1: SPARK Wish tickets read like concrete feature requests. It is not a model difference, so classification should not drive the model choice. C1 needs few-shot examples from **train** and a revised idea definition.
- **Reasoning does not pay off for these tasks.** The reasoning-minimised variants match the as-served ones on macro-F1 and extraction validity, at 4–7× lower cost (glimpse, qwen3.5-27b, seed) and with 1.3–6× lower p50 latency. One exception: glimpse with reasoning minimised produces 3 possibly-invented fields, against 1.
- **OpenRouter's reasoning metadata is unreliable.** glimpse, qwen3.5-27b and seed-2-1-turbo are listed as reasoning *off*, yet as served they produced 56k–142k reasoning tokens. Every role should set `reasoning` explicitly.
- **Grounding.** gemini-3.5-flash-lite and both DeepSeek variants: 100% grounded, 0 flags. The flags I reviewed are real inferences, not word-matching artefacts:
  - qwen3.5-9b: "inferred production cluster based on data size…";
  - glimpse@min: "Spark 3.0+ (implied by warning message)".

  The flag on seed's `expected_behavior` is a borderline paraphrase of an implicit expectation. Gemini marked that same field *missing*.
- **Simulator.** Every configuration stays in character.
  - qwen3.5-9b's one miss is real: "I am running this locally" is not in the ticket.
  - seed-2-1-turbo's miss is a heuristic false negative: "I don't have the exact cluster node count…" is honest.

### Recommendation (differs from the rule for the judge)

| Role | Recommended | Why |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017` with `reasoning: {"effort": "none"}` | The rule's pick. $0.016 per 100 calls, p50 1.0 s / p95 2.9 s, 100% first-try valid, 0 possibly-invented fields, simulator 5/5. |
| judge | `google/gemini-3.5-flash-lite` | Different provider. 100% first-try valid, 0 possibly-invented fields, 100% grounded, simulator 5/5, p95 1.9 s, $0.058 per 100 calls. The rule picked qwen3.5-9b only for the highest macro-F1, which is noise here (CI 0.32–0.55 overlaps every config); qwen3.5-9b also has the most possibly-invented fields (4). Caveat: a "lite" model. AGENTS.md requires calibrating the judge against human scores; if agreement is low, switch to a strong-tier judge (e.g. `anthropic/claude-fable-5.2`). |
| simulator | `qwen/qwen3.5-9b` (the rule's pick); alternative `qwen/qwen3.5-27b` with reasoning off | qwen3.5-9b is the cheapest ($0.0046 per 100 calls), stays in character in 93% of replies, and invented one fact in 15 replies. It is a third provider, different from both generator and judge. qwen3.5-27b with reasoning off scores 100% in character and 5/5 honesty at $0.056 per 100 calls: choose it if a simulator that never invents facts matters more than a negligible cost difference. |

### Needed before `config.yaml` can be updated
- **Per-role reasoning setting.** `config.yaml` has none, and the recommended generator needs `{"effort": "none"}`.
- **Proposal:** add `reasoning: {generator: …, judge: …, simulator: …}` to `config.yaml`, used by `src/llm.py` as the role default (like temperature).
- **Timing:** done together with L2, after confirmation.

### Confirmed decision (2026-11-15, logged as L2 in `reports/decisions.md`)

| Role | Model | Reasoning |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017` | off (`{effort: none}`) |
| judge | `google/gemini-3.5-flash-lite` | `{effort: minimal}` (mandatory reasoning; lowest effort) |
| simulator | `qwen/qwen3.5-27b` | off (`{enabled: false}`) |

- **Judge:** the rule's pick was overridden (see above). It must be calibrated against human scores before its numbers are reported.
- **Simulator:** `qwen3.5-27b` was chosen over the cheaper `qwen3.5-9b` because honesty matters more than about $0.05 per 100 calls. An invented fact would corrupt the end-to-end fact-recall and hallucination metrics, and this is also a different family from the generator.
- **Configuration:** the per-role reasoning settings are in `config.yaml` (`reasoning.<role>`), and `src/llm.py` reads them like temperature.

## Limitations

- Small samples: 40 classification items (macro-F1 CIs are wide), 10 bugs, 5 dialogues. The bake-off ranks models for a first choice; it is not an evaluation of the final components.
- Zero-shot prompts (`*/v1`); component prompts will differ.
- Grounding and simulator checks are heuristics (word overlap and regex); read the examples and transcripts (`eval/results/model_bakeoff_20261115T132437Z_transcripts.md`).
- Prices and model behaviour are as served by OpenRouter on the run date.
