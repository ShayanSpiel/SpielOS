#!/usr/bin/env python3
"""post_x.py — X/Twitter publish pipeline (extract → sanitize → validate → POST → archive).

Replaces the bash wrapper `post-x.sh` and the OAuth helper it called.
Stdlib only (urllib, hmac, hashlib, base64, secrets, time, json, re, subprocess).
Honors rules.yaml §char_limits.x_single and the 15-mechanical-gate rules
(em-dash, leaked markdown, capital-start paragraphs).

Usage:
    python3 scripts/post_x.py <post-file>
    python3 scripts/post_x.py <post-file> --dry-run
    python3 scripts/post_x.py <post-file> --yes
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from state import (
    BANNERS_DIR, BRAND_CONFIG, ENV_FILE, POSTED_DIR, QUEUE_DIR, VAULT,
    now_iso, parse_frontmatter, write_frontmatter,
)
import yaml

REQUIRED_CREDS = (
    "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
)


# ─── Env loading ────────────────────────────────────────────────────────────

def load_env() -> dict:
    """Read ~/.config/opencode/.env into a dict (chmod 600)."""
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ─── Body extraction + sanitization ─────────────────────────────────────────

LEAKED_MARKDOWN = re.compile(r"\*\*|\[\[|]]")
EMDASH = "\u2014"
LEAKED_LINE = re.compile(r"^\s*[-*•#]+\s*")
URL_LINE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
UNICODE_OPENER = re.compile(r"^[\U0001f91d\u2713\u2718\u2192\U0001f3af\u274c\u2705\U0001f447\U0001f4ac]")


def extract_body(post_file: Path) -> str:
    """Extract the post body from a queue file (everything after the frontmatter)."""
    _, body = parse_frontmatter(post_file.read_text(encoding="utf-8"))
    body = re.sub(r"^---\s*$\n?", "", body, flags=re.MULTILINE)
    return body.strip()


def sanitize(body: str) -> str:
    """Strip markdown codes that X can't render; preserve Unicode voice markers + paragraphs."""
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)                              # **bold**
    out = re.sub(r"(^|[\s(>])_([^_\s][^_]*?)_([\s.,)!?>]|$)", r"\1\2\3", out)  # _italic_
    out = re.sub(r"(^|[\s(>])\*([^*\s][^*]*?)\*([\s.,)!?>]|$)", r"\1\2\3", out)  # *italic*
    out = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", out)                # [[wikilink]]
    out = re.sub(r"`([^`]+)`", r"\1", out)                                      # `code`
    out = re.sub(r"^>\s+", "", out, flags=re.MULTILINE)                        # > quote
    return out


def validate(body: str, char_limit: int) -> tuple[bool, str]:
    """Mechanical pre-flight check (char count, paragraphs, capital start, no leaks)."""
    n = len(body)
    if n > char_limit:
        return False, f"body is {n} chars (limit {char_limit})"
    if not re.search(r"^\s*$", body, flags=re.MULTILINE):
        return False, "no paragraph breaks — add blank lines"
    bad = []
    for i, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        line_clean = LEAKED_LINE.sub("", line)
        if URL_LINE.match(line_clean) or UNICODE_OPENER.match(line_clean):
            continue
        if line_clean[0].islower():
            bad.append(f"line {i}: '{line.strip()[:60]}'")
    if bad:
        return False, "lowercase-starting paragraphs: " + "; ".join(bad)
    if LEAKED_MARKDOWN.search(body):
        return False, "leaked markdown codes"
    if EMDASH in body:
        return False, "em-dash present (use →, comma, or colon)"
    return True, "ok"


# ─── OAuth 1.0a + POST ──────────────────────────────────────────────────────

def oauth_sign(method: str, url: str, query: dict, body: dict, ck: str, cs: str, tk: str, ts: str) -> str:
    oauth_params = {
        "oauth_consumer_key": ck, "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
        "oauth_token": tk, "oauth_version": "1.0",
    }
    all_params = {**oauth_params, **query, **body}
    sorted_params = sorted(all_params.items())
    param_string = "&".join(
        f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted_params
    )
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(param_string, safe=""),
    ])
    signing_key = f"{urllib.parse.quote(cs, safe='')}&{urllib.parse.quote(ts, safe='')}"
    digest = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("utf-8")
    return "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )


def post_tweet(text: str, creds: dict) -> tuple[int, str, str]:
    """Returns (http_code, tweet_id, body)."""
    url = "https://api.twitter.com/2/tweets"
    body_bytes = json.dumps({"text": text}).encode("utf-8")
    auth = oauth_sign(
        "POST", url, {}, {},
        creds["X_API_KEY"], creds["X_API_SECRET"],
        creds["X_ACCESS_TOKEN"], creds["X_ACCESS_SECRET"],
    )
    req = urllib.request.Request(
        url, data=body_bytes,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload.get("data", {}).get("id", ""), json.dumps(payload)
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            err = ""
        return e.code, "", err or "HTTPError (no body)"
    except urllib.error.URLError as e:
        return 0, "", f"URLError: {e.reason}"


# ─── Archive: move queue → posted, update frontmatter ──────────────────────

def archive(post_file: Path, tweet_id: str, tweet_url: str, body: str) -> Path:
    posted_file = POSTED_DIR / post_file.name
    fm, _ = parse_frontmatter(post_file.read_text(encoding="utf-8"))
    fm["status"] = "posted"
    fm["posted_at"] = now_iso()
    fm["tweet_id"] = tweet_id
    fm["tweet_url"] = tweet_url
    fm["body"] = body  # sanitized version actually published
    write_frontmatter(posted_file, fm, body)
    post_file.unlink()
    return posted_file


# ─── Char limit (from rules.yaml) ──────────────────────────────────────────

def get_char_limit() -> int:
    rules_file = VAULT / "rules.yaml"
    if rules_file.exists():
        try:
            rules = yaml.safe_load(rules_file.read_text())
            return rules.get("char_limits", {}).get("x_single", 280)
        except Exception:
            pass
    return 280


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post a draft to X / Twitter.")
    parser.add_argument("post_file", help="Path to a queue file (markdown with frontmatter)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Validate + show preview, do not post")
    args = parser.parse_args()

    post_file = Path(args.post_file)
    if not post_file.is_absolute():
        post_file = (QUEUE_DIR / post_file.name) if not post_file.exists() else post_file
    if not post_file.exists():
        print(f"ERROR: post file not found: {post_file}")
        return 1

    creds = load_env()
    missing = [c for c in REQUIRED_CREDS if not creds.get(c)]
    if missing and not args.dry_run:
        print(f"ERROR: missing env vars: {', '.join(missing)}")
        print(f"Set them in {ENV_FILE} (chmod 600).")
        return 2

    body_raw = extract_body(post_file)
    body = sanitize(body_raw)
    char_limit = get_char_limit()
    n = len(body)

    print(f"═══ X Publish: {post_file.name} ═══")
    print(f"  raw:   {len(body_raw)} chars")
    print(f"  clean: {n} chars (limit {char_limit})")

    ok, msg = validate(body, char_limit)
    if not ok:
        print(f"  ✗ validate: {msg}")
        return 1
    print(f"  ✓ validate: {msg}")

    # Preview
    print()
    print("─" * 60)
    print("POST PREVIEW")
    print("─" * 60)
    print(body)
    print("─" * 60)
    print(f"  Length: {n} chars")
    print("─" * 60)

    if args.dry_run:
        print("--dry-run: NOT posting.")
        return 0

    if not args.yes:
        confirm = input("Post to X? (y/N): ")
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    code, tweet_id, raw = post_tweet(body, creds)
    if code not in (200, 201) or not tweet_id:
        print(f"ERROR: API returned {code}: {raw[:300]}")
        return 1

    username = creds.get("X_USERNAME", "i")
    tweet_url = f"https://x.com/{username}/status/{tweet_id}"
    posted = archive(post_file, tweet_id, tweet_url, body)
    print(f"  ✓ posted: {tweet_url}")
    print(f"  ✓ archived: {posted.relative_to(VAULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
