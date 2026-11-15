"""C4/C5: spans, ablation variants and gold, output models, deterministic metrics, test lock (no LLM calls)."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import eval_c4  # noqa: E402
import eval_c5  # noqa: E402

from src.components.question_generator import field_lists  # noqa: E402
from src.eval import ablation  # noqa: E402
from src.eval.build_gap_ablation import UNKNOWN_REPLIES, build_items, ground, ticket_text  # noqa: E402
from src.eval.spans import delete_spans, find_spans, overlaps, quote_grounded  # noqa: E402
from src.schemas.c4 import ExtractedField, c4_model  # noqa: E402

DESCRIPTION = (
    "We noticed a problem in production while running a daily job with many joins over large tables today.\n\n"
    "Steps: spark.range(3).join(spark.range(3), 'id').show()\n\n"
    "Expected: three rows with ids 0, 1 and 2.\n\n"
    "Actual: NullPointerException at Join.scala:42.\n\n"
    "Environment: Spark 3.5.1, PySpark, YARN."
)
QUOTES = {
    "steps_to_reproduce": "spark.range(3).join(spark.range(3), 'id').show()",
    "expected_behavior": "three rows with ids 0, 1 and 2.",
    "actual_behavior": "NullPointerException at Join.scala:42.",
    "environment": "Spark 3.5.1, PySpark, YARN.",
}


def bug_record(quotes=QUOTES):
    text = ticket_text("Join fails with NPE", DESCRIPTION)
    raw = {n: {"status": "confirmed", "value": q, "quotes": [q]} for n, q in quotes.items()}
    raw |= {n: {"status": "missing", "value": None, "quotes": []} for n in ("regression_since", "workaround")}
    return {"key": "SPARK-1", "split": "dev", "class": "bug", "text": text, "extraction": ground(raw, text)}


def test_find_spans_exact_flexible_and_short():
    text = "Run  spark.range(3)\n  .show() now"
    assert find_spans("spark.range(3) .show()", text) == [(5, 29)]
    assert find_spans("Run", text) == [(0, 3)] and find_spans("ab", text) == []
    assert not quote_grounded("spark.range(4)", text)


def test_delete_spans_tidies_and_overlaps():
    assert delete_spans("a b\n\n\nX\n\n\nc", [(6, 7)]) == "a b\n\nc"
    assert overlaps([(0, 5)], [(4, 9)]) and not overlaps([(0, 5)], [(5, 9)])


def test_build_items_variants_and_gold():
    by_id = {i["variant"]: i for i in build_items(bug_record())}
    original = by_id["original"]
    assert original["gold_missing"] == ["regression_since", "workaround"] and len(original["gold_present"]) == 4
    env = by_id["minus_environment"]
    assert "3.5.1" not in env["conversation"][0]["content"] and "environment" in env["gold_missing"]
    assert "environment" not in env["gold_present"] and env["removed"] == ["environment"]
    assert sum(len(i["removed"]) == 2 and i["variant"].startswith("minus_") for i in by_id.values()) == 1
    answered = next(i for i in by_id.values() if i["variant"].startswith("answered_"))
    f = answered["removed"][0]
    assert [t["role"] for t in answered["conversation"]] == ["user", "assistant", "user"]
    assert answered["conversation"][2]["content"] == QUOTES[f] and f in answered["gold_present"]
    unknown = next(i for i in by_id.values() if i["variant"].startswith("unknown_"))
    g = unknown["removed"][0]
    assert unknown["gold_unknown"] == [g] and g not in unknown["gold_missing"] + unknown["gold_present"]
    assert unknown["conversation"][2]["content"] in UNKNOWN_REPLIES and g != f
    assert len(by_id) == 8 and build_items(bug_record()) == build_items(bug_record())  # 1+4+1+1+1, deterministic


def test_overlapped_field_is_left_out_of_scoring_and_title_is_never_deleted():
    overlapping = dict(QUOTES, actual_behavior="2.\n\nActual: NullPointerException")
    by_id = {i["variant"]: i for i in build_items(bug_record(overlapping))}
    expected = by_id["minus_expected_behavior"]
    assert "actual_behavior" in expected["excluded_fields"] and "actual_behavior" not in expected["gold_present"]
    assert "actual_behavior" not in by_id["minus_environment"]["excluded_fields"]
    in_title = dict(QUOTES, actual_behavior="Join fails with NPE")  # quoted from the title
    variants = {i["variant"] for i in build_items(bug_record(in_title))}
    assert "minus_actual_behavior" not in variants and "minus_environment" in variants


def test_c4_model_and_extraction_validation():
    model = c4_model("idea")
    state = {"status": "missing", "value": None, "evidence": []}
    names = list(model.model_fields)
    assert names[:3] == ["summary", "component", "labels"] and "target_users" in names
    model.model_validate(dict.fromkeys(names, state))
    with pytest.raises(ValidationError):
        model.model_validate(dict.fromkeys(names[:-1], state))
    with pytest.raises(ValidationError):
        model.model_validate(dict.fromkeys(names, state) | {"extra": state})
    with pytest.raises(ValidationError, match="verbatim quote"):
        ExtractedField(status="confirmed", value="x", quotes=[])


def state(status, evidence=()):
    return {"status": status, "value": None, "evidence": list(evidence)}


def bug_item(variant, removed, missing, present, unknown=(), text="Spark 3.5.1 fails"):
    return {
        "item_id": f"K|{variant}",
        "key": "K",
        "class": "bug",
        "variant": variant,
        "conversation": [{"role": "user", "content": text}],
        "removed": removed,
        "gold_missing": missing,
        "gold_present": present,
        "gold_unknown": list(unknown),
        "excluded_fields": [],
    }


def test_c4_metrics():
    common = {
        "summary": state("confirmed", ["Spark 3.5.1 fails"]),
        "component": state("assumed"),
        "labels": state("missing"),
    }
    a = bug_item(
        "minus_environment",
        ["environment"],
        ["environment", "regression_since", "workaround"],
        ["steps_to_reproduce", "expected_behavior", "actual_behavior"],
    )
    sa = common | {
        "steps_to_reproduce": state("confirmed", ["Spark 3.5.1"]),
        "expected_behavior": state("confirmed", ["not in the text"]),
        "actual_behavior": state("confirmed", ["fails"]),
        "environment": state("confirmed", ["Spark 3.5.1"]),
        "regression_since": state("missing"),
        "workaround": state("missing"),
    }
    b = bug_item(
        "unknown_actual_behavior",
        ["actual_behavior"],
        ["regression_since", "workaround"],
        ["steps_to_reproduce", "expected_behavior", "environment"],
        unknown=["actual_behavior"],
    )
    sb = sa | {"environment": state("assumed"), "actual_behavior": state("unknown")}
    m = eval_c4.c4_metrics([a, b], [{"item_id": a["item_id"], "states": sa}, {"item_id": b["item_id"], "states": sb}])
    assert m["missing"]["precision"] == 1.0 and m["missing"]["recall"] == 0.8  # 4 of 5 gold-missing found
    assert m["false_confirmed_rate"] == 1.0 and m["n_deleted_fields"] == 1
    assert m["unknown_detected"] == 1.0 and m["false_unknown_rate"] == 0.0
    assert m["confirmed_grounded"] == 0.75  # 2 of 8 confirmed fields cite a quote that is not in the text
    assert m["common_fields"]["component:assumed"] == 2


def test_c5_item_metrics_and_field_lists():
    item = bug_item(
        "minus_steps_to_reproduce",
        ["steps_to_reproduce"],
        ["steps_to_reproduce", "workaround"],
        ["expected_behavior", "actual_behavior", "environment"],
    )
    qs = [{"target_field": "workaround", "question": "?"}, {"target_field": "steps_to_reproduce", "question": "?"}]
    m = eval_c5.item_metrics(item, [*qs, {"target_field": "environment", "question": "?"}], {})
    assert not m["le_2"] and m["targeted"] == [False, True] and m["order_violation"] is False and m["coverage"] == 1.0
    m = eval_c5.item_metrics(item, qs[:1], {})
    assert m["order_violation"] is True and m["coverage"] == 0.0 and m["redundant"] == [False]
    unknown = bug_item("unknown_environment", ["environment"], ["workaround"], [], unknown=["environment"])
    m = eval_c5.item_metrics(
        unknown, [{"target_field": "environment", "question": "?"}], {"environment": state("missing")}
    )
    assert m["reasked_unknown"] and m["reask_cause"] == "C4" and m["redundant"] == [False]
    missing, provided, unk = field_lists(
        "bug",
        {"workaround": state("missing"), "environment": state("unknown"), "expected_behavior": state("confirmed")}
        | {"actual_behavior": state("confirmed"), "regression_since": state("confirmed")},
    )
    assert missing.index("steps_to_reproduce") < missing.index("workaround") and unk == "- environment"
    assert "expected_behavior" in provided and "environment" not in provided + missing


def test_load_items_checks_test_hash(tmp_path):
    item = bug_item("original", [], [], []) | {"split": "test"}
    path, meta = tmp_path / "a.jsonl", tmp_path / "m.json"
    path.write_text(json.dumps(item) + "\n")
    meta.write_text(json.dumps({"test_sha256": ablation.items_sha256([item])}))
    assert ablation.load_items("test", path, meta) == [item]
    meta.write_text(json.dumps({"test_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="test_sha256"):
        ablation.load_items("test", path, meta)


def test_c4_test_lock(tmp_path):
    with pytest.raises(SystemExit, match="--confirm-test"):
        eval_c4.check_test_allowed("test", False, False, tmp_path / "x.json", tmp_path, prefix="c4")


def test_c4_audit_strata_allocation_and_estimate():
    from src.eval.c4_audit_cli import allocate, corrected, evidence_source

    text = "Summary: X fails\n\nDescription:\nfoo bar baz qux. other stuff here."
    assert evidence_source(text, ["X fails"], []) == "title"
    assert evidence_source(text, ["foo bar baz"], ["foo bar baz qux."]) == "other field's passage"
    assert evidence_source(text, ["other stuff"], ["foo bar baz qux."]) == "unquoted text"
    assert evidence_source(text, ["zzz"], []) == "evidence not found"
    sizes = {"other field's passage": 58, "unquoted text": 45, "title": 33, "evidence not found": 1}
    assert allocate(sizes, 20) == {"other field's passage": 8, "unquoted text": 7, "title": 5, "evidence not found": 0}
    meta = {"c4_missing": 10, "population": {"a": {"confirmed": 10, "assumed": 10}, "b": {"assumed": 4}}}
    est = corrected(meta, {"a": ["y", "n"]})  # stratum b has no labels -> pooled shares
    assert est["leaked_share_of_resolved"] == 0.5
    assert est["false_confirmed_rate"] == 5 / 22 and est["resolved_but_gone_rate"] == 12 / 22
