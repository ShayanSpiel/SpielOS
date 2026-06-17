#!/usr/bin/env python3
"""publishers/_common.py — Shared sanitize, validate, archive logic.

All three publishers (buffer, twitter, linkedin) use these.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from engine_state import ENV_FILE, POSTED_DIR, VAULT


LEAKED_MARKDOWN = re.compile(r"\*\*|\[\[|]]")
EMDASH = "\u2014"


def load_creds(required: list[str]) -> dict:
    creds = dict(os.environ)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    missing = [c for c in required if not creds.get(c)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}. Set in {ENV_FILE}")
    return creds


def extract_body(post_file: Path) -> str:
    from engine_frontmatter import parse_frontmatter
    content = post_file.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    out = []
    started = False
    for line in body.splitlines():
        if not started:
            if line.startswith("## ") or line.strip() == "---":
                started = True
                continue
            out.append(line)
        else:
            if line.strip() == "---":
                break
            out.append(line)
    text = "\n".join(out)
    text = re.sub(r"^## .*$", "", text, flags=re.MULTILINE)
    return text.strip()


def sanitize(body: str) -> str:
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    out = re.sub(r"(^|[\s(>])_([^_\s][^_]*?)_([\s.,)!?>]|$)", r"\1\2\3", out)
    out = re.sub(r"(^|[\s(>])\*([^*\s][^*]*?)\*([\s.,)!?>]|$)", r"\1\2\3", out)
    out = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"^>\s+", "", out, flags=re.MULTILINE)
    return out


def validate(body: str, char_limit: int) -> tuple[bool, str]:
    n = len(body)
    if n > char_limit:
        return False, f"body is {n} chars (limit {char_limit})"
    if LEAKED_MARKDOWN.search(body):
        return False, "leaked markdown codes"
    if EMDASH in body:
        return False, "em-dash present (use \u2192, comma, or colon)"
    return True, "ok"


def archive(post_file: Path, channel_results: list[dict], body: str, mode: str,
            posted_dir: Path | None = None) -> Path:
    if posted_dir is None:
        posted_dir = POSTED_DIR
    posted_dir.mkdir(parents=True, exist_ok=True)
    posted_file = posted_dir / post_file.name
    from engine_frontmatter import parse_frontmatter, write_frontmatter
    fm, _ = parse_frontmatter(post_file.read_text(encoding="utf-8"))
    fm["status"] = "posted"
    fm["posted_at"] = datetime.now().isoformat(timespec="seconds")
    fm["buffer_mode"] = mode
    fm["buffer_post_ids"] = {r["service"]: r["post_id"] for r in channel_results}
    fm["buffer_channel_ids"] = [r["channel_id"] for r in channel_results]
    fm["buffer_services"] = [r["service"] for r in channel_results]
    for r in channel_results:
        svc = r["service"]
        pid = r["post_id"]
        if svc == "x":
            fm["tweet_id"] = pid
        elif svc == "linkedin":
            fm["linkedin_share_urn"] = pid
        elif svc == "threads":
            fm["threads_post_id"] = pid
    fm["body"] = body
    write_frontmatter(posted_file, fm, body)
    post_file.unlink()
    return posted_file
