"""Download the RENDERED doc pages whose generated reference tables are missing from docs/**/*.md.

docs/sql-ref-functions-builtin.md and docs/configuration.md pull their reference tables in at site-build time
with `{% include_api_gen generated-*.html %}` (SQL built-in functions, runtime/static SQL configs). The Markdown
sources therefore lack them, and chunk_docs.py (which strips Liquid tags) lost them too. This script stores the
published pages of the same release; chunk_docs.py turns their generated tables into additional chunks.

Usage:
    python src/data/fetch_doc_tables.py
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DOCS_SOURCE = ROOT / "data" / "raw" / "docs" / "SOURCE.txt"
OUT_DIR = ROOT / "data" / "raw" / "docs_generated"
PAGES = ["sql-ref-functions-builtin", "configuration"]


def main() -> None:
    version = re.search(r"tag:\s*v?(\S+)", DOCS_SOURCE.read_text()).group(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"release: {version}", f"downloaded_at: {datetime.now(UTC).isoformat(timespec='seconds')}"]
    for page in PAGES:
        url = f"https://spark.apache.org/docs/{version}/{page}.html"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        (OUT_DIR / f"{page}.html").write_text(resp.text, encoding="utf-8")
        lines.append(f"{page}: {url} ({len(resp.text)} chars)")
        print(f"Saved {page}.html ({len(resp.text):,} chars) from {url}")
    (OUT_DIR / "SOURCE.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
