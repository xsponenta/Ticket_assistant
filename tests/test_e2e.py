"""End-to-end evaluation helpers: opener leak check, simulator checks, scoring, policies (no LLM calls)."""

import sys
from pathlib import Path

from test_pipeline import World

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import eval_e2e  # noqa: E402

from src.eval.simulator import DONT_KNOW_RE, dont_know_only, opener_leaks, sentences  # noqa: E402
from src.pipeline import Pipeline  # noqa: E402
from src.pipeline_driver import Policy, run_dialogue  # noqa: E402

DESCRIPTION = "When I run a left join on decimal keys the join drops rows silently. Spark 3.5.1, PySpark."
HIDDEN = f"Summary: Left join drops rows\n\nDescription:\n{DESCRIPTION}"


def test_opener_leak_check():
    assert opener_leaks("My joins seem to lose some data lately.", "Left join drops rows", DESCRIPTION) == []
    reasons = opener_leaks("Spark 3.5.1 throws NullPointerException on a join", "Join fails", DESCRIPTION)
    assert any("3.5.1" in r for r in reasons) and "error text" in reasons
    assert any("copies the description" in r for r in opener_leaks("the join drops rows silently", "x", DESCRIPTION))
    assert any("words" in r for r in opener_leaks(" ".join(["word"] * 21), "x", DESCRIPTION))


def test_simulator_checks():
    assert DONT_KNOW_RE.search("I don't know which version, sorry.") and DONT_KNOW_RE.search("Not sure about that.")
    assert not DONT_KNOW_RE.search("It runs on Spark 3.5.1.") and sentences("One. Two! Three?") == 3
    assert DONT_KNOW_RE.search("I don't have the code snippet available right now.")
    assert dont_know_only("I don't know. Not sure, sorry.")
    assert not dont_know_only("I don't know the version, but I built it with Maven.")


def test_turn_latencies():
    trace = [
        {"step": "C1", "latency_ms": 5},
        {"step": "C2 pass 1", "latency_ms": 100},
        {"step": "confirm_class", "latency_ms": 0},
        {"step": "C4", "latency_ms": 2000},
        {"step": "C5", "latency_ms": 1000},
        {"step": "answer", "latency_ms": 0},
        {"step": "C4", "latency_ms": 1500},
        {"step": "confirm_assumptions", "latency_ms": 0},
    ]
    assert eval_e2e.turn_latencies(trace) == [105, 3000, 1500]


def field(status, value):
    return {"status": status, "value": value}


def transcript(ticket_class, fields, title="Left join on decimal keys drops rows on Spark 3.4.0"):
    ticket = {"title": title, "fields": fields, "body_markdown": "", "component": ["SQL"]}
    state = {
        "stage": "done",
        "last_error": None,
        "ticket": ticket,
        "ticket_class": ticket_class,
        "component": ["SQL"],
        "class_candidates": [["feature", 0.6], ["bug", 0.3]],
        "conversation": [
            {"role": "user", "content": "My left join drops rows."},
            {"role": "assistant", "content": "1. Which Spark version?"},
            {"role": "user", "content": "Spark 3.5.1 with PySpark, decimal keys."},
        ],
        "trace": [{"step": "C4", "latency_ms": 2000, "cost": 0.0002}],
        "question_turns": 1,
    }
    sim_turns = [
        {"questions": [{"target_field": "environment", "question": "?"}], "answer": "Spark 3.5.1 with PySpark."}
    ]
    return {
        "key": "K",
        "gold_class": "bug",
        "policy": "corrects",
        "opener_leaks": [],
        "sim_turns": sim_turns,
        "state": state,
    }


REC = {
    "text": HIDDEN,
    "extraction": {
        "steps_to_reproduce": {
            "status": "confirmed",
            "grounded": True,
            "value": "Left join on decimal keys",
            "quotes": ["run a left join on decimal keys"],
        },
        "expected_behavior": {"status": "missing", "grounded": True, "value": None, "quotes": []},
        "actual_behavior": {
            "status": "confirmed",
            "grounded": True,
            "value": "Rows dropped silently",
            "quotes": ["the join drops rows silently"],
        },
        "environment": {
            "status": "confirmed",
            "grounded": True,
            "value": "Spark 3.5.1, PySpark",
            "quotes": ["Spark 3.5.1, PySpark."],
        },
        "regression_since": {"status": "missing", "grounded": True, "value": None, "quotes": []},
        "workaround": {"status": "missing", "grounded": True, "value": None, "quotes": []},
    },
}


def test_score_recovery_recall_invention_and_business_proxy():
    fields = {
        "steps_to_reproduce": field("missing", None),
        "expected_behavior": field("missing", None),
        "actual_behavior": field("confirmed", "The left join drops rows."),
        "environment": field("confirmed", "Spark 3.5.1, PySpark"),
        "regression_since": field("missing", None),
        "workaround": field("missing", None),
    }
    s = eval_e2e.score(transcript("bug", fields), REC)
    assert s["completed"] and s["gold_required"] == 3 and s["recovered"] == 2  # steps not recovered
    assert s["recall"] == [1 / 3, 1.0] and s["recall_quotes"] == [0.75, 1.0]  # lexical: "dropped" != "drops"
    assert s["bug_all_four"] is False
    assert s["invented_vs_conversation"] == ["3.4.0"] and s["invented_vs_ticket"] == ["3.4.0"]
    assert not s["class_top1"] and s["class_top2"] and s["user_turns"] == 2 and s["turn_latency_ms"] == [2000]
    wrong_class = eval_e2e.score(transcript("feature", fields), REC)
    assert wrong_class["recovered"] == 0  # under policy auto a wrong class loses the gold fields
    assert s["sim"][0]["all_present"] and not s["sim"][0]["dont_know"]


def test_driver_confirm_class_policy_and_answer_event():
    world = World("bug")
    s = run_dialogue(Pipeline(world.components()), "crash", lambda st, q: "detail", Policy(confirm_class="task"))
    assert s.ticket_class == "task" and s.stage == "done"
    assert "answer" in [e.step for e in s.trace]
