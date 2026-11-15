"""Deterministic text cleaning for Jira issues.

clean_description(): Jira wiki markup -> Markdown, PII masking (decision D5), whitespace normalisation.
clean_summary():     PII masking + whitespace normalisation (Jira does not render markup in summaries).

Code ({code}/{noformat} blocks and {{mono}}) is protected while markup is converted, so nothing inside code
is rewritten. PII masking runs on the whole text (e-mails, Jira mentions and URL credentials also inside code);
GitHub-style @user mentions are masked in prose only, because Java/Scala/Python annotations look the same.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------- Jira -> Markdown

JIRA_CODE_RE = re.compile(r"\{(code|noformat)((?::[^}]*)?)\}(.*?)(?:\{\1\}|\Z)", re.S)
JIRA_MONO_RE = re.compile(r"\{\{(.+?)\}\}")
COLOR_RE = re.compile(r"\{color(?::[^}]*)?\}")
PANEL_RE = re.compile(r"\{(?:panel|anchor)(?::[^}]*)?\}")
QUOTE_RE = re.compile(r"\{quote\}(.*?)\{quote\}", re.S)
BQ_RE = re.compile(r"^[ \t]*bq\.[ \t]+(.*)$", re.M)
LIST_RE = re.compile(r"^[ \t]*([#*]+)[ \t]+(?=\S)", re.M)
HEADING_RE = re.compile(r"^[ \t]*h([1-6])\.[ \t]*(.*)$", re.M)
TABLE_HEADER_RE = re.compile(r"^[ \t]*\|\|(.*)\|\|[ \t]*$", re.M)
LINK_RE = re.compile(r"\[([^\[\]|\n]+?)\|([^\[\]\n]+?)\]")
BARE_LINK_RE = re.compile(r"\[((?:https?|ftp|mailto):[^\[\]\s|]+?)\](?!\()")  # not the text of a Markdown link
IMAGE_RE = re.compile(r"!([^!\s|]+\.(?:png|jpe?g|gif|svg|bmp))(?:\|[^!\n]*)?!", re.I)
PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def _fence(body: str, lang: str = "") -> str:
    """Fenced code block on its own lines; the fence is longer than any backtick run in the body."""
    fence = "```"
    while fence in body:
        fence += "`"
    return f"\n{fence}{lang}\n{body.strip(chr(10))}\n{fence}\n"


def _code_lang(params: str) -> str:
    """'{code:java}' -> 'java'; '{code:title=A.java|language=scala}' -> 'scala'; none/text -> ''."""
    lang = ""
    for i, part in enumerate(params.lstrip(":").split("|")):
        key, _, value = part.partition("=")
        if value and key.strip().lower() in ("language", "lang"):
            lang = value
        elif not value and i == 0:
            lang = key
    lang = lang.strip().lower()
    return "" if lang in ("none", "text", "noformat") or not re.fullmatch(r"[\w+#.-]+", lang) else lang


def _md_list_item(match: re.Match) -> str:
    markers = match.group(1)
    depth = len(markers) - 1
    return ("   " * depth + "1. ") if markers[-1] == "#" else ("  " * depth + "- ")


def _md_table_header(match: re.Match) -> str:
    cells = [c.strip() for c in match.group(1).split("||")]
    return "| " + " | ".join(cells) + " |\n|" + "---|" * len(cells)


def _md_quote(match: re.Match) -> str:
    lines = match.group(1).strip("\n").splitlines()
    return "\n" + "\n".join(f"> {line}".rstrip() for line in lines) + "\n"


def jira_to_markdown(text: str) -> str:
    protected: list[str] = []

    def protect(markdown: str) -> str:
        protected.append(markdown)
        return f"\x00{len(protected) - 1}\x00"

    # 1. code blocks (an unclosed {code} runs to the end of the text)
    text = JIRA_CODE_RE.sub(lambda m: protect(_fence(m.group(3), _code_lang(m.group(2)) if m.group(1) == "code" else "")), text)

    # 2. editor artifacts and escapes: '{{{}x{}}}' -> '{{x}}', '{*}' -> '*', '\{' -> '{'
    text = text.replace("\\{", "{").replace("\\}", "}").replace("{}", "")
    text = text.replace("{*}", "*").replace("{_}", "_")

    # 3. inline monospace
    def mono(m: re.Match) -> str:
        content = m.group(1).strip()
        tick = "``" if "`" in content else "`"
        return protect(f"{tick}{content}{tick}") if content else ""

    text = JIRA_MONO_RE.sub(mono, text)

    # 4. block-level markup (lists before headings: Jira '# item' is an ordered list, Markdown '# x' a heading)
    text = COLOR_RE.sub("", text)
    text = PANEL_RE.sub("", text)
    text = QUOTE_RE.sub(_md_quote, text)
    text = BQ_RE.sub(r"> \1", text)
    text = LIST_RE.sub(_md_list_item, text)
    text = HEADING_RE.sub(lambda m: "#" * int(m.group(1)) + " " + m.group(2).strip(), text)
    text = TABLE_HEADER_RE.sub(_md_table_header, text)

    # 5. links and images
    text = IMAGE_RE.sub(r"![](\1)", text)
    text = LINK_RE.sub(lambda m: f"[{m.group(1).strip()}]({m.group(2).strip()})", text)
    text = BARE_LINK_RE.sub(r"<\1>", text)

    # 6. restore protected code (placeholders can be nested: mono inside a quote etc.)
    while PLACEHOLDER_RE.search(text):
        text = PLACEHOLDER_RE.sub(lambda m: protected[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------- PII masking (D5)

URL_CREDENTIALS_RE = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", re.I)  # scheme://user:pass@
HTTP_USERINFO_RE = re.compile(r"\b((?:https?|ftp)://)[^\s/@:]+@", re.I)  # https://token@host
# e-mail not preceded by '/', so URI authorities such as spark://driver@host or abfss://container@account stay
EMAIL_RE = re.compile(r"(?<![\w.%+\-/])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JIRA_MENTION_RE = re.compile(r"\[~[^\]\s]+\]")
ANNOTATIONS = (
    "since|param|return|returns|throws|throw|deprecated|deprecate|transient|volatile|inline|tailrec|varargs|note|"
    "see|link|code|group|example|author|version|todo|inheritdoc|value|literal|interface|test|before|after|ignore|"
    "nullable|nonnull|override|scala|unchecked|specialized|native|tparam|constructor|define|usecase|udf|udtf|"
    "pandas_udf|property|classproperty|staticmethod|classmethod|dataclass|abstractmethod|overload|"
    "cached_property|contextmanager|wraps|lru_cache|nowarn|pytest|fixture|patch"
)
AT_MENTION_RE = re.compile(rf"(?<![\w.@/*{{`$<])@(?!(?:{ANNOTATIONS})\b)[a-z][A-Za-z0-9-]{{1,38}}\b(?!\s*[(.=])")
MD_CODE_RE = re.compile(r"^(`{3,})[^\n]*\n[\s\S]*?^\1[ \t]*$|(`+)[^`\n]+?\2", re.M)


def split_code(markdown: str) -> list[tuple[bool, str]]:
    """Split Markdown into (is_code, text) segments: fenced blocks and inline code spans are code."""
    segments, pos = [], 0
    for m in MD_CODE_RE.finditer(markdown):
        if m.start() > pos:
            segments.append((False, markdown[pos:m.start()]))
        segments.append((True, m.group(0)))
        pos = m.end()
    if pos < len(markdown):
        segments.append((False, markdown[pos:]))
    return segments


def mask_pii(text: str) -> str:
    text = URL_CREDENTIALS_RE.sub(r"\1", text)
    text = HTTP_USERINFO_RE.sub(r"\1", text)
    text = EMAIL_RE.sub("<EMAIL>", text)
    text = JIRA_MENTION_RE.sub("<USER>", text)
    return "".join(seg if is_code else AT_MENTION_RE.sub("<USER>", seg) for is_code, seg in split_code(text))


# ---------------------------------------------------------------- whitespace

INVISIBLE_RE = re.compile("[​‌‍⁠﻿]")


def _pre_normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace(" ", " ")
    return INVISIBLE_RE.sub("", text)


def normalize_whitespace(markdown: str) -> str:
    """Strip trailing spaces, collapse runs of spaces in prose (not indentation), at most one blank line in a row."""
    parts = []
    for is_code, seg in split_code(markdown):
        if not is_code:
            seg = re.sub(r"(?<=\S)[ \t]{2,}", " ", seg)
        parts.append(re.sub(r"[ \t]+(?=\n)", "", seg))
    text = "".join(parts)
    text = re.sub(r"[ \t]+$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------- public API

def clean_description(text: str | None) -> str:
    if not text:
        return ""
    return normalize_whitespace(mask_pii(jira_to_markdown(_pre_normalise(text))))


def clean_summary(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", mask_pii(_pre_normalise(text))).strip()
