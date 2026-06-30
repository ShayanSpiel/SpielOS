#!/usr/bin/env python3
"""publisher/twitter.py — X/Twitter direct publisher (Buffer fallback).

The Publisher role's fallback when Buffer is down or out of quota.
Direct X API via OAuth 1.0a.

CLI:
    python3 tools/publisher/twitter.py <post-file> [--dry-run] [--yes]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

import _common as common
from _common import VAULT, READY_DIR, load_creds, extract_body, sanitize, archive, check_gates_verdict, set_vault


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
    creds = load_creds(list(REQUIRED_CREDS))
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
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"X API HTTP {e.code}: {body or e.reason}") from e
    tweet_id = result.get("data", {}).get("id", "")
    return {"channel_id": "x-direct", "service": "x", "post_id": tweet_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish to X/Twitter")
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
            confirm = input(f"Post {post_file.name} to X? (y/N): ")
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
        print(f"  posted: tweet_id={result['post_id']}")
        try:
            archived = archive(post_file, [result], extract_body(post_file), "now")
            print(f"  archived: {archived.relative_to(VAULT)}")
        except Exception as e:
            print(f"WARN: archive failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
