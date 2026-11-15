"""C4 gap detector I/O, and the gold-extraction model used to build the C4/C5 ablation set.

Statuses (rubric in src/prompts/c4_gap.md):
- confirmed: stated by the user (evidence = verbatim quote);
- assumed:   inferred from an indirect cue (evidence = the cue);
- missing:   not stated (also "I don't know" volunteered before anyone asked);
- unknown:   the user was asked and, in a later turn, said they don't know / can't provide it. Counts as resolved:
             C5 never asks about it, C6 renders it as "Unknown (reporter)".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model, model_validator

from src.schemas.ticket_fields import class_fields, fields_for

Status = Literal["confirmed", "assumed", "missing", "unknown"]
RESOLVED = ("confirmed", "assumed", "unknown")


class FieldState(BaseModel):
    """All keys required, evidence first: with defaults, structured output let the model omit the evidence."""

    evidence: list[str]
    status: Status
    value: str | None


@lru_cache(maxsize=8)
def c4_model(cls: str) -> type[BaseModel]:
    """Output model with exactly the class's fields (common + class); a missing or extra field fails validation."""
    fields = {f.name: (FieldState, ...) for f in fields_for(cls)}
    return create_model(f"C4Output_{cls}", __config__=ConfigDict(extra="forbid"), **fields)


class ExtractedField(BaseModel):
    """Gold extraction of one field from an original ticket (no `unknown`: nobody has asked yet).

    All keys are required and `quotes` comes first: with defaults, structured output let the model omit the quotes
    (23% of tickets failed validation with ablation_extract/v1)."""

    quotes: list[str]
    status: Literal["confirmed", "assumed", "missing"]
    value: str | None

    @model_validator(mode="after")
    def quotes_when_present(self) -> ExtractedField:
        if self.status != "missing" and not [q for q in self.quotes if q.strip()]:
            raise ValueError("a confirmed or assumed field needs at least one verbatim quote from the text")
        return self


@lru_cache(maxsize=8)
def extraction_model(cls: str) -> type[BaseModel]:
    fields = {f.name: (ExtractedField, ...) for f in class_fields(cls)}
    return create_model(f"Extraction_{cls}", __config__=ConfigDict(extra="forbid"), **fields)
