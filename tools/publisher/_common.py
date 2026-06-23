#!/usr/bin/env python3
"""publisher/_common.py — Shared sanitize, validate, archive logic for the Publisher role.

All three publishers (buffer, twitter, linkedin) use these. This module
is self-contained — no engine.* imports — so the Publisher role can call
these from `tools/publisher/` directly.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ─── Vault detection ─────────────────────────────────────────────────────

def find_vault() -> Path:
    """Find the SpielOS vault root. Walk up from cwd, then check ~/.spielos/, ~/.spiel/ (legacy)."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "team" / "md.md").exists() and (p / "system" / "state-machine.md").exists():
            return p
    for home_vault in [Path.home() / ".spielos", Path.home() / ".spiel"]:
        if (home_vault / "team" / "md.md").exists():
            return home_vault
    # Fall back to env var
    env_vault = os.environ.get("VAULT_DIR")
    if env_vault:
        return Path(env_vault)
    return cwd


VAULT = find_vault()
ENV_FILE = VAULT / ".env"
QUEUE_DIR = VAULT / "content" / "queue"
POSTED_DIR = VAULT / "content" / "posted"
BANNERS_ROOT = (VAULT / "assets" / "banners").resolve()
ICONS_ROOT = (VAULT / "assets" / "icons").resolve()


# ─── Frontmatter parser (standalone) ─────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm = {}
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def write_frontmatter(out_path: Path, fm: dict, body: str) -> None:
    """Atomically write a markdown file with the given frontmatter + body."""
    import yaml
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body
    out_path.write_text(text, encoding="utf-8")


# ─── Creds ───────────────────────────────────────────────────────────────

def load_creds(required: list[str]) -> dict:
    """Load credentials from process env first, then .env file. Fail if required missing."""
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


# ─── Body extraction / sanitization ──────────────────────────────────────

LEAKED_MARKDOWN = re.compile(r"\*\*|\[\[|]]")
EMDASH = "\u2014"


def extract_body(post_file: Path) -> str:
    """Read a draft file and return the post body (frontmatter stripped, H1 removed)."""
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
    """Strip markdown formatting that doesn't render on social platforms."""
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


# ─── Archive ─────────────────────────────────────────────────────────────

def archive(post_file: Path, channel_results: list[dict], body: str, mode: str,
            posted_dir: Path | None = None) -> Path:
    """Move a published post to posted/ with archive frontmatter."""
    if posted_dir is None:
        posted_dir = POSTED_DIR
    posted_dir.mkdir(parents=True, exist_ok=True)
    posted_file = posted_dir / post_file.name
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
