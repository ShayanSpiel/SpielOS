#!/usr/bin/env python3
"""publishers/twitter.py — X/Twitter direct publisher.

Usage:
    python3 -m publishers.twitter <post-file> [--dry-run] [--yes]
"""

import sys
from pathlib import Path
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import argparse
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from engine_state import QUEUE_DIR, VAULT
from publishers._common import load_creds, extract_body, sanitize, archive

REQUIRED_CREDS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
X_API_URL = "https://api.twitter.com/2/tweets"


def oauth1_header(method: str, url: str, params: dict, creds: dict) -> str:
    oauth = {
        "oauth_consumer_key": creds["X_API_KEY"],
        "oauth_nonce": base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest())[:32].decode(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    all_params = {**oauth, **params}
    param_str = "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}" for k, v in sorted(all_params.items()))
    sig_base = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_str, safe='')}"
    signing_key = f"{creds['X_API_SECRET']}&{creds['X_ACCESS_SECRET']}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), sig_base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v)}"' for k, v in oauth.items())


def publish(post_file: Path, *, dry_run: bool = False) -> dict:
    creds = load_creds(REQUIRED_CREDS)
    body_raw = extract_body(post_file)
    body = sanitize(body_raw)
    if dry_run:
        print(f"--- DRY RUN: {post_file.name} ---")
        print(body)
        print(f"--- {len(body)} chars ---")
        return {}
    data = json.dumps({"text": body}).encode("utf-8")
    auth = oauth1_header("POST", X_API_URL, {}, creds)
    req = urllib.request.Request(
        X_API_URL, data=data,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    tweet_id = result.get("data", {}).get("id", "")
    return {"channel_id": "x-direct", "service": "x", "post_id": tweet_id}


def main():
    parser = argparse.ArgumentParser(description="Publish to X/Twitter")
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
        confirm = input(f"Post {post_file.name} to X? (y/N): ")
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    result = publish(post_file, dry_run=args.dry_run)
    if result and result.get("post_id"):
        archived = archive(post_file, [result], extract_body(post_file), "now")
        print(f"  \u2713 posted: tweet_id={result['post_id']}")
        print(f"  \u2713 archived: {archived.relative_to(VAULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
