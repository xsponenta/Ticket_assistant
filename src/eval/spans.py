"""Verbatim-quote matching: find a quoted passage in a text (exact, else whitespace-flexible) and delete spans.

Used to build the C4/C5 ablation set (delete a field's passages) and to check that C4's evidence quotes are grounded.
"""

from __future__ import annotations

import re

MIN_QUOTE_CHARS = 3


def find_spans(quote: str, text: str) -> list[tuple[int, int]]:
    """All non-overlapping (start, end) occurrences of `quote` in `text`; whitespace runs may differ."""
    quote = (quote or "").strip()
    if len(quote) < MIN_QUOTE_CHARS:
        return []
    spans = [(m.start(), m.end()) for m in re.finditer(re.escape(quote), text)]
    if spans:
        return spans
    pattern = r"\s+".join(re.escape(token) for token in quote.split())
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def quote_grounded(quote: str, text: str) -> bool:
    return bool(find_spans(quote, text))


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def overlaps(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> bool:
    return any(s1 < e2 and s2 < e1 for s1, e1 in a for s2, e2 in b)


def delete_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Remove the spans, then tidy whitespace (trailing spaces, 3+ newlines, doubled spaces)."""
    out, last = [], 0
    for start, end in merge_spans(spans):
        out.append(text[last:start])
        last = end
    out.append(text[last:])
    result = re.sub(r"[ \t]+\n", "\n", "".join(out))
    result = re.sub(r"\n{3,}", "\n\n", result)
    return re.sub(r"(?<=\S) {2,}(?=\S)", " ", result).strip()


# ---------------------------------------------------------------- grounding of generated text (C6)

STOPWORDS = set(
    """a an the and or but if of to in on at by for with from into is are was were be been being it its this that these
    those as not no can could should would will we you they i he she our your their there here which who what when where
    how do does did have has had also just only all any some such than too very via per so then while given""".split()
)
TOKEN_RE = re.compile(r"[a-z0-9_]+")
RISKY_PATTERNS = [
    re.compile(r"`([^`\s]{2,80})`"),  # backticked identifiers / config / flags (no whitespace: never prose)
    re.compile(r"\bspark\.[A-Za-z0-9_.]*[A-Za-z0-9_]"),  # config keys
    re.compile(r"\b\d+(?:\.\d+)+\b"),  # versions such as 3.5.1
    re.compile(r"(?<![\w.])\d{2,}(?![\w.])"),  # numbers with 2+ digits
    re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),  # snake_case
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),  # CamelCase
    re.compile(r"\b[A-Za-z_]\w*\.\w+(?=\()"),  # obj.method(
]


def content_words(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def content_word_share(value: str, source: str) -> float:
    """Share of the value's content words that occur in the source (1.0 for a value without content words)."""
    words = content_words(value)
    vocab = set(TOKEN_RE.findall(source.lower()))
    return sum(w in vocab for w in words) / len(words) if words else 1.0


def risky_tokens(text: str) -> set[str]:
    """Tokens a composer could invent: versions, numbers, config keys, code identifiers, backticked spans."""
    text = re.sub(r"```\w*", "\n", text)  # fence markers would pair up with inline backticks
    found = set()
    for pattern in RISKY_PATTERNS:
        for m in pattern.finditer(text):
            token = (m.group(1) if m.groups() else m.group(0)).strip()
            if token:
                found.add(token)
    return found


def invented_tokens(text: str, source: str, ignore: set[str] = frozenset()) -> list[str]:
    """Risky tokens of `text` that do not occur in `source` (case-insensitive, whitespace-normalised)."""
    norm = " ".join(source.lower().split())
    return sorted(t for t in risky_tokens(text) - ignore if " ".join(t.lower().split()) not in norm)
