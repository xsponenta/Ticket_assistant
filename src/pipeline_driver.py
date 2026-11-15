"""Headless driver: run a whole intake dialogue without the UI (for the e2e evaluation with a simulated user).

    state = run_dialogue(pipeline, "Spark crashes when ...", answer_fn, Policy())

`answer_fn(state, questions) -> str` answers C5's questions (later: the simulator). The policy fixes every other
user action, so runs are reproducible: confirm C1's top-1 class and top-1 component, dismiss nothing, continue on
the scope stop offer, accept all assumptions as they are. Returns the final state with the full trace; stops early
on a failed step (state.last_error) or after `max_actions` user actions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.pipeline import Pipeline
from src.schemas.pipeline import SessionState

AnswerFn = Callable[[SessionState, list[dict[str, str]]], str]


@dataclass(frozen=True)
class Policy:
    dismiss_duplicates: bool = False
    continue_on_scope_stop: bool = True
    max_actions: int = 12


def run_dialogue(
    pipeline: Pipeline, first_message: str, answer_fn: AnswerFn, policy: Policy = Policy()
) -> SessionState:
    state = pipeline.start(pipeline.new_session(), first_message)
    for _ in range(policy.max_actions):
        if state.last_error or state.stage in ("done", "stopped"):
            return state
        if state.stage == "confirm_class":
            if policy.dismiss_duplicates:
                for c in (state.c2_pass1 or {}).get("candidates", []):
                    state = pipeline.dismiss(state, c["key"])
            state = pipeline.confirm_class(state, state.class_candidates[0][0], state.component_candidates[:1])
        elif state.stage == "asking":
            state = pipeline.answer(state, answer_fn(state, state.pending_questions))
        elif state.stage == "scope_decision":
            state = pipeline.scope_decision(state, stop=not policy.continue_on_scope_stop)
        elif state.stage == "confirm_assumptions":
            state = pipeline.confirm_assumptions(state, {})
    return state
