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
import urllib.request
from pathlib import Path

from _common import VAULT, QUEUE_DIR, load_creds, extract_body, sanitize, archive


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
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    share_urn = result.get("id", "")
    return {"channel_id": "linkedin-direct", "service": "linkedin", "post_id": share_urn}


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish to LinkedIn")
    parser.add_argument("post_file", help="Path to queue file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    post_file = Path(args.post_file)
    if not post_file.is_absolute():
        post_file = QUEUE_DIR / post_file.name if not post_file.exists() else post_file
    if not post_file.exists():
        print(f"ERROR: not found: {post_file}")
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
        try:
            archived = archive(post_file, [result], extract_body(post_file), "now")
            print(f"  posted: share_urn={result['post_id']}")
            print(f"  archived: {archived.relative_to(VAULT)}")
        except Exception as e:
            print(f"WARN: archive failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
