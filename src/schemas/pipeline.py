"""Pipeline session state (JSON-serializable) and trace events. See src/pipeline.py for the state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Stage = Literal["intake", "confirm_class", "asking", "scope_decision", "confirm_assumptions", "done", "stopped"]


class TraceEvent(BaseModel):
    """One pipeline step: a component call (LLM or not) or a user action."""

    step: str
    component: str
    at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    latency_ms: float = 0.0
    cost: float = 0.0
    cached: bool | None = None
    llm_calls: int = 0
    input_summary: str = ""
    output_summary: str = ""
    error: str | None = None


class SessionState(BaseModel):
    session_id: str
    stage: Stage = "intake"
    chat: list[dict[str, str]] = Field(default_factory=list)  # everything shown in the UI
    conversation: list[dict[str, str]] = Field(default_factory=list)  # what C4/C5/C6 see: user turns + C5 questions
    summary: str = ""
    class_candidates: list[tuple[str, float]] = Field(default_factory=list)
    component_candidates: list[str] = Field(default_factory=list)
    ticket_class: str | None = None
    component: list[str] = Field(default_factory=list)
    c2_pass1: dict[str, Any] | None = None
    c2_pass2: dict[str, Any] | None = None
    dismissed: list[str] = Field(default_factory=list)
    field_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    question_turns: int = 0
    pending_questions: list[dict[str, str]] = Field(default_factory=list)
    skipped: bool = False
    c3: dict[str, Any] | None = None
    scope_stop_offered: bool = False
    ticket: dict[str, Any] | None = None
    last_error: dict[str, str] | None = None
    retry_segment: str | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
