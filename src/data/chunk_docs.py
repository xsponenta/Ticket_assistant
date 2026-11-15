"""Chunk the Spark docs (data/raw/docs/**/*.md) for retrieval -> data/processed/doc_chunks.jsonl.

Per page: drop the Jekyll front matter (keep `title`), turn {% highlight %} blocks into ``` fences, drop
include_example / other Liquid tags, kramdown TOC markers and bare <div> wrapper lines, fill in {{site.*}} variables.
Then split on Markdown headers of any level (outside code) and pack sections into chunks of ~300–500 tokens
(cl100k_base, counted on the final chunk text). Each chunk starts with "page title > header path".

Usage:
    python src/data/chunk_docs.py
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from dataclasses import dataclass
from pathlib import Path

import tiktoken

from prep_stats import PROCESSED, RAW, update_stats

DOCS = RAW / "docs"
OUT = PROCESSED / "doc_chunks.jsonl"
MIN_TOKENS, MAX_TOKENS = 300, 500
SKIP_PAGES = {"README", "404"}  # build instructions for the docs site / error page, not user documentation
# Values from docs/_config.yml of the downloaded release (v4.3.0).
SITE_VARS = {
    "SPARK_VERSION": "4.3.0",
    "SPARK_VERSION_SHORT": "4.3.0",
    "SCALA_BINARY_VERSION": "2.13",
    "SCALA_VERSION": "2.13.18",
    "SPARK_GITHUB_URL": "https://github.com/apache/spark",
    "SPARK_ISSUE_TRACKER_URL": "https://issues.apache.org/jira/browse/SPARK",
}

ENC = tiktoken.get_encoding("cl100k_base")
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
HIGHLIGHT_RE = re.compile(r"\{%\s*highlight\s+(\w+)[^%]*%\}")
ENDHIGHLIGHT_RE = re.compile(r"\{%\s*endhighlight\s*%\}")
COMMENT_RE = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
LIQUID_LINE_RE = re.compile(r"^[ \t]*\{%.*?%\}[ \t]*\n", re.M)  # whole-line tags incl. include_example
LIQUID_TAG_RE = re.compile(r"\{%.*?%\}")
SITE_VAR_RE = re.compile(r"\{\{\s*site\.(\w+)\s*\}\}")
DROP_LINE_RE = re.compile(
    r"^[ \t]*(?:\*[ \t]+This will become a table of contents.*|\{:[^}]*\}|</?div[^>]*>)[ \t]*\n", re.M | re.I
)
HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Fence line (also inside blockquotes: "> ```scala"); not inline code that closes on the same line ("```SELECT 1```").
FENCE_RE = re.compile(r"^\s*(?:>\s*)*(```|~~~)(?!.*(?:```|~~~))")


def n_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def preprocess(raw: str, version: str) -> tuple[str, str]:
    """Return (title, cleaned Markdown body)."""
    title = ""
    m = FRONT_MATTER_RE.match(raw)
    if m:
        t = TITLE_RE.search(m.group(1))
        title = t.group(1).strip("\"'") if t else ""
        raw = raw[m.end() :]
    body = COMMENT_RE.sub("", raw)
    body = HIGHLIGHT_RE.sub(lambda h: f"```{h.group(1)}", body)
    body = ENDHIGHLIGHT_RE.sub("```", body)
    body = LIQUID_LINE_RE.sub("", body)
    body = LIQUID_TAG_RE.sub("", body)
    body = SITE_VAR_RE.sub(
        lambda v: SITE_VARS.get(v.group(1), version if "VERSION" in v.group(1) else v.group(0)), body
    )
    body = DROP_LINE_RE.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body


@dataclass
class Section:
    path: list[str]  # header path, e.g. ["Basic Concepts", "Handling Late Data"]
    text: str  # header line (if any) + body


def split_sections(body: str) -> list[Section]:
    """Split on ATX headers of any level that are not inside code fences."""
    sections, stack, lines, in_fence = [], [], [], False
    current_path: list[str] = []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            sections.append(Section(list(current_path), text))

    for line in body.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        header = None if in_fence else HEADER_RE.match(line)
        if header:
            flush()
            lines = []
            level, name = len(header.group(1)), re.sub(r"\s*\{#[^}]*\}\s*$", "", header.group(2)).strip()
            stack = [(lvl, n) for lvl, n in stack if lvl < level] + [(level, name)]
            current_path = [n for _, n in stack]
        lines.append(line)
    flush()
    return sections


def _split_long_line(line: str, budget: int) -> list[str]:
    parts, cur = [], ""
    for word in line.split(" "):
        candidate = f"{cur} {word}" if cur else word
        if cur and n_tokens(candidate) > budget:
            parts.append(cur)
            candidate = word
        cur = candidate
    return parts + ([cur] if cur else [])


def split_large(text: str, budget: int) -> list[str]:
    """Split text over budget into pieces: by blank-line blocks (code fences kept whole), then by lines.
    A code block cut by lines is re-fenced in every piece."""
    blocks, buf, in_fence = [], [], False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence and buf:
            blocks.append("\n".join(buf))
            buf = []
        else:
            buf.append(line)
    if buf:
        blocks.append("\n".join(buf))

    pieces: list[str] = []
    for block in blocks:
        if n_tokens(block) <= budget:
            pieces.append(block)
            continue
        # cut by lines (a single over-long line by words); a cut inside a code fence closes and re-opens it
        lines: list[str] = []
        for line in block.split("\n"):
            lines += _split_long_line(line, budget - 8) if n_tokens(line) > budget - 8 else [line]
        cur: list[str] = []
        opener: str | None = None
        for line in lines:
            if cur and n_tokens("\n".join(cur + [line])) > budget - 8:
                pieces.append("\n".join(cur + (["```"] if opener else [])))
                cur = [opener] if opener else []
            cur.append(line)
            if FENCE_RE.match(line):
                opener = None if opener else line.strip().lstrip("> ")
        if cur:
            pieces.append("\n".join(cur))

    # merge small consecutive pieces back up to the budget
    merged: list[str] = []
    for p in pieces:
        if merged and n_tokens(merged[-1] + "\n\n" + p) <= budget:
            merged[-1] += "\n\n" + p
        else:
            merged.append(p)
    return merged


def prefix(title: str, path: list[str]) -> str:
    return " > ".join([title, *path]) + "\n\n"


def chunk_page(title: str, body: str) -> list[tuple[list[str], str]]:
    """Return (header_path, chunk text with prefix)."""
    units: list[Section] = []
    for s in split_sections(body):
        budget = MAX_TOKENS - n_tokens(prefix(title, s.path))
        if n_tokens(s.text) <= budget:
            units.append(s)
        else:
            units += [Section(s.path, piece) for piece in split_large(s.text, budget)]

    chunks: list[tuple[list[str], str]] = []
    cur: Section | None = None
    for u in units:
        if cur is not None:
            merged = cur.text + "\n\n" + u.text
            header_only = not cur.text.split("\n", 1)[1:]  # a section that is just a header line
            fits = n_tokens(prefix(title, cur.path) + merged) <= MAX_TOKENS
            if fits and (header_only or n_tokens(prefix(title, cur.path) + cur.text) < MIN_TOKENS):
                cur = Section(cur.path, merged)
                continue
            chunks.append((cur.path, prefix(title, cur.path) + cur.text))
        cur = u
    if cur is not None:
        chunks.append((cur.path, prefix(title, cur.path) + cur.text))

    # A chunk still below MIN_TOKENS is appended to the previous chunk of the page if that stays within MAX_TOKENS.
    merged: list[tuple[list[str], str]] = []
    for path, text in chunks:
        if merged and n_tokens(text) < MIN_TOKENS:
            body = text.split("\n\n", 1)[1]  # drop this chunk's prefix; its header line is kept in the body
            candidate = merged[-1][1] + "\n\n" + body
            if n_tokens(candidate) <= MAX_TOKENS:
                merged[-1] = (merged[-1][0], candidate)
                continue
        merged.append((path, text))
    return merged


GENERATED = RAW / "docs_generated"
# Rendered pages whose generated reference tables are missing from the Markdown sources (src/data/fetch_doc_tables.py):
# page -> (title, which tables to keep). Each kept table row becomes one Markdown list line under its heading.
GENERATED_PAGES = {
    "sql-ref-functions-builtin": (
        "Built-in Functions (reference tables)",
        lambda heading, header: header[:1] == ["Function"],
    ),
    "configuration": (
        "Spark Configuration (Spark SQL reference tables)",
        lambda heading, header: heading in {"Runtime SQL Configuration", "Static SQL Configuration"},
    ),
}


class _TableExtractor(HTMLParser):
    """Headings (h1-h4) and tables (rows of cell texts) of an HTML page, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple] = []
        self._text: list[str] | None = None
        self._rows: list[list[str]] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("h1", "h2", "h3", "h4") or (tag in ("td", "th") and self._rows is not None):
            self._text = []
        elif tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._rows.append([])

    def handle_endtag(self, tag: str) -> None:
        text = " ".join("".join(self._text or []).split())
        if tag in ("h1", "h2", "h3", "h4") and self._text is not None:
            self.events.append(("heading", text))
            self._text = None
        elif tag in ("td", "th") and self._rows is not None and self._text is not None:
            if self._rows:
                self._rows[-1].append(text)
            self._text = None
        elif tag == "table" and self._rows is not None:
            self.events.append(("table", [r for r in self._rows if r]))
            self._rows = None

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text.append(data)


def generated_markdown(page: str, html: str) -> str:
    """Markdown body (## heading + one list line per row) of the kept generated tables of a rendered page."""
    keep = GENERATED_PAGES[page][1]
    parser = _TableExtractor()
    parser.feed(html)
    heading, sections = "", []
    for kind, value in parser.events:
        if kind == "heading":
            heading = value
            continue
        header, rows = value[0], value[1:]
        if not rows or not keep(heading, header):
            continue
        if header[:1] == ["Function"]:
            lines = [f"- `{r[0]}`: {r[1] if len(r) > 1 else ''}".rstrip() for r in rows]
        else:  # Property Name | Default | Meaning | Since Version
            lines = [
                f"- `{r[0]}` (default: {r[1]}; since {r[3] if len(r) > 3 else '?'}): {r[2] if len(r) > 2 else ''}"
                for r in rows
            ]
        sections.append(f"## {heading}\n\n" + "\n".join(lines))
    return "\n\n".join(sections)


def entry_chunks(title: str, body: str) -> list[tuple[list[str], str]]:
    """One chunk per reference entry (list line), prefixed with title > heading: a long list chunk dilutes the one
    entry a request is about, so dense retrieval misses it (CRISP-DM iteration 2, reports/decisions.md)."""
    heading, chunks = "", []
    for line in body.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        elif line.startswith("- "):
            chunks.append(([heading], prefix(title, [heading]) + line))
    return chunks


def main() -> None:
    source = (DOCS / "SOURCE.txt").read_text()
    version = re.search(r"tag:\s*v?(\S+)", source).group(1)
    base_url = f"https://spark.apache.org/docs/{version}/"

    rows, pages, skipped = [], 0, []
    for path in sorted(DOCS.rglob("*.md")):
        page = path.relative_to(DOCS).with_suffix("").as_posix()
        if page in SKIP_PAGES:
            skipped.append(page)
            continue
        title, body = preprocess(path.read_text(encoding="utf-8"), version)
        title = title or page
        pages += 1
        for i, (header_path, text) in enumerate(chunk_page(title, body)):
            rows.append(
                {
                    "chunk_id": f"{page}#{i:03d}",
                    "page": page,
                    "title": title,
                    "header_path": header_path,
                    "url": f"{base_url}{page}.html",
                    "n_tokens": n_tokens(text),
                    "text": text,
                }
            )

    # Generated reference tables (CRISP-DM iterations 1-2, reports/decisions.md): extra pages, one chunk per entry;
    # existing ids unchanged.
    generated = 0
    for page, (title, _) in GENERATED_PAGES.items():
        html_path = GENERATED / f"{page}.html"
        if not html_path.exists():
            print(f"WARNING: {html_path} missing — run src/data/fetch_doc_tables.py")
            continue
        body = generated_markdown(page, html_path.read_text(encoding="utf-8"))
        for i, (header_path, text) in enumerate(entry_chunks(title, body)):
            rows.append(
                {
                    "chunk_id": f"{page}__generated#{i:03d}",
                    "page": f"{page}__generated",
                    "title": title,
                    "header_path": header_path,
                    "url": f"{base_url}{page}.html",
                    "n_tokens": n_tokens(text),
                    "text": text,
                }
            )
            generated += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    toks = sorted(r["n_tokens"] for r in rows)
    q = lambda p: toks[min(len(toks) - 1, int(p * len(toks)))]
    stats = {
        "version": version,
        "pages_in": pages + len(skipped),
        "pages_skipped": skipped,
        "pages_chunked": pages,
        "chunks": len(rows),
        "generated_reference_chunks": generated,
        "tokens_total": sum(toks),
        "tokens": {"min": toks[0], "p10": q(0.1), "median": q(0.5), "p90": q(0.9), "max": toks[-1]},
        "share_lt_300": round(sum(t < MIN_TOKENS for t in toks) / len(toks), 3),
        "share_300_500": round(sum(MIN_TOKENS <= t <= MAX_TOKENS for t in toks) / len(toks), 3),
        "share_gt_500": round(sum(t > MAX_TOKENS for t in toks) / len(toks), 3),
        "tokenizer": "tiktoken cl100k_base",
    }
    update_stats("doc_chunks", stats)
    print(json.dumps(stats, indent=1))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
