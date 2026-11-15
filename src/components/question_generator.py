"""C5 question generator: missing fields + conversation -> at most 2 clarifying questions, each with a target field.

    out = generate(conversation, "bug", states)   # states: {field: {"status": ..., "value": ...}} for the class fields

Only class fields are asked about (summary comes from the first message, component from C1). Fields with status
"unknown" are passed as a do-not-ask list. One LLM call (role "generator").
"""

from __future__ import annotations

from typing import Any

from src import llm
from src.prompting import Prompt, load_prompt, render_conversation
from src.schemas.c5 import C5Output
from src.schemas.ticket_fields import class_fields, render_fields

MAX_QUESTIONS = 2  # shown per turn by the pipeline; the eval measures compliance
MAX_TOKENS = 600  # caps a runaway generation


def field_lists(cls: str, states: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
    """(missing, provided, unknown) blocks for the prompt; missing fields are listed required-first."""
    defs = sorted(class_fields(cls), key=lambda f: not f.required)
    status = {f.name: (states.get(f.name) or {}).get("status", "missing") for f in defs}
    missing = render_fields([f for f in defs if status[f.name] == "missing"])
    provided = [
        f"- {f.name}: {' '.join(str(states[f.name].get('value') or '').split())[:200]}"
        for f in defs
        if status[f.name] in ("confirmed", "assumed")
    ]
    unknown = [f"- {f.name}" for f in defs if status[f.name] == "unknown"]
    return missing or "(none)", "\n".join(provided) or "(none)", "\n".join(unknown) or "(none)"


def build_messages(
    prompt: Prompt, conversation: list[dict[str, str]], cls: str, states: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    missing, provided, unknown = field_lists(cls, states)
    user = prompt.render(
        "user", conversation=render_conversation(conversation), missing=missing, provided=provided, unknown=unknown
    )
    return [{"role": "system", "content": prompt.render("system", cls=cls)}, {"role": "user", "content": user}]


def generate(
    conversation: list[dict[str, str]],
    cls: str,
    states: dict[str, dict[str, Any]],
    *,
    session_id: str | None = None,
    prompt: Prompt | None = None,
) -> C5Output:
    prompt = prompt or load_prompt("c5_questions")
    return llm.complete(
        build_messages(prompt, conversation, cls, states),
        role="generator",
        component="c5_questions",
        session_id=session_id,
        schema=C5Output,
        max_tokens=MAX_TOKENS,
    )
