"""C4 gap detector: conversation + ticket class -> status of every field (confirmed / assumed / missing / unknown).

    states = detect(conversation, "bug")     # {"steps_to_reproduce": FieldState(status="missing", ...), ...}

`conversation` is a list of {"role": "user" | "assistant", "content": str}. One LLM call (role "generator") with a
per-class output model that has exactly the class's fields (src/schemas/c4.py).
"""

from __future__ import annotations

from src import llm
from src.prompting import Prompt, load_prompt, render_conversation
from src.schemas.c4 import FieldState, c4_model
from src.schemas.ticket_fields import class_description, fields_for, render_fields

MAX_TOKENS = 3000  # caps a runaway generation (seen once in the ablation extraction: 131k tokens)


def build_messages(prompt: Prompt, conversation: list[dict[str, str]], cls: str) -> list[dict[str, str]]:
    system = prompt.render(
        "system",
        cls=cls,
        class_description=class_description(cls),
        fields=render_fields(fields_for(cls)),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt.render("user", conversation=render_conversation(conversation))},
    ]


def detect(
    conversation: list[dict[str, str]], cls: str, *, session_id: str | None = None, prompt: Prompt | None = None
) -> dict[str, FieldState]:
    prompt = prompt or load_prompt("c4_gap")
    out = llm.complete(
        build_messages(prompt, conversation, cls),
        role="generator",
        component="c4_gap",
        session_id=session_id,
        schema=c4_model(cls),
        max_tokens=MAX_TOKENS,
    )
    return {name: getattr(out, name) for name in type(out).model_fields}
