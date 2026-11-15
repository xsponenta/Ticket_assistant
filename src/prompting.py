"""Prompt files: src/prompts/<name>.md with a front-matter `version` and `## section` blocks (AGENTS.md).

prompt = load_prompt("c1_classifier")
prompt.version                      # "c1_classifier/v1"
prompt.render("user", ticket="…")   # $variables are filled with string.Template (safe_substitute)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    version: str
    sections: dict[str, str]

    def render(self, section: str, **values: str) -> str:
        return Template(self.sections[section]).safe_substitute(values)


def load_prompt(name: str, prompts_dir: Path = PROMPTS_DIR) -> Prompt:
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    header = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not header:
        raise ValueError(f"{name}.md has no front-matter header")
    version = re.search(r"^version:\s*(\S+)", header.group(1), re.M)
    if not version:
        raise ValueError(f"{name}.md has no `version:` in its header")
    body = text[header.end() :]
    sections = {m.group(1): m.group(2).strip() for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", body, re.S | re.M)}
    return Prompt(version.group(1), sections)
