"""Simulated user for the end-to-end evaluation (role "simulator": qwen3.5-27b, reasoning off; config.yaml).

    opener, leaks, attempts = make_opener(summary, description, session_prefix)
    user = SimulatedUser(hidden_ticket_text, session_prefix)      # answer_fn for src/pipeline_driver.run_dialogue

The opener is written from the ticket SUMMARY only and checked deterministically for leaks (opener_leaks); it is
regenerated once with the reasons as feedback. The simulated user answers only what is asked, from the hidden
ticket, and says "I don't know" otherwise (prompt src/prompts/sim_user.md). Its turns are kept for the
behaviour checks (sentences per answer, honesty, AI mentions).
"""

from __future__ import annotations

import re
from typing import Any

from src import llm
from src.eval.spans import GENERIC_TERMS, content_words, risky_tokens
from src.prompting import load_prompt, render_conversation

MAX_OPENER_WORDS = 20
ERROR_RE = re.compile(r"\b[A-Za-z]+(?:Exception|Error)\b|(?i:traceback|stack ?trace)")
DONT_KNOW_RE = re.compile(
    r"\b(?:i\s+(?:do\s*n[o']t|don’t)\s+know|not\s+sure|no\s+idea|unsure|not\s+available|"
    r"(?:do\s*n[o']t|don’t)\s+have\s+(?:that|this|those|the|any|a|an|specific|exact)\b|"
    r"can(?:'|no)t\s+(?:say|tell|provide|share))",
    re.I,
)
META_RE = re.compile(r"\b(?:the|my|this|that)\s+(?:ticket|jira(?:\s+issue)?|notes?|description|document)\b", re.I)
AI_RE = re.compile(r"\bas an ai\b|\bi am an ai\b|\bi'm an ai\b|language model|\bchatbot\b|\bsimulat(?:ion|ed)\b", re.I)


def ngrams(words: list[str], n: int = 4) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def opener_leaks(opener: str, summary: str, description: str) -> list[str]:
    """Reasons the opener reveals more than a vague first message should (empty list = clean)."""
    reasons = []
    if len(opener.split()) > MAX_OPENER_WORDS:
        reasons.append(f"{len(opener.split())} words (max {MAX_OPENER_WORDS})")
    specific = risky_tokens(opener) - GENERIC_TERMS
    if specific:
        reasons.append(f"specific tokens {sorted(specific)}")
    if ERROR_RE.search(opener):
        reasons.append("error text")
    copied = ngrams(content_words(opener)) & ngrams(content_words(description)) - ngrams(content_words(summary))
    if copied:
        reasons.append(f"copies the description: '{' '.join(sorted(copied)[0])}'")
    return reasons


def clean(text: str) -> str:
    line = next((ln for ln in text.strip().splitlines() if ln.strip()), "")
    return line.strip().strip('"“”').strip()


def make_opener(summary: str, description: str, session_prefix: str) -> tuple[str, list[str], int]:
    """(opener, leak reasons of the opener used, attempts); one regeneration with the reasons as feedback."""
    prompt = load_prompt("sim_opener")
    feedback, opener, reasons = "", "", []
    for attempt in (1, 2):
        messages = [
            {"role": "system", "content": prompt.render("system")},
            {"role": "user", "content": prompt.render("user", summary=summary.strip(), feedback=feedback)},
        ]
        opener = clean(
            llm.complete(
                messages,
                role="simulator",
                component="sim_opener",
                session_id=f"{session_prefix}|opener|{attempt}",
                max_tokens=80,
            )
        )
        reasons = opener_leaks(opener, summary, description)
        if not reasons:
            return opener, [], attempt
        feedback = f"\nYour previous sentence was rejected ({'; '.join(reasons)}). Write a vaguer one."
    return opener, reasons, 2


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def sentences(text: str) -> int:
    return len(split_sentences(text))


def dont_know_only(text: str) -> bool:
    """Every sentence is a "don't know" (a partial answer such as "I don't know the version, but I built it with
    Maven" is not a refusal)."""
    parts = split_sentences(text)
    return bool(parts) and all(DONT_KNOW_RE.search(p) and not re.search(r"\bbut\b", p, re.I) for p in parts)


class SimulatedUser:
    """answer_fn(state, questions) -> str for run_dialogue; keeps every turn for the behaviour checks."""

    def __init__(self, ticket_text: str, session_prefix: str) -> None:
        self.ticket, self.prefix = ticket_text, session_prefix
        self.turns: list[dict[str, Any]] = []
        self.prompt = load_prompt("sim_user")

    def __call__(self, state: Any, questions: list[dict[str, str]]) -> str:
        messages = [
            {"role": "system", "content": self.prompt.render("system", ticket=self.ticket)},
            {
                "role": "user",
                "content": self.prompt.render("user", conversation=render_conversation(state.conversation)),
            },
        ]
        answer = " ".join(
            llm.complete(
                messages,
                role="simulator",
                component="sim_user",
                session_id=f"{self.prefix}|turn{len(self.turns) + 1}",
                max_tokens=200,
            ).split()
        )
        if answer.strip().lower().strip(".") == "skip":  # never stop the dialogue on the simulator's behalf
            answer = "I don't know."
        self.turns.append({"questions": questions, "answer": answer})
        return answer
