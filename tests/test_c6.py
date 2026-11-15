"""C6: deterministic ticket rendering, text-grounding helpers and the eval metrics (no LLM calls)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import eval_c6  # noqa: E402

from src.components.ticket_composer import render  # noqa: E402
from src.eval.spans import content_word_share, invented_tokens, risky_tokens  # noqa: E402
from src.schemas.c6 import MISSING_TEXT, UNKNOWN_TEXT, draft_model  # noqa: E402

USER = "Summary: groupBy fails\n\nDescription:\nRunning df.groupBy(col) on Spark 3.5.1 gives wrong results."


def st(status, value=None, evidence=()):
    return {"status": status, "value": value, "evidence": list(evidence)}


STATES = {
    "steps_to_reproduce": st("confirmed", "df.groupBy(col)", ["df.groupBy(col)"]),
    "expected_behavior": st("missing"),
    "actual_behavior": st("unknown"),
    "environment": st("assumed", "Spark 3.5.1, PySpark", ["Spark 3.5.1"]),
    "regression_since": st("missing"),
    "workaround": st("confirmed", "", []),
}


def draft(**fields):
    texts = dict.fromkeys(
        ["steps_to_reproduce", "expected_behavior", "actual_behavior", "environment", "regression_since", "workaround"]
    )
    return draft_model("bug").model_validate(
        {"title": "groupBy returns wrong results on Spark 3.5.1", "labels": ["correctness"], "fields": texts | fields}
    )


def test_render_enforces_the_rules():
    t = render(
        "bug",
        ["SQL"],
        STATES,
        draft(steps_to_reproduce="Run df.groupBy(col)", expected_behavior="invented", environment="Spark 3.5.1"),
    )
    assert t.jira_type == "Bug" and t.component == ["SQL"] and t.labels == ["correctness"]
    assert t.fields["actual_behavior"].value == UNKNOWN_TEXT and t.fields["expected_behavior"].value is None
    assert "invented" not in t.body_markdown  # text for a missing field is ignored
    assert f"### Expected behavior\n\n{MISSING_TEXT}" in t.body_markdown  # required -> shown as not provided
    assert "### Regression since" not in t.body_markdown  # optional missing -> omitted
    assert t.fields["workaround"].status == "missing"  # confirmed but no text anywhere -> not provided
    assert t.body_markdown.split("### Assumptions to confirm")[1].strip() == "- **Environment:** Spark 3.5.1"
    assert "priority" not in t.body_markdown.lower()


def test_text_grounding_helpers():
    assert content_word_share("Given df.groupBy When running Then wrong results", USER) == 1.0
    assert content_word_share("cluster has 200 executors", USER) == 0.0
    assert {"3.5.1", "spark.sql.x", "df.groupBy", "LongType", "run_id"} <= risky_tokens(
        "`spark.sql.x` on 3.5.1: df.groupBy( LongType run_id"
    )
    assert invented_tokens("Spark 3.5.1 and 3.4.0, `spark.sql.y`", USER) == ["3.4.0", "spark.sql.y"]
    assert risky_tokens("```bash\nx\n``` the `b` flag, so `a b` is prose") == set()  # no prose between backticks


def test_item_metrics():
    ticket = render("bug", ["SQL"], STATES, draft(steps_to_reproduce="Run df.groupBy(col)", environment="Spark 3.5.1"))
    item = {"class": "bug", "conversation": [{"role": "user", "content": USER}]}
    m = eval_c6.item_metrics(item, STATES, ticket.model_dump())
    assert m["required"] == 4 and m["covered"] == 3 and m["resolved_required"] == 3 and m["covered_of_resolved"] == 3
    assert m["missing_filled"] == 0 and all(g["ok"] for g in m["grounded"].values())
    assert m["invented"] == [] and m["assumptions_listed"] and m["unknown_rendered"]
    assert m["labels_without_cue"] == [] and not m["forbidden_line"] and m["title_ok"] and m["gwt"] is None
