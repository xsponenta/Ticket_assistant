"""Sanity-check the raw data and write reports/02_data_sanity.md.

Usage:
    python src/data/sanity_check.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ISSUES_PATH = ROOT / "data" / "raw" / "spark_issues.jsonl"
WISH_OTHER_PATH = ROOT / "data" / "raw" / "wish_other.jsonl"
DOCS_DIR = ROOT / "data" / "raw" / "docs"
REPORT_PATH = ROOT / "reports" / "02_data_sanity.md"


def flatten(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue["fields"]
    links = fields.get("issuelinks") or []
    return {
        "key": issue["key"],
        "project": (fields.get("project") or {}).get("key", issue["key"].split("-")[0]),
        "issuetype": fields["issuetype"]["name"],
        "created": fields["created"],
        "year": int(fields["created"][:4]),
        "empty_description": not (fields.get("description") or "").strip(),
        "has_duplicate_link": any(link["type"]["name"] == "Duplicate" for link in links),
        "components": [c["name"] for c in fields.get("components") or []],
        "resolution": (fields.get("resolution") or {}).get("name", "Unresolved"),
    }


def load_issues(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        return pd.DataFrame([flatten(json.loads(line)) for line in f if line.strip()])


def md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame (index included) as a Markdown table."""
    df = df.reset_index()
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    align = "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(df[c]) else "---" for c in df.columns) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, align, *rows])


def pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def issues_section(df: pd.DataFrame) -> list[str]:
    n = len(df)
    out = [
        "## SPARK issues",
        f"- File: `{ISSUES_PATH.relative_to(ROOT)}`",
        f"- Issues: **{n}** (unique keys: {df['key'].nunique()})",
        f"- Created: {df['created'].min()[:10]} … {df['created'].max()[:10]}",
        "",
        "### Issues per issue type and year",
        md_table(pd.crosstab(df["issuetype"], df["year"], margins=True, margins_name="Total")),
        "",
        "### Empty descriptions per issue type",
    ]
    empty = df.groupby("issuetype").agg(issues=("key", "size"), empty=("empty_description", "sum"))
    empty = empty.sort_values("issues", ascending=False)
    empty["empty_%"] = [pct(e, i) for e, i in zip(empty["empty"], empty["issues"])]
    empty.loc["Total"] = [n, int(df["empty_description"].sum()), pct(df["empty_description"].sum(), n)]
    empty[["issues", "empty"]] = empty[["issues", "empty"]].astype(int)
    out += [md_table(empty), ""]

    dup = int(df["has_duplicate_link"].sum())
    out += ["### Duplicate links", f"Issues with at least one \"Duplicate\" link: **{dup}** ({pct(dup, n)}%)", ""]

    comps = df["components"].explode().dropna().value_counts().head(15).rename("issues").to_frame()
    comps["%_of_issues"] = [pct(c, n) for c in comps["issues"]]
    no_comp = int((df["components"].str.len() == 0).sum())
    out += [
        "### Top-15 components",
        md_table(comps.rename_axis("component")),
        f"\nIssues without any component: {no_comp} ({pct(no_comp, n)}%)",
        "",
    ]

    res = df["resolution"].value_counts().rename("issues").to_frame()
    res["%"] = [pct(c, n) for c in res["issues"]]
    out += ["### Resolution distribution", md_table(res.rename_axis("resolution")), ""]
    return out


def wish_other_section(df: pd.DataFrame) -> list[str]:
    n = len(df)
    projects = df["project"].value_counts().head(10).rename("issues").to_frame()
    return [
        "## Wish issues from all ASF projects",
        f"- File: `{WISH_OTHER_PATH.relative_to(ROOT)}`",
        f"- Issues: **{n}** from {df['project'].nunique()} projects; "
        f"created {df['created'].min()[:10]} … {df['created'].max()[:10]}",
        f"- Empty descriptions: {int(df['empty_description'].sum())} ({pct(df['empty_description'].sum(), n)}%)",
        "",
        "Top-10 projects:",
        "",
        md_table(projects.rename_axis("project")),
        "",
    ]


def docs_section() -> list[str]:
    pages = sorted(DOCS_DIR.rglob("*.md"))
    size = sum(p.stat().st_size for p in pages)
    source = DOCS_DIR / "SOURCE.txt"
    out = ["## Spark documentation"]
    if source.exists():
        out += ["```", source.read_text().strip(), "```"]
    out += [
        f"- Markdown pages: **{len(pages)}**",
        f"- Total size: **{size / 1e6:.2f} MB** ({size} bytes)",
        "",
    ]
    return out


def main() -> None:
    if not ISSUES_PATH.exists():
        raise SystemExit(f"{ISSUES_PATH} not found; run src/data/fetch_jira.py first.")

    lines = [
        "# 02 · Data sanity check",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `src/data/sanity_check.py`_",
        "",
    ]
    lines += issues_section(load_issues(ISSUES_PATH))
    if WISH_OTHER_PATH.exists():
        lines += wish_other_section(load_issues(WISH_OTHER_PATH))
    if DOCS_DIR.exists():
        lines += docs_section()
    else:
        lines += ["## Spark documentation", "_Not downloaded: run src/data/fetch_docs.py._", ""]

    report = "\n".join(lines)
    print(report)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
