"""C6 ticket composer I/O.

The LLM writes only text (`C6Draft`: title, labels, one text per class field). Code assembles the ticket (`C6Output`):
jira_type from ticket_types.yaml, the confirmed component, "Unknown (reporter)" for unknown fields, "_Not provided_"
for missing ones, and the "Assumptions to confirm" section (M4).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

from src.schemas.ticket_fields import class_fields

Label = Literal["correctness", "data-loss"]
UNKNOWN_TEXT = "Unknown (reporter)"
MISSING_TEXT = "_Not provided_"


@lru_cache(maxsize=8)
def draft_model(cls: str) -> type[BaseModel]:
    """All keys required (structured output may omit keys that have defaults); text is null for missing/unknown."""
    texts = create_model(
        f"C6Fields_{cls}",
        __config__=ConfigDict(extra="forbid"),
        **{f.name: (str | None, ...) for f in class_fields(cls)},
    )
    return create_model(
        f"C6Draft_{cls}",
        __config__=ConfigDict(extra="forbid"),
        title=(str, ...),
        labels=(list[Label], ...),
        fields=(texts, ...),
    )


class RenderedField(BaseModel):
    status: Literal["confirmed", "assumed", "missing", "unknown"]
    value: str | None


class C6Output(BaseModel):
    title: str
    jira_type: str
    component: list[str]
    labels: list[Label]
    body_markdown: str
    fields: dict[str, RenderedField]
