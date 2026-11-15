"""Print Jira issue counts per issue type (cheap maxResults=0 queries, no download).

Usage:
    python src/data/check_jira.py [--project SPARK] [--since 2020-01-01]
"""

from __future__ import annotations

import argparse

import requests

from fetch_jira import count_issues

ISSUE_TYPES = ["Bug", "New Feature", "Improvement", "Task", "Sub-task", "Wish"]
MIN_WISH = 150


def main() -> None:
    parser = argparse.ArgumentParser(description="Count Jira issues per issue type.")
    parser.add_argument("--project", default="SPARK")
    parser.add_argument("--since", default="2020-01-01")
    args = parser.parse_args()

    session = requests.Session()
    base = f'project = "{args.project}" AND created >= "{args.since}"'

    print(f"Issues in {args.project} created >= {args.since}")
    counts: dict[str, int] = {}
    for issuetype in ISSUE_TYPES:
        counts[issuetype] = count_issues(session, f'{base} AND issuetype = "{issuetype}"')
        print(f"  {issuetype:<14}{counts[issuetype]:>8}")
    total = count_issues(session, base)
    print(f"  {'(other types)':<14}{total - sum(counts.values()):>8}")
    print(f"  {'TOTAL':<14}{total:>8}")

    wish_all_time = count_issues(session, f'project = "{args.project}" AND issuetype = "Wish"')
    print(f"\nWish in {args.project}, all time: {wish_all_time}")

    if counts["Wish"] < MIN_WISH:
        print(
            f"\nNote: only {counts['Wish']} Wish issues since {args.since} (< {MIN_WISH}). "
            "Use `python src/data/fetch_jira.py --wish-other` to get Wish examples from all ASF projects."
        )


if __name__ == "__main__":
    main()
