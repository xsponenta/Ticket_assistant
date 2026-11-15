"""C3 scope checker I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Verbatim from the labelling guidelines in src/data/label_cli.py (tests/test_c3.py checks they are identical).
SCOPE_LABELS = {
    "already_supported": "doable today with an existing API/config",
    "needs_development": "reasonable for Spark but needs code changes",
    "out_of_scope": "better as a third-party project, contradicts Spark design, or another product",
    "insufficient_info": "cannot decide",
}
Verdict = Literal["already_supported", "needs_development", "out_of_scope", "insufficient_info"]


class C3Output(BaseModel):
    """rationale first; explanation is user-facing (≤ 2 sentences); doc_reference required when already supported."""

    rationale: str
    verdict: Verdict
    cited_chunk_ids: list[str] = Field(default_factory=list, max_length=8)
    explanation: str
    doc_reference: str | None = None

    @model_validator(mode="after")
    def reference_when_supported(self) -> C3Output:
        if self.verdict == "already_supported" and not (self.doc_reference or "").strip():
            raise ValueError(
                "doc_reference (the concrete API/config name) is required when verdict is already_supported"
            )
        return self
