#!/usr/bin/env python3
"""publisher/linkedin.py — LinkedIn UGC post publisher (Buffer fallback).

The Publisher role's fallback when Buffer is down. Direct LinkedIn UGC API.

CLI:
    python3 tools/publisher/linkedin.py <post-file> [--dry-run] [--yes]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import _common as common
from _common import VAULT, READY_DIR, load_creds, extract_body, sanitize, archive, check_gates_verdict, set_vault


REQUIRED_CREDS = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN")
LINKEDIN_API_URL = "https://api.linkedin.com/v2/ugcPosts"


def publish(post_file: Path, *, dry_run: bool = False) -> dict:
    creds = load_creds(list(REQUIRED_CREDS))
    body_raw = extract_body(post_file)
    body = sanitize(body_raw)
    person_urn = creds["LINKEDIN_PERSON_URN"]
    if not person_urn.startswith("urn:li:person:"):
        person_urn = f"urn:li:person:{person_urn}"
    if dry_run:
        print(f"--- DRY RUN: {post_file.name} ---")
        print(body)
        print(f"--- {len(body)} chars ---")
        return {}
    payload = json.dumps({
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": body},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }).encode("utf-8")
    req = urllib.request.Request(
        LINKEDIN_API_URL, data=payload,
        headers={
            "Authorization": f"Bearer {creds['LINKEDIN_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"LinkedIn API HTTP {e.code}: {body or e.reason}") from e
    share_urn = result.get("id", "")
    return {"channel_id": "linkedin-direct", "service": "linkedin", "post_id": share_urn}


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish to LinkedIn")
    parser.add_argument("post_file", help="Path to queue file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--vault", help="SpielOS vault root (overrides $VAULT_DIR and global config)")
    args = parser.parse_args()
    global VAULT, READY_DIR, POSTED_DIR, ENV_FILE
    if args.vault:
        v = Path(args.vault).expanduser().resolve()
        if (v / "team" / "strategist.md").is_file():
            set_vault(v)
            VAULT = common.VAULT
            READY_DIR = common.READY_DIR
        else:
            print(f"ERROR: {v} is not a SpielOS vault (no team/strategist.md)", file=sys.stderr)
            return 3
    post_file = Path(args.post_file)
    if not post_file.is_absolute():
        post_file = READY_DIR / post_file.name if not post_file.exists() else post_file
    if not post_file.exists():
        print(f"ERROR: not found: {post_file}")
        return 1
    # Gate enforcement: refuse to publish a draft that failed tools/editor.py
    ok, gate_msg = check_gates_verdict(post_file)
    if not ok:
        print(f"ERROR: refusing to publish: {gate_msg}", file=sys.stderr)
        return 1
    if not args.yes and not args.dry_run:
        try:
            confirm = input(f"Post {post_file.name} to LinkedIn? (y/N): ")
        except EOFError:
            confirm = "y"
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    try:
        result = publish(post_file, dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if result and result.get("post_id"):
        print(f"  posted: share_urn={result['post_id']}")
        try:
            archived = archive(post_file, [result], extract_body(post_file), "now")
            print(f"  archived: {archived.relative_to(VAULT)}")
        except Exception as e:
            print(f"WARN: archive failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
