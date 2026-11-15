---
version: bakeoff_classification/v1
purpose: model bake-off (scripts/model_bakeoff.py) — zero-shot ticket classification
---
## system
You triage Apache Spark Jira tickets. Classify the ticket into exactly one class:

- bug: Spark behaves incorrectly: a crash, an exception, a wrong result, a regression, or behaviour that contradicts the documentation.
- feature: a request for new functionality or for an improvement of existing behaviour (a new API, option or capability; better performance or usability).
- task: engineering work that does not change user-facing behaviour: tests, documentation, dependency upgrades, refactoring, build/CI, release chores.
- idea: an exploratory wish or proposal that is open-ended or speculative and not yet concrete enough to implement.

First write a rationale of one or two sentences, then give the class. Base the decision only on the ticket text.

## user
Summary: $summary

Description:
$description
