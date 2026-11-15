"""Download Apache Jira issues to JSONL (raw API JSON of selected fields), resumably.

Examples:
    python src/data/fetch_jira.py                          # all SPARK issues created since 2020-01-01
    python src/data/fetch_jira.py --limit 200 --out data/raw/sample.jsonl
    python src/data/fetch_jira.py --issuetype Bug --out data/raw/spark_bugs.jsonl
    python src/data/fetch_jira.py --wish-other             # latest 1500 Wish issues, all ASF projects

If interrupted, rerun the same command: it continues from the checkpoint file
(<out>.checkpoint.json). Reporter/assignee and other personal fields are never requested.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

SEARCH_URL = "https://issues.apache.org/jira/rest/api/2/search"
FIELDS = [
    "summary",
    "description",
    "issuetype",
    "components",
    "priority",
    "status",
    "resolution",
    "created",
    "resolutiondate",
    "issuelinks",
    "labels",
]
PAGE_SIZE = 100
MIN_INTERVAL_S = 1.0  # at most 1 request per second
MAX_RETRIES = 6  # backoff: 1, 2, 4, 8, 16, 32 s
RETRY_STATUSES = {429, 500, 502, 503, 504}
WISH_OTHER_LIMIT = 1500

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "raw" / "spark_issues.jsonl"
DEFAULT_WISH_OUT = ROOT / "data" / "raw" / "wish_other.jsonl"

_last_request_at = 0.0


def get_json(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET with a global rate limit and exponential backoff on 429/5xx and network errors."""
    global _last_request_at
    for attempt in range(MAX_RETRIES + 1):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()

        retry_after: float | None = None
        try:
            resp = session.get(url, params=params, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code not in RETRY_STATUSES:
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code} for {resp.url}: {resp.text[:500]}")
                return resp.json()
            error = f"HTTP {resp.status_code}"
            header = resp.headers.get("Retry-After", "")
            retry_after = float(header) if header.isdigit() else None

        if attempt == MAX_RETRIES:
            raise RuntimeError(f"Giving up after {MAX_RETRIES} retries: {error}")
        delay = retry_after if retry_after is not None else 2.0**attempt
        tqdm.write(f"  {error}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s", file=sys.stderr)
        time.sleep(delay)
    raise AssertionError("unreachable")


def count_issues(session: requests.Session, jql: str) -> int:
    """Number of issues matching a JQL query (maxResults=0 returns only the total)."""
    return int(get_json(session, SEARCH_URL, {"jql": jql, "maxResults": 0})["total"])


def build_jql(project: str, since: str, issuetype: str | None) -> str:
    parts = [f'project = "{project}"', f'created >= "{since}"']
    if issuetype:
        parts.append(f'issuetype = "{issuetype}"')
    return " AND ".join(parts) + " ORDER BY created ASC, key ASC"


def checkpoint_path(out: Path) -> Path:
    return out.with_name(out.name + ".checkpoint.json")


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)  # atomic


def read_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["key"] for line in f if line.strip()}


def fetch(session: requests.Session, jql: str, fields: list[str], out: Path, limit: int | None) -> None:
    """Page through a JQL search and append issues to `out`, checkpointing after every page."""
    ckpt = checkpoint_path(out)
    state: dict[str, Any] = {"jql": jql, "start_at": 0, "bytes": 0}
    if ckpt.exists():
        saved = json.loads(ckpt.read_text())
        if saved["jql"] != jql:
            sys.exit(f"{ckpt} belongs to another query:\n  {saved['jql']}\nDelete it or choose another --out.")
        state = saved
        print(f"Resuming from checkpoint: start_at={state['start_at']}")

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        # Drop anything written after the last checkpoint (or the whole file when starting fresh).
        with out.open("r+b") as f:
            f.truncate(state["bytes"])
    seen = read_keys(out)

    total = count_issues(session, jql.split(" ORDER BY")[0])
    target = min(total, limit) if limit else total
    print(f"JQL: {jql}\nMatching issues: {total}; target: {target}; already saved: {len(seen)}")

    with out.open("ab") as f, tqdm(total=target, initial=min(len(seen), target), unit="issue") as bar:
        while len(seen) < target:
            page = get_json(
                session,
                SEARCH_URL,
                {"jql": jql, "startAt": state["start_at"], "maxResults": PAGE_SIZE, "fields": ",".join(fields)},
            )
            issues = page["issues"]
            if not issues:
                break
            consumed = 0
            for issue in issues:
                if len(seen) >= target:
                    break
                consumed += 1
                if issue["key"] in seen:  # possible when the result order shifts between runs
                    continue
                record = {"id": issue["id"], "key": issue["key"], "fields": issue["fields"]}
                f.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
                seen.add(issue["key"])
                bar.update(1)
            f.flush()
            os.fsync(f.fileno())
            state["start_at"] += consumed
            state["bytes"] = f.tell()
            save_checkpoint(ckpt, state)

            # New issues may be created while we download.
            target = min(page["total"], limit) if limit else page["total"]
            bar.total = target
            bar.refresh()

    print(f"Done: {len(seen)} issues in {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="2020-01-01", help="created >= this date (YYYY-MM-DD)")
    parser.add_argument("--project", default="SPARK", help="Jira project key")
    parser.add_argument("--issuetype", default=None, help='optional filter, e.g. "Bug" or "New Feature"')
    parser.add_argument("--out", type=Path, default=None, help="output JSONL path")
    parser.add_argument("--limit", type=int, default=None, help="max number of issues (for testing)")
    parser.add_argument(
        "--wish-other",
        action="store_true",
        help=f"fetch the most recent Wish issues from ALL ASF projects (default limit {WISH_OTHER_LIMIT}); "
        "ignores --project/--since/--issuetype and adds the project field",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers["Accept"] = "application/json"

    if args.wish_other:
        jql = "issuetype = Wish ORDER BY created DESC, key DESC"
        fetch(session, jql, FIELDS + ["project"], args.out or DEFAULT_WISH_OUT, args.limit or WISH_OTHER_LIMIT)
    else:
        jql = build_jql(args.project, args.since, args.issuetype)
        fetch(session, jql, FIELDS, args.out or DEFAULT_OUT, args.limit)


if __name__ == "__main__":
    main()
