"""C1 classifier I/O (AGENTS.md: component I/O = pydantic models in src/schemas/)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TicketClass = Literal["bug", "feature", "task", "idea"]

# Top-15 Jira components of the TRAIN split (decision in reports/04_modeling.md, C1) + "other".
# They cover 96% of train issues; tests/test_c1.py checks the list against the data.
TOP_COMPONENTS = [
    "SQL",
    "Spark Core",
    "PySpark",
    "Connect",
    "Build",
    "Structured Streaming",
    "Tests",
    "Documentation",
    "Kubernetes",
    "Project Infra",
    "ML",
    "Web UI",
    "Pandas API on Spark",
    "SparkR",
    "YARN",
]
COMPONENTS = [*TOP_COMPONENTS, "other"]
Component = Literal[
    "SQL",
    "Spark Core",
    "PySpark",
    "Connect",
    "Build",
    "Structured Streaming",
    "Tests",
    "Documentation",
    "Kubernetes",
    "Project Infra",
    "ML",
    "Web UI",
    "Pandas API on Spark",
    "SparkR",
    "YARN",
    "other",
]


class C1Input(BaseModel):
    summary: str
    description: str = ""


class C1Output(BaseModel):
    """rationale first (the model reasons before labelling); component = 1–3 components, most likely first."""

    model_config = ConfigDict(populate_by_name=True)
    rationale: str
    label: TicketClass = Field(alias="class")
    component: list[Component] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
