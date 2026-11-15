"""C2 duplicate finder I/O."""

from __future__ import annotations

from pydantic import BaseModel, Field

JIRA_BROWSE = "https://issues.apache.org/jira/browse/"


class DuplicateCandidate(BaseModel):
    key: str
    summary: str
    url: str
    score: float


class C2Output(BaseModel):
    candidates: list[DuplicateCandidate] = Field(max_length=5)
    alert: bool  # "possible duplicate": alert_score >= the threshold chosen on train+val
    alert_score: float
