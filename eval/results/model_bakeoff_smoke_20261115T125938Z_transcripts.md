# Simulator transcripts (model bake-off)

## `qwen/qwen3.5-9b` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to perform similarly to Spark 2.4, taking around 15 minutes. Instead, it took 5.7 hours on Spark 3.1 (even after reducing precision from the default 10,000 to 100), and exceeded 15 hours at the original precision.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.1 (and also tested on Spark 2.4 for comparison), and the queries are written in SQL via a Java application.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have information about the number of nodes in my cluster or the specific executor memory settings in the ticket.

_checks failed: admits_unknown_

## `deepseek/deepseek-v4.1-flash-1017` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to perform roughly like it did on Spark 2.4, around 15 minutes. Instead, on Spark 3.1 the same stage took 5.7 hours even after I reduced the `percentile_approx` precision from the default 10000 to 100, and at the default precision it exceeded 15 hours and hit our application time limits. The shuffle write stayed roughly the same in time and size.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> The regression I observed was on Spark 3.1, during an upgrade from Spark 2.4. The query is SQL, though I showed it in a code block.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure — my ticket doesn't include the cluster node count or executor memory settings. I only reported stage timings, task counts, and shuffle sizes.

_checks failed: none_

## `deepseek/deepseek-v4.1-flash-1017@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage with percentile_approx to perform similarly to Spark 2.4, but on Spark 3.1 it went from 15 minutes to 5.7 hours (and exceeded 15 hours at the default precision of 10000). I don't have a precise expectation beyond that it shouldn't regress this badly.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm upgrading from Spark 2.4 to Spark 3.1, and I also plan to test on Spark 3.3. The queries are SQL, though I described the snippet in Java-like form.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't know — my ticket doesn't include the cluster node count or executor memory settings.

_checks failed: none_

## `elorian/glimpse` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the Spark 3.1 job to have shuffle read performance comparable to Spark 2.4, especially since the shuffle write stage was roughly the same time and size. Instead, the shuffle read became drastically slower: 15 minutes on Spark 2.4 versus 5.7 hours on Spark 3.1 after reducing the precision to 100. With the default precision of 10000, the stage exceeded 15 hours.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I’m comparing Spark 2.4 to Spark 3.1, with the regression observed on Spark 3.1. The queries are written in SQL.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I'm not sure about the exact cluster node count or executor memory settings — those details aren't in my notes.

_checks failed: none_

## `qwen/qwen3.5-27b` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to take about 15 minutes, consistent with our experience on Spark 2.4. Instead, on Spark 3.1, that stage took 5.7 hours even after reducing precision, and exceeded 15 hours when left at the default. This performance regression was severe enough to hit our application time limits.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am currently upgrading from Spark 2.4 to Spark 3.1, where I am observing the performance regression. I am using SQL for the queries, as shown in the snippets provided in my ticket. I am not sure about the specific driver language API, though one code block was labeled Java.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I do not have the cluster node count or executor memory settings documented in the ticket details I shared. I focused on the task counts, shuffle statistics, and performance timing differences instead. So I am not sure about those specific configuration values.

_checks failed: none_

## `bytedance-seed/seed-2-1-turbo` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected my percentile_approx queries to have similar shuffle read performance when upgrading from Spark 2.4 to Spark 3.1, as the shuffle write sizes and input data volumes are comparable. Instead, the shuffle read stage slowed from 15 minutes on Spark 2.4 to 5.7 hours on Spark 3.1 even after I reduced percentile_approx's precision from the default 10000 to 100. At the default 10000 precision, the stage exceeded 15 hours and hit our application time limits.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm using the Spark SQL API. The regression occurs when upgrading from Spark 2.4, where performance was acceptable, to Spark 3.1. I have Spark 3.3 available in my environment but have not yet tested the problematic job on it.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don’t have the exact cluster node count or executor memory settings documented in my current investigation of this regression. I can collect those details as part of my planned follow-up testing for this issue.

_checks failed: admits_unknown_

## `google/gemini-3.5-flash-lite` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read performance when using `percentile_approx` to be similar between Spark 2.4 and Spark 3.1. Instead, I observed a massive regression where the shuffle read time went from 15 minutes on Spark 2.4 to 5.7 hours on Spark 3.1, even after reducing the precision from 10000 to 100.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am upgrading from Spark 2.4 to Spark 3.1, and using Java along with SQL queries.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the number of nodes or the executor memory setting, as those details are not in my ticket.

_checks failed: none_
