#!/usr/bin/env python3
"""archive.py — Move a posted draft from queue/ to posted/ and update frontmatter.

This is the canonical "publish succeeded, file the post" step. It is the
ONLY place that moves files between queue/ and posted/. The dispatcher
calls it after a successful API call, then verify.py runs the post-archive
assertions.

The function is atomic at the file level (read + write + delete). It is NOT
transactional across multiple files.

Pure-ish: file I/O is the point. No CLI. No external API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from engine_state import POSTED_DIR, QUEUE_DIR
from engine_frontmatter import parse_frontmatter, write_frontmatter, now_iso
from engine_serial import log, log_err


class ArchiveError(Exception):
    pass


def _stamp(fm: dict, key: str, value: Any) -> dict:
    fm = dict(fm) if fm else {}
    fm[key] = value
    return fm


def archive_draft(
    draft_path: Path,
    post_ids: dict | None = None,
    urls: dict | None = None,
    posted_at: str | None = None,
    platform: str | None = None,
    queue_dir: Path | None = None,
    posted_dir: Path | None = None,
) -> Path:
    """Move a draft from queue/ to posted/, update frontmatter, return new path.

    Args:
        draft_path: Path to the draft in content/queue/. Must exist.
        post_ids: Optional dict of per-service post IDs (e.g. {"x": "abc",
            "linkedin": "def", "threads": "ghi"}).
        urls: Optional dict of per-service public URLs.
        posted_at: Optional ISO timestamp. Defaults to now.
        platform: Optional platform override. Defaults to frontmatter value.
        queue_dir: Optional override for the source directory.
        posted_dir: Optional override for the destination directory.

    Returns:
        Path to the new location in content/posted/.

    Raises:
        ArchiveError: if the file is missing, not in queue/, or move fails.
    """
    draft_path = Path(draft_path)
    queue_dir = queue_dir or QUEUE_DIR
    posted_dir = posted_dir or POSTED_DIR
    if not draft_path.exists():
        raise ArchiveError(f"draft not found: {draft_path}")
    if draft_path.parent != queue_dir:
        raise ArchiveError(f"draft must be in {queue_dir}, got {draft_path.parent}")
    text = draft_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if not fm:
        fm = {}
    ts = posted_at or now_iso()
    fm = _stamp(fm, "posted_at", ts)
    if platform:
        fm = _stamp(fm, "platform", platform)
    elif not fm.get("platform"):
        fm = _stamp(fm, "platform", _platform_from_filename(draft_path.name))
    if post_ids:
        for service, pid in post_ids.items():
            if not pid:
                continue
            if service == "x":
                fm = _stamp(fm, "tweet_id", pid)
            elif service == "linkedin":
                fm = _stamp(fm, "linkedin_share_urn", pid)
            elif service == "threads":
                fm = _stamp(fm, "threads_post_id", pid)
        grouped = {k: v for k, v in post_ids.items() if v}
        if grouped:
            fm = _stamp(fm, "buffer_post_ids", grouped)
    if urls:
        for service, url in urls.items():
            if not url:
                continue
            if service == "x":
                fm = _stamp(fm, "tweet_url", url)
            elif service == "linkedin":
                fm = _stamp(fm, "linkedin_url", url)
            elif service == "threads":
                fm = _stamp(fm, "threads_url", url)
        grouped_urls = {k: v for k, v in urls.items() if v}
        if grouped_urls:
            fm = _stamp(fm, "urls", grouped_urls)
    if not fm.get("engagement"):
        fm = _stamp(fm, "engagement", {
            "reactions": 0,
            "comments": 0,
            "reposts": 0,
            "impressions": 0,
            "rate": 0.0,
            "fetched_at": None,
        })
    posted_dir.mkdir(parents=True, exist_ok=True)
    target = posted_dir / draft_path.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        i = 1
        while target.exists():
            target = posted_dir / f"{stem}-{i}{suffix}"
            i += 1
    try:
        write_frontmatter(target, fm, body)
    except Exception as e:
        raise ArchiveError(f"failed to write {target}: {e}") from e
    try:
        draft_path.unlink()
    except OSError as e:
        log_err("archive", f"failed to remove original {draft_path}: {e}")
        log("WARN", "archive", "Original draft still exists after archive",
            original=str(draft_path), archived=str(target))
    log("INFO", "archive", "Draft archived",
        from_path=str(draft_path), to_path=str(target),
        platform=fm.get("platform", ""),
        posted_at=ts,
        post_ids=post_ids or {},
        urls=urls or {},
    )
    return target


def _platform_from_filename(name: str) -> str:
    n = name.lower()
    if "tweet" in n or "-x-" in n or "-x." in n:
        return "x"
    if "linkedin" in n:
        return "linkedin"
    if "pillar" in n or "blog" in n:
        return "blog"
    return "other"
