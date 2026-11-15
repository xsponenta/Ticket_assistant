"""C6 ticket composer: class, component, C4 field states and the conversation -> a Jira-ready ticket.

    ticket = compose(conversation, "bug", ["SQL"], states)   # C6Output: title, jira_type, ..., body_markdown, fields

One LLM call (role "generator") writes the title, labels and a text per field (C6Draft). render() assembles the
ticket deterministically, so the hard rules hold by construction: jira_type from ticket_types.yaml, the confirmed
component, "Unknown (reporter)" for unknown fields, "_Not provided_" for missing required fields, the "Assumptions to
confirm" section for every assumed field (M4), and no priority or fix version.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src import llm
from src.prompting import Prompt, load_prompt, render_conversation
from src.schemas.c6 import MISSING_TEXT, UNKNOWN_TEXT, C6Output, RenderedField, draft_model
from src.schemas.ticket_fields import class_description, class_fields, heading, render_fields, submit_as

MAX_TOKENS = 2000
WRITTEN = ("confirmed", "assumed")


def render_states(cls: str, states: dict[str, dict[str, Any]]) -> str:
    lines = []
    for f in class_fields(cls):
        s = states.get(f.name) or {}
        value = " ".join(str(s.get("value") or "").split())[:300]
        lines.append(f"- {f.name}: {s.get('status', 'missing')}" + (f" — {value}" if value else ""))
    return "\n".join(lines)


def build_messages(
    prompt: Prompt, conversation: list[dict[str, str]], cls: str, component: list[str], states: dict
) -> list[dict[str, str]]:
    system = prompt.render(
        "system",
        cls=cls,
        class_description=class_description(cls),
        fields=render_fields(class_fields(cls)),
        states=render_states(cls, states),
    )
    user = prompt.render(
        "user", component=", ".join(component) or "(none)", conversation=render_conversation(conversation)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def render(cls: str, component: list[str], states: dict[str, dict[str, Any]], draft: BaseModel) -> C6Output:
    """Deterministic assembly of the ticket from the draft and the field states."""
    fields: dict[str, RenderedField] = {}
    for f in class_fields(cls):
        status = (states.get(f.name) or {}).get("status", "missing")
        text = ""
        if status in WRITTEN:
            text = (getattr(draft.fields, f.name) or (states[f.name].get("value") or "")).strip()
        if status in WRITTEN and not text:
            status = "missing"  # nothing to show: treat as not provided
        fields[f.name] = RenderedField(status=status, value=UNKNOWN_TEXT if status == "unknown" else (text or None))
    labels = list(dict.fromkeys(draft.labels))
    jira_type = submit_as(cls)
    header = f"**Type:** {jira_type} · **Component:** {', '.join(component) or '—'}"
    sections = [header + (f" · **Labels:** {', '.join(labels)}" if labels else "")]
    for f in class_fields(cls):
        rendered = fields[f.name]
        if rendered.status == "missing" and not f.required:
            continue
        text = rendered.value or MISSING_TEXT
        if rendered.status == "assumed":
            text += "\n\n_(assumed — see Assumptions to confirm)_"
        sections.append(f"### {heading(f.name)}\n\n{text}")
    assumed = [f.name for f in class_fields(cls) if fields[f.name].status == "assumed"]
    if assumed:
        items = [f"- **{heading(n)}:** {' '.join((fields[n].value or '').split())}" for n in assumed]
        sections.append("### Assumptions to confirm\n\n" + "\n".join(items))
    return C6Output(
        title=" ".join(draft.title.split()),
        jira_type=jira_type,
        component=component,
        labels=labels,
        body_markdown="\n\n".join(sections),
        fields=fields,
    )


def compose(
    conversation: list[dict[str, str]],
    cls: str,
    component: list[str],
    states: dict[str, dict[str, Any]],
    *,
    session_id: str | None = None,
    prompt: Prompt | None = None,
) -> C6Output:
    prompt = prompt or load_prompt("c6_compose")
    draft = llm.complete(
        build_messages(prompt, conversation, cls, component, states),
        role="generator",
        component="c6_compose",
        session_id=session_id,
        schema=draft_model(cls),
        max_tokens=MAX_TOKENS,
    )
    return render(cls, component, states, draft)
