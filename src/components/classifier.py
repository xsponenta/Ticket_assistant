"""C1 classifier, LLM variant: class + component from the ticket text, with dynamic few-shot examples from TRAIN.

    index = FewShotIndex(train_df, mode="full")
    out = classify(summary, description, mode="full", k=2, index=index)   # -> C1Output

- Class definitions come from src/schemas/ticket_types.yaml (single source of truth).
- k = number of nearest TRAIN examples PER CLASS (TF-IDF cosine), so k=2 shows 8 examples.
- One LLM call per ticket via src/llm.py (role "generator": model, temperature and reasoning from config.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer

from src import llm
from src.prompting import Prompt, load_prompt
from src.schemas.c1 import COMPONENTS, TOP_COMPONENTS, C1Output

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ["bug", "feature", "task", "idea"]
MODES = ("full", "summary")
DESC_CHARS = 1500  # description chars in mode "full" (same as the bake-off and the human-ceiling tool)
EXAMPLE_DESC_CHARS = 400  # description chars per few-shot example (keeps the prompt short)


def input_text(summary: str, description: str, mode: str, desc_chars: int = DESC_CHARS) -> str:
    """'full' = summary + first `desc_chars` of the description; 'summary' = summary only."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode == "summary" or not (description or "").strip():
        return summary.strip()
    return f"{summary.strip()}\n\n{description[:desc_chars].strip()}"


def map_components(components: list[str]) -> set[str]:
    """Jira components → top-15 names or 'other' (an issue without components counts as 'other')."""
    mapped = {c if c in TOP_COMPONENTS else "other" for c in components}
    return mapped or {"other"}


def class_definitions(path: Path = ROOT / "src" / "schemas" / "ticket_types.yaml") -> str:
    types = yaml.safe_load(path.read_text())["classes"]
    return "\n".join(
        f"- {c}: {types[c]['description']} (Jira types: {', '.join(types[c]['jira_issue_types'])})" for c in CLASSES
    )


@dataclass(frozen=True)
class Example:
    key: str
    label: str
    components: list[str]
    text: str
    similarity: float


class FewShotIndex:
    """TF-IDF (word 1–2) index over TRAIN issues for one input mode."""

    def __init__(self, train: pd.DataFrame, mode: str) -> None:
        self.mode = mode
        self.keys = list(train.key)
        self.labels = list(train.target_class)
        self.components = [sorted(map_components(list(c))) for c in train.components]
        self.texts = [
            input_text(s, d, mode, EXAMPLE_DESC_CHARS) for s, d in zip(train.summary, train.description_md, strict=True)
        ]
        full_texts = [input_text(s, d, mode) for s, d in zip(train.summary, train.description_md, strict=True)]
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(full_texts)

    def neighbours(self, text: str, k: int) -> list[Example]:
        """The k most similar TRAIN issues of EACH class, most similar first."""
        if k <= 0:
            return []
        sims = (self.matrix @ self.vectorizer.transform([text]).T).toarray().ravel()
        picked: list[int] = []
        for cls in CLASSES:
            idx = [i for i, label in enumerate(self.labels) if label == cls]
            picked += sorted(idx, key=lambda i: (-sims[i], self.keys[i]))[:k]
        picked.sort(key=lambda i: (-sims[i], self.keys[i]))
        return [
            Example(self.keys[i], self.labels[i], self.components[i], self.texts[i], float(sims[i])) for i in picked
        ]


def build_messages(prompt: Prompt, ticket: str, examples: list[Example]) -> list[dict[str, str]]:
    system = prompt.render("system", class_definitions=class_definitions(), components=", ".join(COMPONENTS))
    rendered = "\n\n".join(
        prompt.render("example", label=e.label, components=", ".join(e.components), ticket=e.text) for e in examples
    )
    examples_block = f"Labelled examples of similar Spark tickets:\n\n{rendered}" if examples else ""
    user = prompt.render("user", examples=examples_block, ticket=ticket).strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def classify(
    summary: str,
    description: str,
    *,
    mode: str,
    k: int,
    index: FewShotIndex | None,
    session_id: str | None = None,
    prompt: Prompt | None = None,
) -> C1Output:
    prompt = prompt or load_prompt("c1_classifier")
    ticket = input_text(summary, description, mode)
    examples = index.neighbours(ticket, k) if (index is not None and k) else []
    return llm.complete(
        build_messages(prompt, ticket, examples),
        role="generator",
        component="c1_classifier",
        session_id=session_id,
        schema=C1Output,
    )
