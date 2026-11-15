# C5 question sample (chained, dev; 20 items, seed 42)

## SPARK-42088|original · bug

> Summary: Running python3 setup.py sdist on windows reports a permission error Description: My system version is windows 10, and I can run setup.py with administrator permissions, so there will be no error. However, it may be troublesome for us to upgrade permissions with Windows Server, so we need to modify the code of setup.py to ensure no error. To avoid the hassle of compiling for the user, I suggest modifying the following code to enable the out-of-the-box effect ```python def _supports_syml…

Gold missing: ['regression_since'] · unknown: []

- [regression_since] Which Spark version are you building (e.g. 3.5.1 or 4.0.0), and did `python3 setup.py sdist` work without admin rights in an earlier version, making this a regression?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-31530|minus_expected_behavior · bug

> Summary: Spark submit fails if we provide extraJavaOption which contains Xmx as substring Description: Spark submit doesn't allow Xmx anywhere in the spark.driver.extraJavaOptions For eg: ```java bin\spark-submit --class org.apache.spark.examples.SparkPi --master local[*] --conf "spark.driver.extraJavaOptions=-DmyKey=MyValueContainsXmx" examples\jars\spark-examples_2.11-2.4.4.jar Error: Not allowed to specify max heap(Xmx) memory settings through java options (was -DmyKey=MyValueContainsXmx). Us…

Gold missing: ['expected_behavior', 'regression_since', 'workaround'] · unknown: []

- [regression_since] Do you know the last Spark version where this worked (i.e., is this a regression), and if so which version was it?
- [workaround] Is there any known workaround you've used to avoid this error, such as changing how the option is passed or renaming the value?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-31430|minus_steps_to_reproduce_environment · bug

> Summary: Bug in the approximate quantile computation. Description: I am seeing a bug where passing lower relative error to the `approxQuantile` function is leading to incorrect result in the presence of partitions. Setting a relative error 1e-6 causes it to compute equal values for 0.9 and 1.0 quantiles. Coalescing it back to 1 partition gives correct results.…

Gold missing: ['environment', 'steps_to_reproduce'] · unknown: []

- [steps_to_reproduce] Could you share a minimal, runnable snippet (e.g. in PySpark or spark-shell) that reproduces the equal 0.9/1.0 quantile results with relative error 1e-6 on a partitioned DataFrame?
- [expected_behavior] What did you expect approxQuantile to return for the 0.9 and 1.0 quantiles in that case, and why (e.g. documentation or a previous Spark version)?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-52965|minus_environment · bug

> Summary: [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation Description: The Spark Connect server terminates the connection, leading to an `Encountered end-of-stream mid-frame` error. The issue is reproducible in a minimal Docker environment and persists even after eliminating network factors and increasing gRPC message size limits, indicating a potential core issue rather than a configuration problem. Steps to Reproduce This issue can be fully repro…

Gold missing: ['environment', 'expected_behavior', 'regression_since', 'workaround'] · unknown: []

- [expected_behavior] What did you expect final_agg.show() to return for this complex schema transformation, and why (e.g., behavior in Spark 3.5, documentation, or another engine)?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-33338|minus_actual_behavior · bug

> Summary: GROUP BY using literal map should not fail Description: *SQL* ``` CREATE TABLE t USING ORC AS SELECT map('k1', 'v1') m, 'k1' k SELECT map('k1', 'v1')[k] FROM t GROUP BY 1 SELECT map('k1', 'v1')[k] FROM t GROUP BY map('k1', 'v1')[k] SELECT map('k1', 'v1')[k] a FROM t GROUP BY a ``` *ERROR* ``` ``` This is a regression from Apache Spark 1.6.x. ``` scala> sc.version res1: String = 1.6.3 scala> sqlContext.sql("SELECT map('k1', 'v1')[k] FROM t GROUP BY map('k1', 'v1')[k]").show +---+ |_c0| +…

Gold missing: ['actual_behavior', 'workaround'] · unknown: []

- [workaround] Do you know of any workaround that avoids the failure, such as rewriting the query to use a column alias or a subquery instead of the literal map lookup in GROUP BY?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-41813|minus_proposed_behavior_acceptance_criteria · feature

> Summary: UnsafeHashedRelation read method needs to confirm the correctness of the data Description: Recently, we have encountered the thread-safe issue of[ [SPARK-31511]|https://issues.apache.org/jira/browse/SPARK-31511] in production. The version 2.4.3 we use has not been fixed yet, which leads to data errors. I think this is a serious error, the data broadcast by the Driver is inconsistent with the data of the Executor.…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'proposed_behavior'] · unknown: []

- [acceptance_criteria] What checkable conditions would confirm this fix is working — for example, a regression test reproducing the SPARK-31511 mismatch that now passes, or a specific query returning identical results across Driver and Executor?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-41813|minus_motivation · feature

> Summary: UnsafeHashedRelation read method needs to confirm the correctness of the data Description: The Executor side should confirm the correctness of the data when reading the data. The numKeys and numValues read from the file header should be consistent with the real data read. This judgment should be added to prevent wrong data from being calculated.…

Gold missing: ['alternatives_considered', 'motivation'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm the fix works — e.g. a corrupted UnsafeHashedRelation file with mismatched numKeys/numValues causes a clear exception instead of wrong results, and valid files still read correctly?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-37085|original · feature

> Summary: Missing overloads in functions accepting both varargs and single arg collection Description: There are a few functions that have vararg signature, but can accept a single item (`list` or `tuple`): - `def create_map(*cols: "ColumnOrName") -> Column: ...` - `def struct(*cols: "ColumnOrName") -> Column: ...` - `def array(*cols: "ColumnOrName") -> Column: ...` - `def map_concat(*cols: "ColumnOrName") -> Column: ...` We should add overloads of the following form ```python @overload def _(col…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'design_reference'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm this is done — e.g. mypy/pyright accepts both `create_map([col1, col2])` and `create_map(col1, col2)` without errors, and existing tests still pass?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-35258|original · feature

> Summary: Enhance ESS ExternalBlockHandler with additional block rate-based metrics and histograms Description: Today the `ExternalBlockHandler` component of ESS exposes some useful metrics, but is lacking around metrics for the rate of block transfers. We have `blockTransferRateBytes` to tell us the rate of _bytes_, but no metric to tell us the rate of _blocks_, which is especially relevant when running the ESS on HDDs that are sensitive to random reads. Many small block transfers can have a neg…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'design_reference'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm this is done — e.g. which new metric names appear in ExternalBlockHandler's metric source, and which Timer histogram fields (count, min, max, mean, percentiles) YarnShuffleServiceMetrics should expose?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-51704|unknown_acceptance_criteria · feature

> Summary: Eliminate unnecessary collect operation Description: Change the `TreeNode` operation from ```collect``` to ```collectFirst`,`` when it is supposed to find the first qualified node rather than apply function through out all the node and it's child, this function should not take any effect or make any change to the node which applied for.…

> **assistant:** Could you add the acceptance criteria? Checkable conditions that tell when the request is fulfilled.

> **user:** Sorry, I can't provide that.

Gold missing: ['alternatives_considered', 'design_reference'] · unknown: ['acceptance_criteria']

- [alternatives_considered] Did you consider any alternative approaches (e.g., early-exit traversal helpers or existing TreeNode APIs) and why do they fall short compared to switching to collectFirst?
- [design_reference] Is there a design doc, mailing-list thread, or prior Jira issue you can reference for this change?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-33928|minus_goal · task

> Summary: Flaky o.a.s.ExecutorAllocationManagerSuite - "SPARK-23365 Don't update target num executors when killing idle executors" Description: [info] org.scalatest.exceptions.TestFailedException: [info] at org.scalatest.Assertions.newAssertionFailedException(Assertions.scala:530) [info] at org.scalatest.Assertions.newAssertionFailedException$(Assertions.scala:529) [info] at org.scalatest.FunSuite.newAssertionFailedException(FunSuite.scala:1560) [info] at org.scalatest.Assertions$AssertionsHelper…

Gold missing: ['definition_of_done', 'goal', 'scope'] · unknown: []

- [scope] What exactly should this ticket cover—e.g., only stabilizing the "SPARK-23365 Don't update target num executors when killing idle executors" test in ExecutorAllocationManagerSuite—and what is explicitly out of scope (other flaky tests, production code changes)?
- [definition_of_done] What are the verifiable completion criteria, e.g., the test passes reliably across N repeated runs on the supported JDK/Scala builds and the fix is merged with CI green?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-49897|original · task

> Summary: Bump Hadoop libraries to to 3.3.9 Description: CVE-2024-47554 is fixed in that version of the library. Could please you confirm whether Spark is affected by this vulnerability and if so, are there any plans to update the dependency? ``` │ commons-io:commons-io (hadoop-client-runtime-3.3.4.jar) │ CVE-2024-47554 │ HIGH │ │ 2.8.0 │ 2.14.0 │ apache-commons-io: Possible denial of service attack on │ │ │ │ │ │ │ │ untrusted input to XmlStreamReader │ │ │ │ │ │ │ │ https://avd.aquasec.com/nvd/…

Gold missing: ['definition_of_done'] · unknown: []

- [definition_of_done] What verifiable completion criteria should this ticket have—e.g., which build/test matrix (JDK versions, profiles) must pass and which dependency manifests (dev/deps) need updating to show commons-io ≥ 2.14.0?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-40021|minus_goal · task

> Summary: `Cancel workflow` can not cancel some jobs Description: I have been observing this behavior for a long time: - Run / Build modules: pyspark-sql, pyspark-mllib, pyspark-resource - Run / Build modules: pyspark-core, pyspark-streaming, pyspark-ml - Run / Build modules: pyspark-pandas - Run / Build modules: pyspark-pandas-slow - Run / Linters, licenses, dependencies and documentation generation…

Gold missing: ['definition_of_done', 'goal', 'related_issues'] · unknown: []

- [definition_of_done] What verifiable criteria should mark this task complete—e.g., which CI jobs must be confirmed cancellable and on which JDK versions must the build and tests pass?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-32072|answered_goal · task

> Summary: Unaligned benchmark results Description: ``` OpenJDK 64-Bit Server VM 1.8.0_232-8u232-b09-0ubuntu1~18.04.1-b09 on Linux 4.15.0-1044-aws Intel(R) Xeon(R) CPU E5-2670 v2 @ 2.50GHz make_timestamp(): Best Time(ms) Avg Time(ms) Stdev(ms) Rate(M/s) Per Row(ns) Relative ------------------------------------------------------------------------------------------------------------------------ prepare make_timestamp() 3636 3673 38 0.3 3635.7 1.0X make_timestamp(2019, 1, 2, 3, 4, 50.123456) 94 99 4 …

> **assistant:** Could you add the goal? Why the work is needed (risk, maintenance cost, broken docs, CVE, flaky test).

> **user:** If the length of benchmark names is greater than 40, benchmark results are not aligned to column names. For example:

Gold missing: ['related_issues'] · unknown: []

- [definition_of_done] What are the verifiable completion criteria for this fix, e.g. benchmark output with names over 40 characters aligns with column headers and existing tests pass?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-32072|minus_goal · task

> Summary: Unaligned benchmark results Description: ``` OpenJDK 64-Bit Server VM 1.8.0_232-8u232-b09-0ubuntu1~18.04.1-b09 on Linux 4.15.0-1044-aws Intel(R) Xeon(R) CPU E5-2670 v2 @ 2.50GHz make_timestamp(): Best Time(ms) Avg Time(ms) Stdev(ms) Rate(M/s) Per Row(ns) Relative ------------------------------------------------------------------------------------------------------------------------ prepare make_timestamp() 3636 3673 38 0.3 3635.7 1.0X make_timestamp(2019, 1, 2, 3, 4, 50.123456) 94 99 4 …

Gold missing: ['goal', 'related_issues'] · unknown: []

- [goal] What is the goal of this ticket—why are these unaligned benchmark results a problem (e.g., misleading docs, regression risk, maintenance cost)?
- [scope] What is in scope and out of scope for fixing this (e.g., only the make_timestamp benchmark file vs. all datetime benchmarks)?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-15504|minus_problem_hypothesis · idea

> Summary: Could MatrixFactorizationModel support recommend for some users only ? Description: So I think if there could have an API such as -> recommendProductsForUsers(users: RDD[Int], num: Int): RDD[(Int, Array[Rating])], so it best match my case.…

Gold missing: ['open_questions', 'problem_hypothesis'] · unknown: []

- [target_users] Who would benefit from a `recommendProductsForUsers(users: RDD[Int], num: Int)` API—for example, which user group, workload type, and scale (number of users/items) do you have in mind?
- [expected_impact] What improvement would this API bring and how could it be measured—e.g., reduced runtime, avoided full-model scoring, lower memory use, or better fit for subset-based recommendation jobs?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-23824|minus_problem_hypothesis · idea

> Summary: Make inpurityStats publicly accessible in ml.tree.Node Description: This is minor, but it is also a very easy fix. I'm pretty sure that the fix for this is as easy as removing the private[ml] qualifier from occurrences of private[ml] def impurityStats: ImpurityCalculator and override private[ml] val impurityStats: ImpurityCalculator…

Gold missing: ['open_questions', 'problem_hypothesis'] · unknown: []

- [target_users] Which user group would benefit from making `impurityStats` public in `ml.tree.Node` (e.g., Spark MLlib users writing custom tree-based models, PySpark users, library developers extending spark.ml)?
- [expected_impact] What would improve for those users once `impurityStats` is accessible, and how could that improvement be measured (e.g., ability to build custom impurity-based feature importance without forking Spark, fewer workarounds)?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-23824|minus_expected_impact · idea

> Summary: Make inpurityStats publicly accessible in ml.tree.Node Description: This is minor, but it is also a very easy fix. I'm pretty sure that the fix for this is as easy as removing the private[ml] qualifier from occurrences of private[ml] def impurityStats: ImpurityCalculator and override private[ml] val impurityStats: ImpurityCalculator As a workaround, I've put my class that needs access into a org.apache.spark.ml.tree package in my own repository, but I would really like to not have to do…

Gold missing: ['expected_impact', 'open_questions'] · unknown: []

- [open_questions] Before this becomes a feature request, are there concerns about widening the public API surface of Node—e.g., binary compatibility, future maintenance of ImpurityCalculator, or whether this should be exposed via an alternative public accessor instead?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-36680|unknown_problem_hypothesis · idea

> Summary: Supports Dynamic Table Options for Spark SQL Description: ```java DataFrameReader/AstBuilder -> UnresolvedRelation$options -> DataSourceV2Relation$options -> SupportsRead$newScanBuilder(options) ``` - JDBCTable set _fetchsize_ according to the actual situation of the table - IcebergTable support time travel ```java spark.read .option("snapshot-id", 10963874102873L) .format("iceberg") .load("path/to/table") ``` These parameters setting is very common and ad-hoc, setting them flexibly wou…

> **assistant:** Could you add the problem hypothesis? The problem the user believes exists and why — stated as a hypothesis, not a solution.

> **user:** I don't know.

Gold missing: ['open_questions'] · unknown: ['problem_hypothesis']

- [open_questions] Since I can't ask about the problem hypothesis, should this dynamic table options support live in Spark core or as a separate spark-packages project/advisor?

Clarity (1 = unclear … 3 = clear): ___

## SPARK-39474|unknown_problem_hypothesis · idea

> Summary: Streamline the options for the `.write` method of a Spark DataFrame Description: Hi Team! Let me show you the differences: *Current:* First, run: ```java import pandas as pd df = spark.createDataFrame( pd.DataFrame( {'a': [1,2,3,4], 'b': ['a','b','c','d']} ) ) df.write.mode('overwrite').format('delta').save('./folder') ``` Then, once it's saved, run: ```java CREATE TABLE df USING DELTA LOCATION './folder' ``` Then, once the table is loaded, run: ```java OPTIMIZE df --or OPTIMIZE df ZORD…

> **assistant:** Could you add the problem hypothesis? The problem the user believes exists and why — stated as a hypothesis, not a solution.

> **user:** No idea, I don't have that information.

Gold missing: ['open_questions', 'target_users'] · unknown: ['problem_hypothesis']

- [open_questions] Since Delta's OPTIMIZE/ZORDER BY are Delta-specific and Spark's DataFrameWriter is format-agnostic, what uncertainties should be settled first—e.g., should this live in Spark core or as a separate spark-packages/Delta connector feature?

Clarity (1 = unclear … 3 = clear): ___
