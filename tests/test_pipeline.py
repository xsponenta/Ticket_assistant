"""Pipeline state machine and headless driver with mocked components (no LLM, no models)."""

from types import SimpleNamespace

from src.components.ticket_composer import render
from src.pipeline import MAX_TURNS, Components, Pipeline
from src.pipeline_driver import run_dialogue
from src.schemas.c2 import C2Output, DuplicateCandidate
from src.schemas.c3 import C3Output
from src.schemas.c4 import FieldState
from src.schemas.c5 import C5Output, Question
from src.schemas.c6 import draft_model
from src.schemas.pipeline import SessionState
from src.schemas.ticket_fields import class_fields, fields_for

CHUNK = {"chunk_id": "doc#1", "url": "https://spark.apache.org/x.html", "text": "Use `spark.sql.adaptive.enabled`."}


class World:
    """Scripted components: C4 resolves one more required field per user turn; the last one stays assumed."""

    def __init__(self, cls="bug", always_missing=False, verdict="needs_development", reference=None, fail_compose=0):
        self.cls, self.always_missing, self.fail_compose = cls, always_missing, fail_compose
        self.verdict, self.reference = verdict, reference
        self.calls: list[tuple] = []

    def components(self) -> Components:
        return Components(
            self.classify, self.find_duplicates, self.detect_gaps, self.ask, self.check_scope, self.compose
        )

    def classify(self, summary, description):
        self.calls.append(("C1",))
        return {"classes": [(self.cls, 0.7), ("task", 0.2)], "components": ["SQL", "Spark Core", "PySpark"]}

    def find_duplicates(self, summary, description, mode, exclude):
        self.calls.append(("C2", mode, tuple(exclude)))
        keys = [k for k in ("SPARK-1", "SPARK-2") if k not in exclude]
        cands = [DuplicateCandidate(key=k, summary=k, url=f"https://x/{k}", score=0.9) for k in keys]
        return C2Output(candidates=cands, alert=True, alert_score=0.9)

    def detect_gaps(self, conversation, cls, session_id=None):
        self.calls.append(("C4",))
        answers = sum(t["role"] == "user" for t in conversation) - 1
        required = [f.name for f in class_fields(cls) if f.required]
        states = {f.name: FieldState(evidence=[], status="missing", value=None) for f in fields_for(cls)}
        resolved = 0 if self.always_missing else answers + 1
        for i, name in enumerate(required[:resolved]):
            status = "assumed" if i == len(required) - 1 else "confirmed"
            states[name] = FieldState(evidence=["x"], status=status, value=f"{name} value")
        return states

    def ask(self, conversation, cls, states, session_id=None):
        self.calls.append(("C5",))
        missing = [
            n for n, s in states.items() if s["status"] == "missing" and n in {f.name for f in class_fields(cls)}
        ]
        return C5Output(questions=[Question(target_field=missing[0], question=f"What is the {missing[0]}?")])

    def check_scope(self, summary, description, session_id=None):
        self.calls.append(("C3",))
        out = C3Output(rationale="r", verdict=self.verdict, explanation="Set the config.", doc_reference=self.reference)
        return out, [CHUNK]

    def compose(self, conversation, cls, component, states, session_id=None):
        self.calls.append(("C6",))
        if self.fail_compose:
            self.fail_compose -= 1
            raise RuntimeError("provider down")
        texts = {f.name: states[f.name]["value"] for f in class_fields(cls)}
        draft = draft_model(cls).model_validate({"title": "A descriptive title", "labels": [], "fields": texts})
        return render(cls, component, states, draft)


def steps(state: SessionState) -> list[str]:
    return [e.step for e in state.trace]


def test_bug_walk_to_done_with_assumption_correction():
    world = World("bug")
    p = Pipeline(world.components())
    s = p.start(p.new_session(), "Join fails with NPE\nWhen I run a join on two tables it crashes.")
    assert s.stage == "confirm_class" and s.class_candidates[0] == ("bug", 0.7) and s.summary == "Join fails with NPE"
    assert ("C2", "summary", ()) in world.calls
    s = p.confirm_class(s, "bug", ["SQL"])
    assert s.stage == "asking" and s.pending_questions[0]["target_field"] == "expected_behavior"
    for answer in ("Expected three rows", "NPE at Join.scala", "Spark 3.5.1"):
        s = p.answer(s, answer)
    assert s.stage == "confirm_assumptions" and ("C3",) not in world.calls  # no scope check for bugs
    assert "### Assumptions to confirm" in s.ticket["body_markdown"]
    s = p.confirm_assumptions(s, {"environment": "Spark 3.5.1 on YARN"})
    assert s.stage == "done" and s.ticket["fields"]["environment"] == {
        "status": "confirmed",
        "value": "Spark 3.5.1 on YARN",
    }
    assert "Assumptions to confirm" not in s.ticket["body_markdown"]
    assert steps(s)[:4] == ["C1", "C2 pass 1", "confirm_class", "C4"] and steps(s)[-3:] == [
        "C2 pass 2",
        "C6",
        "confirm_assumptions",
    ]
    assert SessionState.model_validate_json(s.model_dump_json()) == s  # serializable


def test_question_turns_are_capped():
    world = World("bug", always_missing=True)
    p = Pipeline(world.components())
    s = p.confirm_class(p.start(p.new_session(), "It crashes"), "bug", ["SQL"])
    for _ in range(MAX_TURNS):
        assert s.stage == "asking"
        s = p.answer(s, "more detail")
    assert s.question_turns == MAX_TURNS and s.stage == "done"  # missing fields stay "Not provided"
    assert "_Not provided_" in s.ticket["body_markdown"]


def test_skip_stops_questions_without_another_c4_call():
    world = World("bug", always_missing=True)
    p = Pipeline(world.components())
    s = p.confirm_class(p.start(p.new_session(), "It crashes"), "bug", ["SQL"])
    n_c4 = world.calls.count(("C4",))
    s = p.answer(s, "skip")
    assert s.skipped and s.stage == "done" and world.calls.count(("C4",)) == n_c4 and "skip" in steps(s)


def feature_until_scope(reference):
    world = World("feature", verdict="already_supported", reference=reference)
    p = Pipeline(world.components())
    s = p.confirm_class(p.start(p.new_session(), "Please add X"), "feature", ["SQL"])
    while s.stage == "asking":
        s = p.answer(s, "detail")
    return world, p, s


def test_scope_stop_only_for_grounded_already_supported():
    world, p, s = feature_until_scope("spark.sql.adaptive.enabled")  # in the retrieved chunk
    assert s.stage == "scope_decision" and s.scope_stop_offered and ("C3",) in world.calls and s.c3["grounded"]
    assert p.scope_decision(s, stop=True).stage == "stopped"
    assert p.scope_decision(s, stop=False).stage == "confirm_assumptions"
    _, _, s = feature_until_scope("spark.sql.not.in.docs")  # ungrounded: no stop offered
    assert s.stage == "confirm_assumptions" and not s.scope_stop_offered and not s.c3["grounded"]


def test_dismissed_candidates_are_excluded_from_pass_2():
    world = World("bug")
    p = Pipeline(world.components())
    s = p.dismiss(p.start(p.new_session(), "It crashes"), "SPARK-1")
    s = p.confirm_class(s, "bug", ["SQL"])
    while s.stage == "asking":
        s = p.answer(s, "detail")
    assert ("C2", "full", ("SPARK-1",)) in world.calls
    assert [c["key"] for c in s.c2_pass2["candidates"]] == ["SPARK-2"]


def test_failed_step_keeps_state_and_retry_recovers():
    world = World("task", fail_compose=1)
    p = Pipeline(world.components())
    s = p.confirm_class(p.start(p.new_session(), "Upgrade netty"), "task", ["Build"])
    while s.stage == "asking" and not s.last_error:
        s = p.answer(s, "detail")
    assert s.last_error["step"] == "C6" and s.retry_segment == "gather" and s.ticket is None
    assert s.trace[-1].error.startswith("RuntimeError") and "failed (C6)" in s.chat[-1]["content"]
    s = p.retry(s)
    assert s.last_error is None and s.stage == "confirm_assumptions" and s.ticket is not None


def answer_with(text):
    return lambda state, questions: text


def test_driver_bug_walk_uses_the_policy():
    world = World("bug")
    s = run_dialogue(Pipeline(world.components()), "Join fails\nNPE on join", answer_with("detail"))
    assert s.stage == "done" and s.ticket_class == "bug" and s.component == ["SQL"] and s.dismissed == []
    assert s.ticket["fields"]["environment"]["status"] == "confirmed"  # assumption accepted as is


def test_driver_continues_on_scope_stop_and_handles_cap_and_skip():
    world = World("feature", verdict="already_supported", reference="spark.sql.adaptive.enabled")
    s = run_dialogue(Pipeline(world.components()), "Please add X", answer_with("detail"))
    assert s.scope_stop_offered and s.stage == "done"
    capped = run_dialogue(Pipeline(World("bug", always_missing=True).components()), "crash", answer_with("more"))
    assert capped.stage == "done" and capped.question_turns == MAX_TURNS
    skipped = run_dialogue(Pipeline(World("bug", always_missing=True).components()), "crash", answer_with("skip"))
    assert skipped.skipped and skipped.question_turns == 1 and skipped.stage == "done"


def test_driver_stops_on_failure():
    s = run_dialogue(Pipeline(World("task", fail_compose=5).components()), "Upgrade netty", answer_with("detail"))
    assert s.last_error is not None and s.ticket is None
    assert SimpleNamespace(stage=s.stage).stage != "done"


def test_m6_pass1_never_alerts_and_confirmed_component_wins():
    world = World("bug")
    original = world.detect_gaps

    def c4_with_other_component(conversation, cls, session_id=None):
        states = original(conversation, cls, session_id)
        states["component"] = FieldState(evidence=["guess"], status="assumed", value="Spark Core")
        return states

    world.detect_gaps = c4_with_other_component
    p = Pipeline(world.components())
    s = p.start(p.new_session(), "Join fails\nNPE on join")
    assert s.c2_pass1["alert"] is False  # the finder said alert=True
    s = p.confirm_class(s, "bug", ["SQL", "PySpark"])
    assert s.field_states["component"] == {
        "status": "confirmed",
        "value": "SQL, PySpark",
        "evidence": ["confirmed in the UI"],
    }
    while s.stage == "asking":
        s = p.answer(s, "detail")
        assert s.field_states["component"]["value"] == "SQL, PySpark"
    assert s.c2_pass2["alert"] is True and s.ticket["component"] == ["SQL", "PySpark"]


def test_m7_failed_scope_check_continues_to_the_ticket():
    world = World("feature")

    def broken_scope(summary, description, session_id=None):
        raise ValueError("doc_reference is required when verdict is already_supported")

    world.check_scope = broken_scope
    p = Pipeline(world.components())
    s = p.confirm_class(p.start(p.new_session(), "Please add X"), "feature", ["SQL"])
    while s.stage == "asking":
        s = p.answer(s, "detail")
    assert s.last_error is None and s.ticket is not None and s.stage in ("confirm_assumptions", "done")
    assert s.c3["failed"] and "doc_reference" in s.c3["error"] and not s.scope_stop_offered
    assert any(e.step == "C3" and e.error for e in s.trace)
