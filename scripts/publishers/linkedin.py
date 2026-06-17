#!/usr/bin/env python3
"""publishers/linkedin.py — LinkedIn UGC post publisher.

Usage:
    python3 -m publishers.linkedin <post-file> [--dry-run] [--yes]
"""

import sys
from pathlib import Path
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import argparse
import json
import urllib.request

from engine_state import QUEUE_DIR, VAULT
from publishers._common import load_creds, extract_body, sanitize, archive

REQUIRED_CREDS = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN")
LINKEDIN_API_URL = "https://api.linkedin.com/v2/ugcPosts"


def publish(post_file: Path, *, dry_run: bool = False) -> dict:
    creds = load_creds(REQUIRED_CREDS)
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


def main():
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
        confirm = input(f"Post {post_file.name} to LinkedIn? (y/N): ")
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    result = publish(post_file, dry_run=args.dry_run)
    if result and result.get("post_id"):
        archived = archive(post_file, [result], extract_body(post_file), "now")
        print(f"  \u2713 posted: share_urn={result['post_id']}")
        print(f"  \u2713 archived: {archived.relative_to(VAULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
