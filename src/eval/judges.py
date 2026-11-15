"""LLM judges used by the evals (role "judge": temperature 0, different provider than the generator) and
deterministic grounding checks."""

from __future__ import annotations

import re

from src import llm
from src.prompting import load_prompt
from src.schemas.c3 import C3Output
from src.schemas.judge import BinaryJudgement

DESC_CHARS = 1500


def judge_relevance(
    summary: str, description: str, chunk: dict, session_id: str | None = None, use_cache: bool = True
) -> BinaryJudgement:
    prompt = load_prompt("judge_chunk_relevance")
    messages = [
        {"role": "system", "content": prompt.sections["system"]},
        {
            "role": "user",
            "content": prompt.render(
                "user",
                summary=summary,
                description=(description or "")[:DESC_CHARS] or "(none)",
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
            ),
        },
    ]
    return llm.complete(
        messages,
        role="judge",
        component="judge_chunk_relevance",
        session_id=session_id,
        schema=BinaryJudgement,
        use_cache=use_cache,
    )


def judge_citation(
    summary: str, output: C3Output | dict, chunk: dict, session_id: str | None = None, use_cache: bool = True
) -> BinaryJudgement:
    out = output if isinstance(output, dict) else output.model_dump()
    prompt = load_prompt("judge_citation_support")
    messages = [
        {"role": "system", "content": prompt.sections["system"]},
        {
            "role": "user",
            "content": prompt.render(
                "user",
                summary=summary,
                verdict=out["verdict"],
                explanation=out["explanation"],
                doc_reference=out.get("doc_reference") or "(none)",
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
            ),
        },
    ]
    return llm.complete(
        messages,
        role="judge",
        component="judge_citation_support",
        session_id=session_id,
        schema=BinaryJudgement,
        use_cache=use_cache,
    )


def _normalise(text: str) -> str:
    text = re.sub(r"[`'\"()\[\]]", " ", text.lower())
    return " ".join(re.sub(r"[._/\\-]+", " ", text).split())


def reference_grounded(reference: str | None, chunk_texts: list[str]) -> bool:
    """Every part of the doc_reference (split on , ; / ' or ' ' and ') occurs in at least one retrieved chunk,
    case-insensitive, ignoring backticks, quotes, brackets and the separators . _ / - ."""
    if not reference or not reference.strip():
        return False
    parts = [p for p in re.split(r",|;| or | and |\s/\s", reference) if p.strip()]
    texts = [_normalise(t) for t in chunk_texts]
    return all(any(_normalise(p) in t for t in texts) for p in parts if _normalise(p))
