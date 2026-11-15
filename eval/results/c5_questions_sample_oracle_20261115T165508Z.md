# C5 question sample (oracle, dev; 20 items, seed 42)

## SPARK-42088|minus_expected_behavior · bug

> Summary: Running python3 setup.py sdist on windows reports a permission error Description: My system version is windows 10, and I can run setup.py with administrator permissions, so there will be no error. However, it may be troublesome for us to upgrade permissions with Windows Server, so we need to modify the code of setup.py to ensure no error. ```python def _supports_symlinks(): """Check if the system supports symlinks (e.g. *nix) or not.""" return getattr(os, "symlink", None) is not None an…

Gold missing: ['expected_behavior', 'regression_since'] · unknown: []

- [expected_behavior] What did you expect `python3 setup.py sdist` to do on Windows without administrator permissions (e.g., complete the sdist build successfully), and why should that be the expected behavior?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-31530|minus_expected_behavior · bug

> Summary: Spark submit fails if we provide extraJavaOption which contains Xmx as substring Description: Spark submit doesn't allow Xmx anywhere in the spark.driver.extraJavaOptions For eg: ```java bin\spark-submit --class org.apache.spark.examples.SparkPi --master local[*] --conf "spark.driver.extraJavaOptions=-DmyKey=MyValueContainsXmx" examples\jars\spark-examples_2.11-2.4.4.jar Error: Not allowed to specify max heap(Xmx) memory settings through java options (was -DmyKey=MyValueContainsXmx). Us…

Gold missing: ['expected_behavior', 'regression_since', 'workaround'] · unknown: []

- [expected_behavior] What did you expect spark-submit to do with `-DmyKey=MyValueContainsXmx` in spark.driver.extraJavaOptions, and why (e.g., the option is a system property, not a heap setting)?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-31430|minus_environment · bug

> Summary: Bug in the approximate quantile computation. Description: I am seeing a bug where passing lower relative error to the `approxQuantile` function is leading to incorrect result in the presence of partitions. Setting a relative error 1e-6 causes it to compute equal values for 0.9 and 1.0 quantiles. Coalescing it back to 1 partition gives correct results. `>>> df = df.repartition(200, 'Store').localCheckpoint()` `>>> df.approxQuantile('seconds', [0.8, 0.9, 1.0], 0.0001)` `[1422576000.0, 143…

Gold missing: ['environment'] · unknown: []

- [environment] Which Spark version(s) are affected (Jira Affects Version), and what API language and deployment are you using (e.g., PySpark on YARN)?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-52965|minus_steps_to_reproduce_actual_behavior · bug

> Summary: [SPARK-CONNECT] [SPARK-4.0] Encountered end-of-stream mid-frame on Complex Schema Transformation Description: A gRPC connection failure occurs when executing a PySpark DataFrame action that involves a complex, dynamically generated schema transformation. The Spark Connect server terminates the connection, leading to an `Encountered end-of-stream mid-frame` error. The issue is reproducible in a minimal Docker environment and persists even after eliminating network factors and increasing …

Gold missing: ['actual_behavior', 'expected_behavior', 'regression_since', 'steps_to_reproduce', 'workaround'] · unknown: []

- [steps_to_reproduce] You mentioned a minimal Docker environment reproduces it — can you share the minimal PySpark code (the DataFrame transformation and action) that triggers the end-of-stream error?
- [actual_behavior] What exact error output and stack trace lines does the Spark Connect server log show when the connection terminates mid-frame?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-33338|minus_actual_behavior · bug

> Summary: GROUP BY using literal map should not fail Description: *SQL* ``` CREATE TABLE t USING ORC AS SELECT map('k1', 'v1') m, 'k1' k SELECT map('k1', 'v1')[k] FROM t GROUP BY 1 SELECT map('k1', 'v1')[k] FROM t GROUP BY map('k1', 'v1')[k] SELECT map('k1', 'v1')[k] a FROM t GROUP BY a ``` *ERROR* ``` ``` This is a regression from Apache Spark 1.6.x. ``` scala> sc.version res1: String = 1.6.3 scala> sqlContext.sql("SELECT map('k1', 'v1')[k] FROM t GROUP BY map('k1', 'v1')[k]").show +---+ |_c0| +…

Gold missing: ['actual_behavior', 'workaround'] · unknown: []

- [actual_behavior] The ERROR block in your description is empty — what exactly happens when you run these queries (e.g. the exception class and key stack trace lines, or wrong output)?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-41813|minus_proposed_behavior_acceptance_criteria · feature

> Summary: UnsafeHashedRelation read method needs to confirm the correctness of the data Description: Recently, we have encountered the thread-safe issue of[ [SPARK-31511]|https://issues.apache.org/jira/browse/SPARK-31511] in production. The version 2.4.3 we use has not been fixed yet, which leads to data errors. I think this is a serious error, the data broadcast by the Driver is inconsistent with the data of the Executor.…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'proposed_behavior'] · unknown: []

- [proposed_behavior] What should Spark do at the API/config/observable-behavior level to confirm the correctness of UnsafeHashedRelation read data (e.g., a new config, validation check, or fallback behavior) rather than describing the internal fix?
- [acceptance_criteria] What checkable conditions would show this request is fulfilled (e.g., specific tests, no data mismatch between Driver-broadcast and Executor data, behavior under concurrent reads, documentation/config entry)?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-41813|minus_motivation · feature

> Summary: UnsafeHashedRelation read method needs to confirm the correctness of the data Description: The Executor side should confirm the correctness of the data when reading the data. The numKeys and numValues read from the file header should be consistent with the real data read. This judgment should be added to prevent wrong data from being calculated.…

Gold missing: ['alternatives_considered', 'motivation'] · unknown: []

- [motivation] What user problem or use case motivates adding this validation in UnsafeHashedRelation's read method, and why aren't existing checks or configs sufficient?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-37085|original · feature

> Summary: Missing overloads in functions accepting both varargs and single arg collection Description: There are a few functions that have vararg signature, but can accept a single item (`list` or `tuple`): - `def create_map(*cols: "ColumnOrName") -> Column: ...` - `def struct(*cols: "ColumnOrName") -> Column: ...` - `def array(*cols: "ColumnOrName") -> Column: ...` - `def map_concat(*cols: "ColumnOrName") -> Column: ...` We should add overloads of the following form ```python @overload def _(col…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'design_reference'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm this is done — e.g. mypy/pyright accepts both `array(col)` and `array(col1, col2)` without errors, and existing tests still pass?
- [design_reference] Is there a design doc, Jira/PR discussion, or dev@spark.apache.org thread for these overloads that you can link as a reference?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-35258|original · feature

> Summary: Enhance ESS ExternalBlockHandler with additional block rate-based metrics and histograms Description: Today the `ExternalBlockHandler` component of ESS exposes some useful metrics, but is lacking around metrics for the rate of block transfers. We have `blockTransferRateBytes` to tell us the rate of _bytes_, but no metric to tell us the rate of _blocks_, which is especially relevant when running the ESS on HDDs that are sensitive to random reads. Many small block transfers can have a neg…

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'design_reference'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm this is done — e.g. the new block-rate metric name and that it appears in the ESS metrics output, and which Timer histogram fields (count, min, max, mean, percentiles) YarnShuffleServiceMetrics should expose?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-34937|answered_motivation · feature

> Summary: Remove unnecessary sort in FileFormatWriter when only have one partition Description: related file: ```java org.apache.spark.sql.execution.datasources.FileFormatWriter ``` related code: ```java // We should first sort by partition columns, then bucket id, and finally sorting columns. val requiredOrdering = partitionColumns ++ bucketIdExpression ++ sortColumns // the sort order doesn't matter val actualOrdering = plan.outputOrdering.map(_.child) val orderingMatched = if (requiredOrdering…

> **assistant:** Could you add the motivation? The user problem or use case, and why existing APIs/configs are not enough.

> **user:** sort is a very resource-intensive operation, spark may add SortExec when writing partition file for writing sequentially, but i think sorting is unnecessary when only have one partition.

Gold missing: ['acceptance_criteria', 'alternatives_considered', 'design_reference'] · unknown: []

- [acceptance_criteria] What checkable conditions should confirm this change works — e.g. a query plan test showing no SortExec for a single-partition write, and existing FileFormatWriter tests still passing?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-46639|answered_goal · task

> Summary: Add WindowExec SQLMetrics Description: ```java numOfOutputRows: Number of total output rows. numOfPartitions: Number of processed input partitions. numOfWindowPartitions: Number of generated window partitions. spilledRows: Number of total spilled rows. spillSizeOnDisk: Total spilled data size on disk. ``` *1-* WindowExec creates ExternalAppendOnlyUnsafeRowArray (internal ArrayBuffer) per task (a.k.a child RDD partition) *2-* When ExternalAppendOnlyUnsafeRowArray size exceeds spark.sql.w…

> **assistant:** Could you add the goal? Why the work is needed (risk, maintenance cost, broken docs, CVE, flaky test).

> **user:** Currently, WindowExec Physical Operator has only spillSize SQLMetric. This jira aims to add following SQLMetrics to provide more information from WindowExec usage during query execution: As an example

Gold missing: ['definition_of_done', 'related_issues'] · unknown: []

- [definition_of_done] What are the verifiable completion criteria for this change (e.g., build and tests pass on JDK 17/21, new SQLMetrics covered by tests, no new license warnings)?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-39684|original · task

> Summary: Docker IT build broken in master with Hadoop 2 Description: https://github.com/apache/spark/runs/7054055518?check_suite_focus=true ``` [info] DB2KrbIntegrationSuite: [info] org.apache.spark.sql.jdbc.DB2KrbIntegrationSuite *** ABORTED *** (3 minutes, 47 seconds) [info] The code passed to eventually never returned normally. Attempted 185 times over 3.0097517207166664 minutes. Last failure message: Login failure for db2/10.1.0.36@EXAMPLE.COM from keytab /home/runner/work/spark/spark/target…

Gold missing: ['definition_of_done', 'related_issues'] · unknown: []

- [definition_of_done] What verifiable completion criteria should the ticket use, e.g. the DB2KrbIntegrationSuite passes in the Docker IT build with Hadoop 2 and the full build/tests are green?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-32072|answered_goal · task

> Summary: Unaligned benchmark results Description: ``` OpenJDK 64-Bit Server VM 1.8.0_232-8u232-b09-0ubuntu1~18.04.1-b09 on Linux 4.15.0-1044-aws Intel(R) Xeon(R) CPU E5-2670 v2 @ 2.50GHz make_timestamp(): Best Time(ms) Avg Time(ms) Stdev(ms) Rate(M/s) Per Row(ns) Relative ------------------------------------------------------------------------------------------------------------------------ prepare make_timestamp() 3636 3673 38 0.3 3635.7 1.0X make_timestamp(2019, 1, 2, 3, 4, 50.123456) 94 99 4 …

> **assistant:** Could you add the goal? Why the work is needed (risk, maintenance cost, broken docs, CVE, flaky test).

> **user:** If the length of benchmark names is greater than 40, benchmark results are not aligned to column names. For example:

Gold missing: ['related_issues'] · unknown: []

- [related_issues] Do you have any related Jira keys or pull request numbers for this fix, such as the ticket where the misalignment was reported or a PR that addresses it?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-32072|minus_goal · task

> Summary: Unaligned benchmark results Description: ``` OpenJDK 64-Bit Server VM 1.8.0_232-8u232-b09-0ubuntu1~18.04.1-b09 on Linux 4.15.0-1044-aws Intel(R) Xeon(R) CPU E5-2670 v2 @ 2.50GHz make_timestamp(): Best Time(ms) Avg Time(ms) Stdev(ms) Rate(M/s) Per Row(ns) Relative ------------------------------------------------------------------------------------------------------------------------ prepare make_timestamp() 3636 3673 38 0.3 3635.7 1.0X make_timestamp(2019, 1, 2, 3, 4, 50.123456) 94 99 4 …

Gold missing: ['goal', 'related_issues'] · unknown: []

- [goal] Why is fixing the unaligned benchmark output needed (e.g., readability, maintenance cost, or misleading docs)?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-33928|original · task

> Summary: Flaky o.a.s.ExecutorAllocationManagerSuite - "SPARK-23365 Don't update target num executors when killing idle executors" Description: [info] - SPARK-23365 Don't update target num executors when killing idle executors *** FAILED *** (126 milliseconds) [info] 1 did not equal 2 (ExecutorAllocationManagerSuite.scala:1617) [info] org.scalatest.exceptions.TestFailedException: [info] at org.scalatest.Assertions.newAssertionFailedException(Assertions.scala:530) [info] at org.scalatest.Assertion…

Gold missing: ['definition_of_done', 'scope'] · unknown: []

- [scope] What should the fix cover—e.g., only stabilizing the test in ExecutorAllocationManagerSuite.scala (timing/awaitility changes) versus also changing ExecutorAllocationManager production logic—and what is explicitly out of scope?
- [definition_of_done] What are the verifiable completion criteria for this flaky-test task (e.g., the test passes reliably in repeated runs, full ExecutorAllocationManagerSuite passes, and CI is green)?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-30286|answered_problem_hypothesis · idea

> Summary: Some thoughts on new features for MLLIB Description: Some thoughts on new features for ML: 1, clustering: *mini-batch KMeans*: 2, classification & regression: 2.1 ExtraTrees (Extremely Randomized Trees): 2.2 Categorical Naive Bayes: 3, features: 3.1 *vector validator*: a new UnaryTransformer that check whether a vector column meets some requirements, like non-NaN, non-negative, positive, all values are binary/int, all vectors are dense/sparse, numFetures; 3.2 inverse transform for model…

> **assistant:** Could you add the problem hypothesis? The problem the user believes exists and why — stated as a hypothesis, not a solution.

> **user:** KMeans maybe one of the most widely used algs in MLLIB, mini-batch KMeans is much faster than KMeans with [compareable results](https://scikit-learn.org/stable/auto_examples/cluster/plot_mini_batch_km

Gold missing: ['expected_impact', 'open_questions', 'target_users'] · unknown: []

- [target_users] Which Spark users or workloads would benefit most from these MLlib additions (e.g., PySpark data scientists running clustering/classification pipelines, Scala MLlib users needing faster KMeans, or teams building production ML pipelines that need early validation)?
- [expected_impact] What concrete improvements do you expect from these features, and how could they be measured (e.g., faster training time for mini-batch KMeans, fewer NaN-related pipeline failures via the vector validator, or lower variance from ExtraTrees)?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-31276|original · idea

> Summary: Contrived working example that works with multiple URI file storages for Spark cluster mode Description: This Spark SQL Guide --> Data sources --> Generic Load/Save Functions <https://spark.apache.org/docs/latest/sql-data-sources-load-save-functions.html> described a very simple "local file system load of an example file". I am looking for an example that demonstrates a workflow that exercises different file systems. For example, 1. Driver loads an input file from local file system 1. A…

Gold missing: ['expected_impact'] · unknown: []

- [expected_impact] What would improve if this multi-URI example were added to the Spark docs, and how could that improvement be measured (e.g., fewer user errors or support questions about local vs HDFS paths in YARN client mode)?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-53903|minus_problem_hypothesis_target_users · idea

> Summary: Performance degradation for PySpark apis at scale as compared to Scala apis Description: and we are debating if it's worth changing existing workflows to scala just like that (existing DEs are more comfortable with PySpark, there is cost of migration as well that we will have to convince our management to approve) *ASK:* This Jira includes a sample notebook that reproduces what our usecases see. We are seeking community feedback on such a usecase and if there are ideas to improve this s…

Gold missing: ['expected_impact', 'problem_hypothesis', 'target_users'] · unknown: []

- [problem_hypothesis] What do you believe is the root cause of the PySpark-vs-Scala performance gap in your workloads (e.g., Python UDF serialization overhead, row-to-arrow conversion, shuffle behavior), stated as a hypothesis?
- [target_users] Which user group and workload scale would benefit from improvements here (e.g., DEs running PySpark batch jobs at what data volume, cluster size, or job count)?

Clarity (1 = unclear … 3 = clear): 2

## SPARK-11882|unknown_problem_hypothesis · idea

> Summary: Allow for running Spark applications against a custom coarse grained scheduler Description: Such a custom scheduler would just extend `CoarseGrainedSchedulerBackend`. The custom scheduler would be created by a provided factory. Factories would be defined in the configuration like `spark.scheduler.factory.<name>=<factory-class>`, where `name` is the scheduler name. `SparkContext`, once it learns that master address is not for standalone, Yarn, Mesos, local or any other predefined schedul…

> **assistant:** Could you add the problem hypothesis? The problem the user believes exists and why — stated as a hypothesis, not a solution.

> **user:** No idea, I don't have that information.

Gold missing: ['expected_impact', 'open_questions', 'target_users'] · unknown: ['problem_hypothesis']

- [target_users] Who would benefit from plugging in a custom coarse-grained scheduler via `spark.scheduler.factory.<name>` — for example, platform teams running Spark on a proprietary cluster manager, or users with in-house resource managers?
- [expected_impact] What would improve for those users once this works, and how could it be measured — e.g. Spark jobs running on a new cluster manager without forking Spark, or reduced integration effort?

Clarity (1 = unclear … 3 = clear): 3

## SPARK-30286|original · idea

> Summary: Some thoughts on new features for MLLIB Description: Some thoughts on new features for ML: 1, clustering: *mini-batch KMeans*: KMeans maybe one of the most widely used algs in MLLIB, mini-batch KMeans is much faster than KMeans with [compareable results](https://scikit-learn.org/stable/auto_examples/cluster/plot_mini_batch_kmeans.html#sphx-glr-auto-examples-cluster-plot-mini-batch-kmeans-py); in SKLearn it is a seperate estimator, in MLLIB we may add it as one/two params in existing KMe…

Gold missing: ['expected_impact', 'open_questions', 'target_users'] · unknown: []

- [target_users] Which user group and workload would benefit most from these MLlib additions (e.g., PySpark data scientists running clustering/classification pipelines, or Scala users building custom estimators)? 
- [expected_impact] What concrete improvement would you expect from these features (e.g., faster training, earlier failure on invalid vectors, fewer NaN model coefficients), and how could it be measured?

Clarity (1 = unclear … 3 = clear): 3
