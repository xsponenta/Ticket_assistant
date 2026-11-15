# Simulator transcripts (model bake-off)

## `elorian/glimpse@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to complete in roughly 15 minutes, matching the performance I saw on Spark 2.4. Instead, on Spark 3.1, the shuffle read took 5.7 hours even after reducing the precision to 100, and it exceeded 15 hours when left at the default precision of 10000.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am using Spark 3.1, having upgraded from Spark 2.4. The query is written in SQL, though I provided the snippet in a Java-like format.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I am not sure about the exact number of nodes or the specific executor memory settings. My ticket only details the task counts and shuffle sizes for the Spark 2.4 and 3.1 runs.

_checks failed: none_

## `qwen/qwen3.5-27b@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage to complete in about 15 minutes, as it did on Spark 2.4, but instead it took 5.7 hours on Spark 3.1 even after reducing the precision to 100. When left at the default precision of 10000, the stage exceeded 15 hours and hit our application time limits. This represents a drastic regression in performance for the `percentile_approx` operation during our upgrade.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I am experiencing this issue while upgrading from Spark 2.4 to Spark 3.1. The problematic query is written in SQL, although the original report included Java code snippets to illustrate the logic.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have information about the number of nodes in my cluster or the specific executor memory settings in my ticket. I only mentioned the input data size of 37 billion rows and the shuffle read/write sizes, but not the cluster configuration.

_checks failed: admits_unknown_

## `bytedance-seed/seed-2-1-turbo@reasoning-min` · SPARK-46706

**Q1.** What did you expect to happen, and what happened instead?

> I expected the shuffle read stage for my queries using `percentile_approx` to perform similarly after upgrading from Spark 2.4 to Spark 3.1, as the shuffle write size and stage time were roughly equivalent between versions. Instead, the shuffle read stage slowed drastically: it took 15 minutes on Spark 2.4 but 5.7 hours on Spark 3.1 even after reducing `percentile_approx` precision from the default 10000 to 100, and exceeded 15 hours when left at the default precision.

_checks failed: no_volunteered_version_

**Q2.** Which Spark version and which language API (Scala, Python, Java, SQL or R) are you using?

> I'm upgrading from Spark 2.4 to Spark 3.1, and I'm using the SQL API for the queries with `percentile_approx`. I also noted I have a Spark 3.3 environment available that I plan to test the job on later.

_checks failed: none_

**Q3.** How many nodes does your cluster have, and what exactly is your executor memory setting?

> I don't have those details available in what I've noted so far, I'm not sure of the exact cluster node count or executor memory setting for these runs. I can dig up that information as part of my follow-up profiling work on the slow stage.

_checks failed: none_
