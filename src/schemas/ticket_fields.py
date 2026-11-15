"""Ticket fields per class, read from src/schemas/ticket_types.yaml (the single source of truth)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

TYPES_PATH = Path(__file__).resolve().parent / "ticket_types.yaml"
CLASSES = ("bug", "feature", "task", "idea")


@dataclass(frozen=True)
class FieldDef:
    name: str
    required: bool
    description: str
    example: str
    common: bool


@lru_cache(maxsize=1)
def _types() -> dict:
    return yaml.safe_load(TYPES_PATH.read_text(encoding="utf-8"))


def _defs(raw: list[dict], common: bool) -> list[FieldDef]:
    return [
        FieldDef(f["name"], bool(f["required"]), " ".join(f["description"].split()), str(f["example"]).strip(), common)
        for f in raw
    ]


def class_fields(cls: str) -> list[FieldDef]:
    """The class-specific fields (required and optional), in YAML order."""
    if cls not in CLASSES:
        raise ValueError(f"unknown class {cls!r}")
    return _defs(_types()["classes"][cls]["fields"], common=False)


def fields_for(cls: str) -> list[FieldDef]:
    """Common fields (summary, component, labels) + the class fields."""
    return _defs(_types()["common_fields"], common=True) + class_fields(cls)


def class_description(cls: str) -> str:
    return " ".join(_types()["classes"][cls]["description"].split())


def submit_as(cls: str) -> str:
    """Jira issue type a new ticket of this class is filed as (ticket_types.yaml `submit_as`)."""
    return _types()["classes"][cls]["submit_as"]


def heading(name: str) -> str:
    """Human-readable section heading for a field name (steps_to_reproduce -> Steps to reproduce)."""
    return name.replace("_", " ").capitalize()


def render_fields(fields: list[FieldDef]) -> str:
    """Bullet list for prompts: name (required/optional): description. Example: …"""
    return "\n".join(
        f"- {f.name} ({'required' if f.required else 'optional'}): {f.description} "
        f"Example: {' '.join(f.example.split())}"
        for f in fields
    )
