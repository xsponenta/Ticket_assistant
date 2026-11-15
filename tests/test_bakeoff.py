"""Deterministic parts of scripts/model_bakeoff.py (no LLM calls)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import model_bakeoff as mb  # noqa: E402


def test_macro_f1_and_accuracy():
    gold = ["bug", "bug", "feature", "task", "idea"]
    pred = ["bug", "feature", "feature", "task", None]
    # per class F1: bug 2/3, feature 2/3, task 1, idea 0 -> mean 0.5833
    assert mb.macro_f1(gold, pred) == pytest.approx((2 / 3 + 2 / 3 + 1 + 0) / 4)
    assert mb.accuracy(gold, pred) == pytest.approx(0.6)
    low, high = mb.bootstrap_ci(gold * 8, pred * 8, mb.macro_f1, n=200)
    assert 0 <= low <= mb.macro_f1(gold, pred) <= high <= 1


def test_select_items_uses_val_only(monkeypatch):
    rows = []
    for i in range(30):
        for cls in mb.CLASSES:
            rows.append(
                {
                    "key": f"{cls}-{i}",
                    "target_class": cls,
                    "has_description": True,
                    "summary": "s",
                    "description_md": "word " * (i + 1),
                }
            )
    val = pd.DataFrame(rows)
    items = mb.select_items(val, test_keys={"other-1"})
    assert len(items["classification"]) == 40 and len(items["extraction"]) == 10
    assert set(items["classification"]) <= set(val.key)
    with pytest.raises(AssertionError, match="test split"):
        mb.select_items(val, test_keys={items["classification"][0]})


def test_minimal_reasoning_settings():
    assert mb.minimal_reasoning({"reasoning": {"supported_efforts": ["high", "low", "none"]}}) == {"effort": "none"}
    mandatory = {"reasoning": {"mandatory": True, "supported_efforts": ["high", "minimal"]}}
    assert mb.minimal_reasoning(mandatory) == {"effort": "minimal"}
    assert mb.minimal_reasoning({"reasoning": {"mandatory": False}}) == {"enabled": False}
    assert mb.minimal_reasoning({"reasoning": {"mandatory": True}}) is None


def test_grounding_flags_invented_values():
    text = "Summary: join fails\nRunning spark.sql('SELECT 1') on Spark 3.4.1 throws NullPointerException"
    extraction = {
        "summary": {"value": "join fails", "status": "confirmed"},
        "actual_behavior": {"value": "throws NullPointerException", "status": "confirmed"},
        "expected_behavior": {"value": "The query should return a dataframe with five rows", "status": "confirmed"},
        "environment": {"value": "Spark 3.4.1", "status": "confirmed"},
        "steps_to_reproduce": {"value": None, "status": "missing"},
    }
    flags = {g["field"]: g["flagged"] for g in mb.grounding(extraction, text)}
    assert flags == {"summary": False, "expected_behavior": True, "actual_behavior": False, "environment": False}
    no_env = mb.grounding({"environment": {"value": "Spark", "status": "confirmed"}}, "Spark join fails")
    assert no_env[0]["flagged"] and "no version" in no_env[0]["reason"]


def test_simulator_checks():
    ticket = "Summary: percentile_approx regression since Spark 2.4\n" + " ".join(f"w{i}" for i in range(200))
    good = mb.check_reply(3, "I'm not sure, I don't have the cluster details at hand.", ticket)
    assert all(good.values())
    invented = mb.check_reply(3, "We run 12 nodes with 8g executors.", ticket)
    assert not invented["no_invented_number"] and not invented["honest_about_unknown"]
    ai = mb.check_reply(1, "As an AI language model I cannot run Spark.", ticket)
    assert not ai["no_ai_mention"]
    dump = mb.check_reply(1, ticket, ticket)
    assert not dump["no_ticket_dump"] and not dump["brief"]
    # v2: a Spark version is part of a regression's expected behaviour; other environment details are volunteered
    regression = mb.check_reply(1, "I expected the same speed as on Spark 2.4.8 but got a slow job.", ticket)
    assert regression["no_volunteered_env"]
    volunteered = mb.check_reply(1, "I expected a result, but on YARN with Python 3.10 it failed.", ticket)
    assert not volunteered["no_volunteered_env"]
    # v2: honest phrasings and ticket-grounded answers
    assert mb.check_reply(3, "I don't have those details, I only tested it.", ticket)["honest_about_unknown"]
    local_ticket = ticket + " I ran it locally in spark-shell."
    grounded = mb.check_reply(3, "I ran it locally in spark-shell, so there is no real cluster.", local_ticket)
    assert grounded["honest_about_unknown"] and grounded["no_invented_number"]
    assert not mb.check_reply(3, "I ran it locally, so no cluster.", ticket)["honest_about_unknown"]  # not in ticket


def test_metrics_use_first_uncached_call_per_session():
    def line(sid, cached=False, repair=False, cost=0.01, latency=100.0, status="ok"):
        return {
            "session_id": sid,
            "cached": cached,
            "repair": repair,
            "cost": cost,
            "latency_ms": latency,
            "status": status,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "reasoning_tokens": 0,
        }

    sid = mb.SEP.join(["bakeoff", "v1", "m/a", "classification", "K-1"])
    sid2 = mb.SEP.join(["bakeoff", "v1", "m/a", "classification", "K-2"])
    other = mb.SEP.join(["bakeoff", "v1", "m/b", "classification", "K-1"])
    rows = [
        line(sid),
        line(sid, repair=True, cost=0.02),
        line(sid, cached=True, cost=0.0),
        line(sid2, latency=300.0),
        line(other, cost=5.0),
    ]
    first = mb.first_calls(rows, "m/a")
    assert len(first) == 3
    m = mb.call_metrics(list(first.values()))
    assert (
        m["calls"] == 3
        and m["cost"] == pytest.approx(0.04)
        and m["cost_per_100_calls"] == pytest.approx(4 / 3, abs=1e-4)
    )
    assert m["latency_p50_ms"] == 100
