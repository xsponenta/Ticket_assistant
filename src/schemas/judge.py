"""LLM-as-judge output (AGENTS.md: binary questions, reasoning before the verdict)."""

from __future__ import annotations

from pydantic import BaseModel


class BinaryJudgement(BaseModel):
    reasoning: str
    verdict: bool
