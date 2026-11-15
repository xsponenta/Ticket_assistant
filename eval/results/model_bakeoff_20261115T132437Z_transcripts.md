# Simulator transcripts (model bake-off)

## `qwen/qwen3.5-9b` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to perform similarly to Spark 2.4, taking around 15 minutes. Instead, it took 5.7 hours on Spark 3.1 (even after reducing precision from the default 10,000 to 100), and exceeded 15 hours at the original precision.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.1 (and also tested on Spark 2.4 for comparison), and the queries are written in SQL via a Java application.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have information about the number of nodes in my cluster or the specific executor memory settings in the ticket.

_checks failed: none_

## `qwen/qwen3.5-9b` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to execute successfully and print the transformed DataFrame. Instead, the command failed with a gRPC error: "Encountered end-of-stream mid-frame," which caused the Spark Connect server to terminate the connection.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Apache Spark version 4.0.0 with the Python API (PySpark).

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running the test in a single Docker container environment, so there is only one node. I did not set any specific executor memory configuration for this reproduction case.

_checks failed: none_

## `qwen/qwen3.5-9b` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer the partition column type as TimestampType for folder names containing timestamps with millisecond or microsecond fractions (e.g., `yyyy-MM-dd HH:mm:ss.S`). Instead, Spark incorrectly inferred the type as StringType, causing queries with timestamp literals to return no results.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0 and the Java API, as indicated by the discussion of version 3.0 changes and the Java PoC code provided in my ticket.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the cluster node count or executor memory settings since they were not included in my ticket. I mostly performed validation using a local Spark session configured with `local[*]` mode rather than a distributed cluster. Therefore, I do not have specific details regarding production infrastructure or memory configurations.

_checks failed: none_

## `qwen/qwen3.5-9b` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected the execution time per SHAP iteration to remain consistent with Spark 3.4 (approximately 1s for the small dataset). Instead, after upgrading to Spark 3.5.*, the execution time increased substantially, reaching about 5 seconds for the same task.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark versions 3.5.0 through 3.5.5, and the language API is Python.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running this locally, so I do not have a cluster with multiple nodes. I did not set an explicit executor memory setting in my code; I only configured `spark.task.cpus` later to fix the issue.

_checks failed: honest_about_unknown_

## `qwen/qwen3.5-9b` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected a deterministic LEFT JOIN where unmatched left rows appear with NULLs for right-side fields, as in Spark 2.4.6. Instead, in Spark 3.0.0 the output is non-deterministic: some matched rows reappear without their right-side values, and the truly unmatched row ("has no join partner") disappears entirely.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0 with the Scala API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running this in `spark-shell` for a local demonstration, so I don't have a multi-node cluster configured or specific executor memory settings to report.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to perform roughly like it did on Spark 2.4, around 15 minutes. Instead, on Spark 3.1 the same stage took 5.7 hours even after I reduced the `percentile_approx` precision from the default 10000 to 100, and at the default precision it exceeded 15 hours and hit our application time limits. The shuffle write stayed roughly the same in time and size.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> The regression I observed was on Spark 3.1, during an upgrade from Spark 2.4. The query is SQL, though I showed it in a code block.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure — my ticket doesn't include the cluster node count or executor memory settings. I only reported stage timings, task counts, and shuffle sizes.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected `final_agg.show()` to run successfully and print the transformed DataFrame to the console. Instead, the client failed with a `SparkConnectGrpcException` reporting `StatusCode.INTERNAL` and "Encountered end-of-stream mid-frame", with a matching server-side `NettyServerStream` warning.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 4.0.0 (the `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` image) with the Python API — I'm running PySpark via `pyspark --remote sc://localhost:15002`.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure — my ticket doesn't specify the number of nodes or any executor memory settings. The reproduction is a single Docker container running the Spark Connect server locally, but I didn't record cluster size or memory configuration.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to infer `TimestampType` for partition folder names with fractional seconds like `yyyy-MM-dd HH:mm:ss.S` or `.n`, just as it does for `yyyy-MM-dd HH:mm:ss`. Instead it inferred `StringType`, so queries with timestamp strings returned no results. In my PoC, Spark wrote `partitioncol=2022-11-23 15:59:01.122726` and then read the column back as `string`.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using the Java API for my PoC, and I referenced the changes introduced with Spark 3.0. I don't have an exact Spark version number stated in my ticket, so I'm not sure which precise build I was running.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have that information in my ticket. My PoC just ran locally with `master("local[*]")`, so I wasn't testing on a cluster.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected `mapInPandas` performance to remain consistent with Spark 3.1–3.4 for my computationally intensive SHAP workload. Instead, after upgrading to Spark 3.5.*, execution time increased substantially—about 5–8x in my minimal example.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using PySpark (Python) with `mapInPandas`. I tested Spark 3.5.0 through 3.5.5 and the issue persisted in every release; I also saw it with Spark 4.0.0-preview2.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure—my ticket doesn't specify the number of nodes or the executor memory settings. The minimal reproducible example uses a local Spark session with `coalesce(1)`, but I didn't record cluster or executor memory details.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to return the two matching pairs plus the "has no join partner" row with NULLs on the right side, deterministically, as it did in Spark 2.4.6. Instead, in Spark 3.0.0 the output is non-deterministic: the "has no join partner" row is missing and one of the already-joined left rows is repeated with NULL right-side fields.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 3.0.0 (upgrading from 2.4.6), and the example is written in Scala, run in `spark-shell`.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't mention the cluster size or any executor memory settings. The example is a minimal one I ran in `spark-shell`.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage with percentile_approx to perform similarly to Spark 2.4, but on Spark 3.1 it went from 15 minutes to 5.7 hours (and exceeded 15 hours at the default precision of 10000). I don't have a precise expectation beyond that it shouldn't regress this badly.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm upgrading from Spark 2.4 to Spark 3.1, and I also plan to test on Spark 3.3. The queries are SQL, though I described the snippet in Java-like form.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't include the cluster node count or executor memory settings.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected `final_agg.show()` to execute successfully and print the transformed DataFrame to the console. Instead it fails with a `SparkConnectGrpcException` reporting `StatusCode.INTERNAL` and "Encountered end-of-stream mid-frame", and the server logs show the same error.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 4.0.0 (the `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` image) with the Python API via a pyspark shell connected over Spark Connect.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't specify the cluster node count or executor memory settings. The reproduction was done in a single minimal Docker container.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to infer TimestampType for partition folder names containing fractional seconds, like `colName=2020-04-03 04%3A48%3A28.467`. Instead it inferred StringType for those, so queries with timestamp strings returned no results.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm not sure of the exact Spark version—the ticket mentions Spark 3.0 changes and the `spark.sql.datetime.java8API.enabled` config. For the PoC I used the Java API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know—my ticket doesn't mention cluster size or executor memory settings. The PoC was run locally with `master("local[*]")`.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected mapInPandas performance to stay consistent, as it did across Spark 3.1 through 3.4. Instead, after upgrading to 3.5, execution time increased roughly 5-8x, and I later found SHAP was only using one core instead of all of them.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using PySpark with Spark 3.5.* — I tested every release from 3.5.0 to 3.5.5 and the issue persists in all of them.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't include any details about cluster nodes or executor memory settings.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the left join to produce two matched pairs (A and B) plus the "has no join partner" row with NULLs on the right, as it did in Spark 2.4.6. Instead, in Spark 3.0.0 I get non-deterministic output where "has no join partner" is missing and one of the already-matched left rows is repeated with NULL right-side fields.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 3.0.0 (upgraded from 2.4.6), and the example is in Scala, run in spark-shell.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't mention the cluster size or any executor memory settings. I ran the example in spark-shell.

_checks failed: none_

## `elorian/glimpse` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the Spark 3.1 job to have shuffle read performance comparable to Spark 2.4, especially since the shuffle write stage was roughly the same time and size. Instead, the shuffle read became drastically slower: 15 minutes on Spark 2.4 versus 5.7 hours on Spark 3.1 after reducing the precision to 100. With the default precision of 10000, the stage exceeded 15 hours.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I’m comparing Spark 2.4 to Spark 3.1, with the regression observed on Spark 3.1. The queries are written in SQL.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure about the exact cluster node count or executor memory settings — those details aren't in my notes.

_checks failed: none_

## `elorian/glimpse` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected `final_agg.show()` to run successfully and print the transformed DataFrame to the console. Instead, the command failed with a `SparkConnectGrpcException` saying `Encountered end-of-stream mid-frame`. The Spark Connect server also logged an `INTERNAL: Encountered end-of-stream mid-frame` error.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I’m using Spark 4.0.0 and the Python API through PySpark.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I’m not sure. My ticket doesn’t mention the number of cluster nodes or any executor memory settings.

_checks failed: none_

## `elorian/glimpse` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to infer the partition column as `TimestampType` when the folder name contained a timestamp with millisecond or microsecond fractions. Instead, Spark inferred the column as `StringType`. Because of that, queries using timestamp strings returned no results.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I’m not sure of the exact Spark version, but I mentioned Spark 3.0 in the ticket. The reproduction I used was through the Java API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know. My tests were run locally with `master("local[*]")`, and I didn't mention any cluster node count or executor memory setting in the ticket.

_checks failed: none_

## `elorian/glimpse` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected the SHAP computations inside `mapInPandas` to run with the same performance as in Spark 3.1–3.4. Instead, after upgrading to Spark 3.5, execution time increased by about 5–8x. I later found that the computation was using only one core instead of all available cores.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I’m using Spark 3.5.*, and I tested releases from 3.5.0 through 3.5.5, plus 4.0.0-preview2. I’m using the Python API through PySpark.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure about the exact number of nodes in my cluster, and I didn't note the executor memory setting in my ticket. The reproducible example only sets `spark.sql.execution.arrow.maxRecordsPerBatch` to 1 and uses `coalesce(1)` on the DataFrame.

_checks failed: none_

## `elorian/glimpse` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to return two matching pairs plus the one left-side row with no join partner as NULLs on the right side. Instead, in Spark 3.0.0 the result was non-deterministic: one of the matched left rows appeared again with NULL right-side fields, and the “has no join partner” row was missing.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0, after upgrading from Spark 2.4.6. The reproducible example is written in Scala and run in `spark-shell`.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I’m not sure how many nodes my cluster has. I also don’t know the exact executor memory setting I was using.

_checks failed: none_

## `elorian/glimpse@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to complete in roughly 15 minutes, matching the performance I saw on Spark 2.4. Instead, on Spark 3.1, the shuffle read took 5.7 hours even after reducing the precision to 100, and it exceeded 15 hours when left at the default precision of 10000.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.1, having upgraded from Spark 2.4. The query is written in SQL, though I provided the snippet in a Java-like format.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the exact number of nodes or the specific executor memory settings. My ticket only details the task counts and shuffle sizes for the Spark 2.4 and 3.1 runs.

_checks failed: none_

## `elorian/glimpse@reasoning-min` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to execute successfully and print the transformed DataFrame to the console without any errors. Instead, the command failed with a `SparkConnectGrpcException` indicating an "Encountered end-of-stream mid-frame" error on the client side. The server logs also showed a `StatusRuntimeException` with the same internal error message during message processing.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark version 4.0.0, specifically the `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` Docker image. I am using the Python API (PySpark) via the Spark Connect client.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the exact node count or executor memory settings, as my reproduction environment is a minimal single-node Docker setup. The issue occurs even when running the client and server within the same container using localhost.

_checks failed: none_

## `elorian/glimpse@reasoning-min` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer the partition column type as TimestampType for folder names containing millisecond or microsecond fractions, such as `yyyy-MM-dd HH:mm:ss.S`. Instead, Spark inferred the type as StringType, causing queries with timestamp strings to return no results because the comparison was treated as a string match rather than a timestamp match.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0 and the Java API for my reproduction case.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the cluster node count or executor memory settings, as I reproduced this issue locally using a `local[*]` SparkSession.

_checks failed: none_

## `elorian/glimpse@reasoning-min` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected `mapInPandas` to perform consistently with Spark versions 3.1 through 3.4, where execution times remained stable across upgrades. Instead, after upgrading to Spark 3.5.*, I observed a significant performance degradation of approximately 5-8x per SHAP iteration.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.5.* with the Python API (PySpark), specifically using `mapInPandas`.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes in the cluster, as the ticket does not mention it. I also do not know the exact executor memory setting, as it is not specified in my configuration.

_checks failed: none_

## `elorian/glimpse@reasoning-min` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to output two matching pairs and the one left-side event with no match as NULLs on the right side, just like it did in Spark 2.4.6. Instead, Spark 3.0.0 non-deterministically drops the non-joinable event entirely and instead duplicates one of the successfully joined left-side rows with NULLs on the right.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0, having upgraded from Spark 2.4.6. I am using the Scala API via spark-shell.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the cluster size or executor memory settings, as I was running this in a local spark-shell environment.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to take about 15 minutes, consistent with our experience on Spark 2.4. Instead, on Spark 3.1, that stage took 5.7 hours even after reducing precision, and exceeded 15 hours when left at the default. This performance regression was severe enough to hit our application time limits.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am currently upgrading from Spark 2.4 to Spark 3.1, where I am observing the performance regression. I am using SQL for the queries, as shown in the snippets provided in my ticket. I am not sure about the specific driver language API, though one code block was labeled Java.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I do not have the cluster node count or executor memory settings documented in the ticket details I shared. I focused on the task counts, shuffle statistics, and performance timing differences instead. So I am not sure about those specific configuration values.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to execute successfully and print the transformed DataFrame to the console without errors. Instead, the operation failed with a `SparkConnectGrpcException` reporting `Encountered end-of-stream mid-frame`, and the server logs showed a corresponding `INTERNAL` status exception.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Apache Spark version 4.0.0 with the Python API via the PySpark shell. The Docker image I built is based on `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu`, and the reproduction steps involve executing Python code within a `pyspark` session.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running this test inside a single Docker container locally, so there is no multi-node cluster involved. The reproduction steps do not specify any executor memory settings, only driver and gRPC configurations, so I do not know the executor memory setting.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to infer the partition column as TimestampType even when the folder names included millisecond or microsecond fractions. Instead, Spark incorrectly inferred the type as StringType for those specific timestamp formats. This caused queries sending timestamp strings to return no results because they were matched as strings rather than times.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> 
> 
> I am using the Java API, as I ran a Java PoC to observe Spark's behavior. I mention Spark 3.0 regarding changes in timestamp parsing, but I do not explicitly state the specific version I am running. So I am not sure of the exact version number.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the cluster node count or executor memory settings as those details are not in my ticket. In the Java PoC code I provided, I configured the SparkSession to run in local mode using `master("local[*]")`. I do not have specific information regarding a distributed cluster setup.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected performance to remain consistent with Spark versions 3.1 to 3.4, where all cores were utilized for SHAP computations. Instead, execution time increased substantially after upgrading to Spark 3.5 because the tasks were restricted to using only one core. This happened because `spark.task.cpus` defaulted to 1 since I wasn't explicitly setting it.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.5.* (specifically versions 3.5.0 through 3.5.5) and also tested with 4.0.0-preview2. I am using the Python API via PySpark.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes or the executor memory setting, as those details are not included in the ticket information I provided. The minimal reproducible example I shared does not specify cluster configuration or memory settings.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to return two matching pairs and one unmatched left-side record with NULL values for the right side, as it did in Spark 2.4.6. Instead, Spark 3.0.0 produces non-deterministic results where one matched record is repeated without its right-side fields and the unmatched record is missing entirely.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0, where the issue appeared after upgrading from Spark 2.4.6. I am using the Scala API to write the streaming query in `spark-shell`.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I did not specify the cluster size or executor memory settings in my ticket. I am running the example in `spark-shell`, but I am not sure of the exact configuration used during testing. I don't have those details available.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to complete in about 15 minutes, as it did on Spark 2.4, but instead it took 5.7 hours on Spark 3.1 even after reducing the precision to 100. When left at the default precision of 10000, the stage exceeded 15 hours and hit our application time limits. This represents a drastic regression in performance for the `percentile_approx` operation during our upgrade.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am experiencing this issue while upgrading from Spark 2.4 to Spark 3.1. The problematic query is written in SQL, although the original report included Java code snippets to illustrate the logic.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have information about the number of nodes in my cluster or the specific executor memory settings in my ticket. I only mentioned the input data size of 37 billion rows and the shuffle read/write sizes, but not the cluster configuration.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to execute successfully and print the transformed DataFrame to the console. Instead, the command failed with a `SparkConnectGrpcException` on the client side, reporting an "Encountered end-of-stream mid-frame" error. The server logs also show a `StatusRuntimeException` with the same "Encountered end-of-stream mid-frame" message, indicating the gRPC connection was terminated prematurely.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Apache Spark version 4.0.0, as indicated by the Docker image `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu`. I am using the Python API (PySpark) via the `pyspark` shell to connect to the Spark Connect server. The code causing the issue is written in Python and executed within this shell.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running this in a single-node Docker environment where the client and server are inside the same container, so there is no cluster with multiple nodes. My ticket does not specify any executor memory settings, as the issue occurs during the schema transformation step before any distributed execution is configured or observed.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer the partition column type as TimestampType even when the folder name includes millisecond or microsecond fractions, such as `2020-04-03 04%3A48%3A28.467`. Instead, Spark incorrectly inferred the type as StringType, causing queries with timestamp values to return no results. This issue occurs specifically when the timestamp format includes fractional seconds, despite the source code suggesting it should handle milliseconds correctly.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0, and I primarily tested this issue using the Java API with a Java PoC code snippet. I also referenced Scala source code while investigating the problem.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I ran my tests locally using `master("local[*]")`, so I don't have a multi-node cluster or specific executor memory settings configured for this issue. The problem was observed in these local tests and is related to how Spark infers types from partition folder names.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected the execution time for `mapInPandas` to remain consistent with Spark versions 3.1 through 3.4, but instead, I observed a significant performance degradation of approximately 5-8x after upgrading to Spark 3.5. Specifically, SHAP computations inside the UDF ended up using only one core per task rather than utilizing all available cores as they did previously. This caused the substantial increase in elapsed time per iteration that I documented in my reproducible example.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark versions 3.5.0 through 3.5.5, as well as Spark 4.0.0-preview2, and the issue persists across all of them. The code is written in Python using the PySpark API. My minimal reproducible example relies on `mapInPandas` within a Python script.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes in my cluster or the specific executor memory setting, as those details are not mentioned in my ticket. My reproducible example focuses on the performance difference using a local setup with a coalesced DataFrame.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to deterministically output two matching pairs and one left-side item with NULL right-side fields, as it did in Spark 2.4.6. Instead, in Spark 3.0.0, the result is non-deterministic: the "has no join partner" entry is missing, and one of the already-joined entries is repeated with NULL right-side fields. This behavior only disappears if the non-joinable entry has a different ID.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0 with the Scala API. I also tested the same code on Spark 2.4.6, where it worked correctly.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am running this example in `spark-shell` on a single node, so I don't have a cluster with multiple nodes or specific executor memory settings configured for this test. The issue appears to be in the logic of the streaming join rather than the cluster configuration.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected my percentile_approx queries to have similar shuffle read performance when upgrading from Spark 2.4 to Spark 3.1, as the shuffle write sizes and input data volumes are comparable. Instead, the shuffle read stage slowed from 15 minutes on Spark 2.4 to 5.7 hours on Spark 3.1 even after I reduced percentile_approx's precision from the default 10000 to 100. At the default 10000 precision, the stage exceeded 15 hours and hit our application time limits.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using the Spark SQL API. The regression occurs when upgrading from Spark 2.4, where performance was acceptable, to Spark 3.1. I have Spark 3.3 available in my environment but have not yet tested the problematic job on it.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don’t have the exact cluster node count or executor memory settings documented in my current investigation of this regression. I can collect those details as part of my planned follow-up testing for this issue.

_checks failed: honest_about_unknown_

## `bytedance-seed/seed-2-1-turbo` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the final_agg.show() command to execute successfully without gRPC or network-related errors, printing the transformed DataFrame to the console. Instead, the command failed with a client-side SparkConnectGrpcException citing "Encountered end-of-stream mid-frame", and the Spark Connect server logged a corresponding NettyServerStream exception for the same error.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 4.0.0, and the Python (PySpark) API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I’m not sure about the cluster node count or exact executor memory settings, as those details aren’t specified in my reproduction setup. I run the Spark Connect server in a single Docker container for testing.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer TimestampType for partition columns whose folder name timestamps have millisecond or microsecond fractional seconds, just like it does for timestamps without fractional parts. Instead, Spark incorrectly infers those columns as StringType, so queries using timestamp values return no results because the values are compared as strings rather than timestamps.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using the Java API. I don't have the exact Spark version I'm running specified, though I referenced timestamp parsing changes that were introduced in Spark 3.0.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I ran all my testing locally with a local Spark session, not on a cluster, so I don't have cluster node counts or executor memory settings to share.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected `mapInPandas` performance for my computationally intensive SHAP value computation tasks to stay consistent with the speeds I saw in Spark 3.1 through 3.4 after upgrading to Spark 3.5.*. Instead, execution time increased by roughly 5-8x across different model sizes, and the issue persisted across all 3.5.x releases and even Spark 4.0.0-preview2. I later traced the slowdown to SHAP computations inside `mapInPandas` only using one core in these newer versions, rather than all available cores as they had previously.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using the Python (PySpark) API. The performance issue occurs across all Spark 3.5.x releases I tested, from 3.5.0 through 3.5.5, and also persists in Spark 4.0.0-preview2.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have the exact number of cluster nodes or my executor memory setting documented from my testing. The root cause I eventually identified was unrelated to those configurations, so I didn't track them closely during my investigation.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the streaming left join to return three rows: two matching left-right pairs, plus the left entry with no matching right side with null values for all right-side fields, as it worked in Spark 2.4.6. Instead, in Spark 3.0.0, the result is non-deterministic: the unmatched left entry is completely missing, and one of the already matched left-side entries is duplicated with null right-side fields.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using the Scala API, and I encountered this regression when upgrading to Spark 3.0.0 from Spark 2.4.6, where the same join worked as expected.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have those details, as I only tested this minimal example in spark-shell and didn't note specific cluster configuration or executor memory settings for this reproduction.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage for my queries using `percentile_approx` to perform similarly after upgrading from Spark 2.4 to Spark 3.1, as the shuffle write size and stage time were roughly equivalent between versions. Instead, the shuffle read stage slowed drastically: it took 15 minutes on Spark 2.4 but 5.7 hours on Spark 3.1 even after reducing `percentile_approx` precision from the default 10000 to 100, and exceeded 15 hours when left at the default precision.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm upgrading from Spark 2.4 to Spark 3.1, and I'm using the SQL API for the queries with `percentile_approx`. I also noted I have a Spark 3.3 environment available that I plan to test the job on later.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have those details available in what I've noted so far, I'm not sure of the exact cluster node count or executor memory setting for these runs. I can dig up that information as part of my follow-up profiling work on the slow stage.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to run successfully and print the transformed DataFrame to the console. Instead, the command failed with a gRPC `Encountered end-of-stream mid-frame` error, and the Spark Connect server terminated the connection.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 4.0.0, with the Python (PySpark) API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure about the exact number of cluster nodes or executor memory settings, as I only ran the Spark Connect server in a single local Docker container for reproduction. I didn't configure those specific parameters in my test setup.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer that partition columns with timestamp folder names containing millisecond or microsecond fractions (like `yyyy-MM-dd HH:mm:ss.S` or `yyyy-MM-dd HH:mm:ss.######`) are TimestampType. Instead, Spark infers these partition columns as StringType, which causes timestamp-based queries against these columns to return no results due to string comparison instead of time comparison.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0 or later, and my PoC code uses the Java API. I am not sure of the exact minor version I tested with.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have that information, since I only tested this locally in local[*] mode, not on a cluster. I did not note any executor memory settings from my local test.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected `mapInPandas` performance for my SHAP value computation to remain consistent with Spark 3.1 through 3.4, using all available cores as it did before. Instead, after upgrading to Spark 3.5, execution time increased by 5–8x because SHAP was only using one core instead of all available cores.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using the Python PySpark API, and I tested this issue across all Spark 3.5.x releases from 3.5.0 to 3.5.5, as well as Spark 4.0.0-preview2. The performance degradation appeared starting in Spark 3.5.0.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have those specific cluster configuration details noted, since I was focused on the per-iteration performance comparison between Spark versions. I'm not sure of the exact node count or executor memory settings from my tests.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the LEFT JOIN to return two matching left-right pairs plus the left entry with no join partner, with nulls for the right-side fields, as it did in Spark 2.4.6. Instead, in Spark 3.0.0 the result is non-deterministic: the unmatched left entry is missing entirely, and one of the successfully joined left-side rows appears a second time with nulls for the right-side fields.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using Spark 3.0.0 with the Scala API, running the example in spark-shell.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have those details, as I only ran this minimal example locally in spark-shell to reproduce the issue.

_checks failed: none_

## `google/gemini-3.5-flash-lite` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read performance when using `percentile_approx` to be similar between Spark 2.4 and Spark 3.1. Instead, I observed a massive regression where the shuffle read time went from 15 minutes on Spark 2.4 to 5.7 hours on Spark 3.1, even after reducing the precision from 10000 to 100.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am upgrading from Spark 2.4 to Spark 3.1, and using Java along with SQL queries.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes or the executor memory setting, as those details are not in my ticket.

_checks failed: none_

## `google/gemini-3.5-flash-lite` · SPARK-52965

**Q1.** What did you expect to happen, and what happened instead?

> I expected the `final_agg.show()` command to execute successfully without any gRPC or network-related errors, and print the transformed DataFrame to the console. Instead, it failed with a `SparkConnectGrpcException` showing a status of `INTERNAL` and details stating "Encountered end-of-stream mid-frame".

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Apache Spark version 4.0.0 and the Python language API (PySpark).

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the cluster node count and executor memory settings, as I am reproducing this locally using a minimal Docker environment with the `apache/spark:4.0.0-scala2.13-java17-python3-r-ubuntu` image.

_checks failed: none_

## `google/gemini-3.5-flash-lite` · SPARK-41242

**Q1.** What did you expect to happen, and what happened instead?

> I expected Spark to correctly infer the partition column type as TimestampType when the folder name contains millisecond or microsecond fractions, but instead it incorrectly infers it as StringType.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Java, but I am not sure of the exact Spark version.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know the number of nodes or the executor memory setting, as I ran my tests locally using `master("local[*]")`.

_checks failed: none_

## `google/gemini-3.5-flash-lite` · SPARK-51533

**Q1.** What did you expect to happen, and what happened instead?

> I expected the performance of `mapInPandas` when computing SHAP values in parallel to remain consistent with previous Spark versions, but instead, the execution time increased substantially by approximately 5-8x after upgrading to Spark 3.5.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.5.* and the Python API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes or the executor memory setting, as those details are not in my ticket.

_checks failed: none_

## `google/gemini-3.5-flash-lite` · SPARK-32148

**Q1.** What did you expect to happen, and what happened instead?

> I expected the output to contain two matching pairs and one item on the left side without a matching right side (output with the right side fields as `NULL`). However, in Spark 3.0.0, the result is non-deterministic and incorrectly repeats a previously joined left-side entry without its right-side fields while omitting the unjoined entry entirely.

_checks failed: none_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.0.0 and the Scala API.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes or the executor memory setting, as I ran this minimal example locally in `spark-shell`.

_checks failed: none_
