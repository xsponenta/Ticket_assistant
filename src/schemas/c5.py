"""C5 question generator I/O. The list is not capped here: "at most 2 per turn" is measured by eval/eval_c5.py,
and the pipeline shows only the first 2."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    target_field: str
    question: str


class C5Output(BaseModel):
    questions: list[Question] = Field(default_factory=list)
