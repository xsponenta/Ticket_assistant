"""Download docs/**/*.md of the latest stable Apache Spark release from GitHub.

Usage:
    python src/data/fetch_docs.py

Writes Markdown files to data/raw/docs/ (paths relative to the repo's docs/ folder)
and data/raw/docs/SOURCE.txt with the tag and download date.
Set GITHUB_TOKEN to avoid the 60 requests/hour anonymous GitHub API limit (rarely needed).
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import requests
from tqdm import tqdm

REPO = "apache/spark"
TAGS_URL = f"https://api.github.com/repos/{REPO}/tags"
TARBALL_URL = "https://codeload.github.com/" + REPO + "/tar.gz/refs/tags/{tag}"
STABLE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")  # excludes -rcN, -previewN, etc.

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "docs"


def latest_stable_tag(session: requests.Session) -> str:
    """Scan all tags (paginated) and return the highest vX.Y.Z."""
    best: tuple[tuple[int, int, int], str] | None = None
    url: str | None = TAGS_URL
    params: dict[str, int] | None = {"per_page": 100}
    while url:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        for tag in resp.json():
            match = STABLE_TAG.match(tag["name"])
            if match:
                version = (int(match[1]), int(match[2]), int(match[3]))
                if best is None or version > best[0]:
                    best = (version, tag["name"])
        url = resp.links.get("next", {}).get("url")
        params = None  # the "next" link already carries the query string
    if best is None:
        raise RuntimeError("No stable vX.Y.Z tag found")
    return best[1]


def docs_relative_path(member: tarfile.TarInfo) -> PurePosixPath | None:
    """Map 'spark-X.Y.Z/docs/a/b.md' -> 'a/b.md'; None for anything we don't extract."""
    parts = PurePosixPath(member.name).parts[1:]  # drop the top-level 'spark-X.Y.Z/' folder
    if not member.isfile() or len(parts) < 2 or parts[0] != "docs" or ".." in parts:
        return None
    if not parts[-1].endswith(".md"):
        return None
    return PurePosixPath(*parts[1:])


def extract_docs(session: requests.Session, tag: str, out_dir: Path) -> tuple[int, int]:
    """Stream the source tarball and write only docs/**/*.md. Returns (file count, total bytes)."""
    n_files = n_bytes = 0
    with session.get(TARBALL_URL.format(tag=tag), stream=True, timeout=60) as resp:
        resp.raise_for_status()
        size = int(resp.headers.get("Content-Length", 0)) or None
        with tqdm.wrapattr(resp.raw, "read", total=size, desc=f"{tag}.tar.gz") as raw:
            with tarfile.open(fileobj=raw, mode="r|gz") as tar:
                for member in tar:
                    rel = docs_relative_path(member)
                    if rel is None:
                        continue
                    data = tar.extractfile(member).read()  # type: ignore[union-attr]
                    target = out_dir.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    n_files += 1
                    n_bytes += len(data)
    return n_files, n_bytes


def main() -> None:
    session = requests.Session()
    if token := os.environ.get("GITHUB_TOKEN"):
        session.headers["Authorization"] = f"Bearer {token}"

    tag = latest_stable_tag(session)
    print(f"Latest stable Spark tag: {tag}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)  # avoid mixing files from different releases
    OUT_DIR.mkdir(parents=True)

    n_files, n_bytes = extract_docs(session, tag, OUT_DIR)
    downloaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (OUT_DIR / "SOURCE.txt").write_text(
        f"repository: https://github.com/{REPO}\n"
        f"tag: {tag}\n"
        f"tarball: {TARBALL_URL.format(tag=tag)}\n"
        f"downloaded_at: {downloaded_at}\n"
        f"markdown_files: {n_files}\n"
        f"total_bytes: {n_bytes}\n"
    )
    print(f"Extracted {n_files} .md files ({n_bytes / 1e6:.1f} MB) to {OUT_DIR}")


if __name__ == "__main__":
    main()
