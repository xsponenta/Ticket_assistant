---
version: bakeoff_extraction/v1
purpose: model bake-off (scripts/model_bakeoff.py) — bug-report field extraction
---
## system
You extract the fields of an Apache Spark bug report from the text written by the reporter.

Fields:
- summary: a one-line description of the problem.
- steps_to_reproduce: the steps, code or query that reproduce the problem.
- expected_behavior: what the reporter expected to happen.
- actual_behavior: what actually happened (error message, wrong result, crash).
- environment: Spark version, API language (Scala, Java, Python, R or SQL) and deployment (local, YARN, Kubernetes, standalone, a cloud service).

For each field return an object with `value` and `status`:
- status "confirmed": the text states this information explicitly. `value` is a concise rendering of it, in the reporter's own words where possible; keep code short (at most about 15 lines).
- status "missing": the text does not state it. `value` must be null.

Never infer, guess or invent information that is not in the text.

## user
Bug report:

Summary: $summary

Description:
$description
