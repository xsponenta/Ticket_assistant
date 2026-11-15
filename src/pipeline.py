"""Ticket intake pipeline: an explicit state machine over C1-C6 (no agent framework; AGENTS.md).

    pipeline = Pipeline(components)                  # components: src/pipeline_resources.load_components()
    state = pipeline.new_session()
    state = pipeline.start(state, "Spark crashes when ...")
    state = pipeline.confirm_class(state, "bug", ["SQL"])
    state = pipeline.answer(state, "Spark 3.5.1 on YARN")   # or "skip"
    ...                                              # scope_decision / confirm_assumptions / dismiss / retry

Stages: intake -> confirm_class -> asking* -> [scope_decision] -> confirm_assumptions -> done | stopped.
Every user action runs the automatic steps up to the next user input ("segments"):
- classify: C1 (baseline, top-2 classes, top-3 components; M1) + C2 pass 1 (summary-only threshold; M2);
- gather:   C4 -> C5 while class fields are missing, < MAX_TURNS question turns and the user did not "skip";
- scope:    C3 for feature/task/idea; a stop is offered only for a grounded already_supported (M3); a failed C3
            call continues to the ticket (M7);
- compose:  C2 pass 2 (full threshold, dismissed candidates removed) -> C6; assumed fields go to the user (M4).
A failing step is recorded in the trace and `last_error`; the stage does not change and `retry()` reruns the segment.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src import llm
from src.components.ticket_composer import render
from src.eval.judges import reference_grounded
from src.schemas.c6 import draft_model
from src.schemas.pipeline import SessionState, TraceEvent
from src.schemas.ticket_fields import class_fields, heading

log = logging.getLogger("pipeline")
MAX_TURNS = 4  # question turns (AGENTS.md flow)
MAX_QUESTIONS = 2
SCOPE_CLASSES = ("feature", "task", "idea")
SKIP = "skip"


@dataclass(frozen=True)
class Components:
    """The six components as plain callables (mocked in tests; built by src/pipeline_resources.py)."""

    classify: Callable[[str, str], dict[str, Any]]  # (summary, description) -> {"classes": [(c, p)], "components"}
    find_duplicates: Callable[[str, str, str, list[str]], Any]  # (summary, description, mode, exclude) -> C2Output
    detect_gaps: Callable[..., dict[str, Any]]  # (conversation, cls, session_id=) -> {field: FieldState}
    ask: Callable[..., Any]  # (conversation, cls, states, session_id=) -> C5Output
    check_scope: Callable[..., tuple[Any, list[dict]]]  # (summary, description, session_id=) -> (C3Output, chunks)
    compose: Callable[..., Any]  # (conversation, cls, component, states, session_id=) -> C6Output


class StepFailed(Exception):
    pass


def first_line(text: str, limit: int = 120) -> str:
    line = text.strip().split("\n", 1)[0].strip()
    return line if len(line) <= limit else line[:limit].rsplit(" ", 1)[0] + "…"


def short(value: Any, limit: int = 160) -> str:
    return " ".join(str(value).split())[:limit]


def summarize(result: Any) -> str:
    """Compact trace output: field statuses for C4, questions for C5, else the (dumped) result."""
    if isinstance(result, dict) and result and all(hasattr(v, "status") for v in result.values()):
        return short(", ".join(f"{n}: {v.status}" for n, v in result.items()), 300)
    if hasattr(result, "questions"):
        return short(" | ".join(f"[{q.target_field}] {q.question}" for q in result.questions), 300)
    return short(getattr(result, "model_dump", lambda: result)(), 300)


class Pipeline:
    def __init__(self, components: Components) -> None:
        self.c = components

    # ------------------------------------------------------------ user actions

    def new_session(self) -> SessionState:
        return SessionState(session_id=uuid.uuid4().hex[:12])

    def start(self, state: SessionState, text: str) -> SessionState:
        state = state.model_copy(deep=True)
        state.summary = first_line(text)
        state.conversation.append({"role": "user", "content": text.strip()})
        state.chat.append({"role": "user", "content": text.strip()})
        return self._run(state, "classify")

    def confirm_class(self, state: SessionState, cls: str, component: list[str]) -> SessionState:
        state = state.model_copy(deep=True)
        state.ticket_class, state.component = cls, list(component)
        self._event(state, "confirm_class", "user", f"{cls} · {', '.join(component)}", "confirmed")
        return self._run(state, "gather")

    def answer(self, state: SessionState, text: str) -> SessionState:
        state = state.model_copy(deep=True)
        state.chat.append({"role": "user", "content": text.strip()})
        state.pending_questions = []
        if text.strip().lower() == SKIP:
            state.skipped = True
            self._event(state, "skip", "user", "skip", "no more questions")
            return self._run(state, "scope")
        state.conversation.append({"role": "user", "content": text.strip()})
        self._event(state, "answer", "user", text, f"turn {state.question_turns}")
        return self._run(state, "gather")

    def scope_decision(self, state: SessionState, stop: bool) -> SessionState:
        state = state.model_copy(deep=True)
        self._event(state, "scope_decision", "user", "stop" if stop else "continue", "")
        if stop:
            state.stage = "stopped"
            state.chat.append({"role": "assistant", "content": "OK, no ticket needed: see the documentation above."})
            return state
        return self._run(state, "compose")

    def confirm_assumptions(self, state: SessionState, corrections: dict[str, str | None]) -> SessionState:
        """Every assumed field becomes confirmed: with the user's correction, or as is. Re-rendered without an LLM."""
        state = state.model_copy(deep=True)
        cls, ticket = state.ticket_class, state.ticket
        texts = {n: f["value"] for n, f in ticket["fields"].items() if f["status"] in ("confirmed", "assumed")}
        changed = []
        for name, f in ticket["fields"].items():
            if f["status"] != "assumed":
                continue
            corrected = (corrections.get(name) or "").strip()
            value = corrected or f["value"]
            state.field_states[name] = {"status": "confirmed", "value": value, "evidence": [value]}
            texts[name] = value
            if corrected:
                changed.append(name)
                state.conversation.append({"role": "user", "content": f"Correction for {heading(name)}: {corrected}"})
        draft = draft_model(cls).model_validate(
            {
                "title": ticket["title"],
                "labels": ticket["labels"],
                "fields": {f.name: texts.get(f.name) for f in class_fields(cls)},
            }
        )
        state.ticket = render(cls, state.component, state.field_states, draft).model_dump()
        state.stage = "done"
        self._event(state, "confirm_assumptions", "user", f"corrected: {changed or 'none'}", "ticket final")
        state.chat.append({"role": "assistant", "content": "The ticket is final: copy or download it on the right."})
        return state

    def dismiss(self, state: SessionState, key: str) -> SessionState:
        state = state.model_copy(deep=True)
        if key not in state.dismissed:
            state.dismissed.append(key)
            self._event(state, "dismiss", "user", key, "removed from duplicate candidates")
        return state

    def retry(self, state: SessionState) -> SessionState:
        state = state.model_copy(deep=True)
        segment = state.retry_segment
        return self._run(state, segment) if segment else state

    # ------------------------------------------------------------ segments

    def _run(self, state: SessionState, segment: str) -> SessionState:
        state.last_error, state.retry_segment = None, None
        try:
            getattr(self, f"_{segment}")(state)
        except StepFailed:
            state.retry_segment = segment
            failed = state.last_error["step"]
            state.chat.append(
                {"role": "assistant", "content": f"This step failed ({failed}). Try again, or type skip to go on."}
            )
        return state

    def _classify(self, state: SessionState) -> None:
        description = state.conversation[0]["content"]
        c1 = self._step(
            state, "C1", "classifier (baseline)", state.summary, lambda: self.c.classify(state.summary, description)
        )
        state.class_candidates = [(c, round(float(p), 3)) for c, p in c1["classes"]]
        state.component_candidates = list(c1["components"])
        c2 = self._step(
            state,
            "C2 pass 1",
            "duplicate finder (summary-only)",
            state.summary,
            lambda: self.c.find_duplicates(state.summary, "", "summary", []),
        )
        # M6: pass 1 never alerts (short first message; summary-only false alarms were 18-25% on test). Its
        # candidates are shown as related issues; only pass 2 (full description) may raise the alert.
        state.c2_pass1 = {**c2.model_dump(), "alert": False}
        state.stage = "confirm_class"
        state.chat.append(
            {"role": "assistant", "content": "Please confirm the ticket type and component on the right."}
        )

    def _gather(self, state: SessionState) -> None:
        cls = state.ticket_class
        states = self._step(
            state,
            "C4",
            "gap detector",
            f"{len(state.conversation)} turns",
            lambda sid: self.c.detect_gaps(state.conversation, cls, session_id=sid),
            llm_step=True,
        )
        state.field_states = {n: s.model_dump() if hasattr(s, "model_dump") else dict(s) for n, s in states.items()}
        # M6: the component confirmed by the user always wins over C4's reading.
        state.field_states["component"] = {
            "status": "confirmed",
            "value": ", ".join(state.component),
            "evidence": ["confirmed in the UI"],
        }
        # Questions continue only while a REQUIRED field is missing (optional ones never cost the user a turn).
        missing = [
            f.name for f in class_fields(cls) if f.required and state.field_states[f.name]["status"] == "missing"
        ]
        if missing and state.question_turns < MAX_TURNS and not state.skipped:
            out = self._step(
                state,
                "C5",
                "question generator",
                f"missing: {missing}",
                lambda sid: self.c.ask(state.conversation, cls, state.field_states, session_id=sid),
                llm_step=True,
            )
            questions = [q.model_dump() if hasattr(q, "model_dump") else dict(q) for q in out.questions][:MAX_QUESTIONS]
            if questions:
                text = "\n".join(f"{i}. {q['question']}" for i, q in enumerate(questions, 1))
                state.pending_questions = questions
                state.question_turns += 1
                state.conversation.append({"role": "assistant", "content": text})
                state.chat.append({"role": "assistant", "content": text + "\n\n_(Type **skip** to stop questions.)_"})
                state.stage = "asking"
                return
        self._scope(state)

    def _scope(self, state: SessionState) -> None:
        if state.ticket_class not in SCOPE_CLASSES:
            return self._compose(state)
        summary, description = self._request(state)
        try:
            out, chunks = self._step(
                state,
                "C3",
                "scope checker",
                summary,
                lambda sid: self.c.check_scope(summary, description, session_id=sid),
                llm_step=True,
            )
        except StepFailed:  # M7: C3 is advisory; a failed check means "continue to the ticket" (as in M3)
            state.c3 = {"failed": True, "error": state.last_error["message"]}
            state.last_error = None  # the failure stays in the trace, but it does not block the dialogue
            return self._compose(state)
        grounded = out.verdict == "already_supported" and reference_grounded(
            out.doc_reference, [c["text"] for c in chunks]
        )
        state.c3 = {
            **out.model_dump(),
            "grounded": grounded,
            "chunks": [{"chunk_id": c["chunk_id"], "url": c["url"]} for c in chunks],
        }
        if grounded:  # M3: offer a stop only for a grounded already_supported
            state.scope_stop_offered = True
            state.stage = "scope_decision"
            state.chat.append(
                {
                    "role": "assistant",
                    "content": f"This may already be supported: {out.explanation} (`{out.doc_reference}`). "
                    "Stop here, or continue to a ticket?",
                }
            )
            return None
        return self._compose(state)

    def _compose(self, state: SessionState) -> None:
        summary, description = self._request(state)
        c2 = self._step(
            state,
            "C2 pass 2",
            "duplicate finder (full)",
            summary,
            lambda: self.c.find_duplicates(summary, description, "full", list(state.dismissed)),
        )
        state.c2_pass2 = c2.model_dump()
        ticket = self._step(
            state,
            "C6",
            "ticket composer",
            f"{state.ticket_class} · {', '.join(state.component)}",
            lambda sid: self.c.compose(
                state.conversation, state.ticket_class, state.component, state.field_states, session_id=sid
            ),
            llm_step=True,
        )
        state.ticket = ticket.model_dump()
        assumed = [n for n, f in state.ticket["fields"].items() if f["status"] == "assumed"]
        state.stage = "confirm_assumptions" if assumed else "done"
        state.chat.append(
            {
                "role": "assistant",
                "content": "Here is the draft ticket. Please confirm or correct the assumptions on the right."
                if assumed
                else "The ticket is ready: copy or download it on the right.",
            }
        )

    # ------------------------------------------------------------ helpers

    def _request(self, state: SessionState) -> tuple[str, str]:
        """(summary, description) for C3 and C2 pass 2: C4's summary if resolved, else the first line; all user text."""
        s = state.field_states.get("summary") or {}
        summary = s.get("value") if s.get("status") in ("confirmed", "assumed") and s.get("value") else state.summary
        description = "\n\n".join(t["content"] for t in state.conversation if t["role"] == "user")
        return summary, description

    def _step(self, state, step, component, input_summary, fn, llm_step: bool = False):
        """Run one component call: time it, read its LLM calls from the log, record a TraceEvent; raise StepFailed."""
        session_id = f"app|{state.session_id}|{step.replace(' ', '_')}|{len(state.trace)}"
        offset = llm.log_offset() if llm_step else 0
        start = time.perf_counter()
        event = TraceEvent(step=step, component=component, input_summary=short(input_summary))
        try:
            result = fn(session_id) if llm_step else fn()
        except Exception as exc:  # any failure: keep the session, show it, allow retry
            event.error = f"{type(exc).__name__}: {short(exc, 300)}"
            state.last_error = {"step": step, "message": event.error}
            log.warning("[%s] %s failed: %s", state.session_id, step, event.error)
            raise StepFailed(step) from exc
        finally:
            event.latency_ms = round(1000 * (time.perf_counter() - start), 1)
            if llm_step:
                calls = llm.session_calls(session_id, offset)
                event.cost = round(sum(c.get("cost") or 0.0 for c in calls), 6)
                event.cached = all(c.get("cached") for c in calls) if calls else None
                event.llm_calls = len(calls)
            state.trace.append(event)
        event.output_summary = summarize(result)
        log.info("[%s] %s %.0f ms $%.5f", state.session_id, step, event.latency_ms, event.cost)
        return result

    def _event(self, state: SessionState, step: str, component: str, inp: str, out: str) -> None:
        state.trace.append(TraceEvent(step=step, component=component, input_summary=short(inp), output_summary=out))
        log.info("[%s] %s: %s", state.session_id, step, inp)
