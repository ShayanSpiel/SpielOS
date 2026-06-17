#!/usr/bin/env python3
"""publishers/buffer.py — Buffer multi-platform publisher.

Usage:
    python3 -m publishers.buffer <post-file> [--dry-run] [--yes]
"""

import sys
from pathlib import Path
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

from engine_state import QUEUE_DIR, VAULT
from publishers._common import load_creds, extract_body, sanitize, archive

BUFFER_API_URL = "https://api.buffer.com"
REQUIRED_CREDS = ("BUFFER_ACCESS_TOKEN", "BUFFER_CHANNEL_IDS")
SERVICE_NORMALIZE = {
    "twitter": "x", "x": "x", "linkedin": "linkedin",
    "linkedin-page": "linkedin", "linkedin-profile": "linkedin",
    "threads": "threads",
}


def buffer_request(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        BUFFER_API_URL, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:300] if hasattr(e, 'read') else ""
        raise RuntimeError(f"Buffer API HTTP {e.code}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Buffer API URLError: {e.reason}") from e


def list_channels(token: str) -> list[dict]:
    query = """
    query { account { organizations { id name channels { id service name } } } }
    """
    data = buffer_request(query, {}, token)
    orgs = (data.get("data") or {}).get("account", {}).get("organizations", []) or []
    out = []
    for org in orgs:
        for ch in org.get("channels", []) or []:
            out.append({
                "id": ch.get("id"), "service": ch.get("service"),
                "name": ch.get("name"), "organization_id": org.get("id"),
                "organization_name": org.get("name"),
            })
    return out


def create_post(token: str, channel_id: str, text: str, *,
                mode: str = "now") -> tuple[str, dict]:
    scheduling_input = {
        "text": text, "schedulingType": "automatic",
        "mode": "addToQueue" if mode == "queue" else "automatic",
    }
    if mode != "queue":
        scheduling_input["sentImmediately"] = True
    variables = {"input": {"channelId": channel_id, **scheduling_input}}
    data = buffer_request("""
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt status service channelId } }
        ... on MutationError { message }
      }
    }
    """, variables, token)
    payload = data.get("data", {}).get("createPost") or {}
    if "message" in payload:
        raise RuntimeError(f"Buffer error: {payload['message']}")
    post = payload.get("post") or {}
    post_id = str(post.get("id", ""))
    if not post_id:
        raise RuntimeError("Buffer: no post id returned")
    return post_id, post


def publish(post_file: Path, *, mode: str = "now", dry_run: bool = False,
            service: str | None = None) -> list[dict]:
    """Publish to Buffer. If service is specified, only post to matching channels."""
    creds = load_creds(REQUIRED_CREDS)
    all_configured = [c.strip() for c in creds["BUFFER_CHANNEL_IDS"].split(",") if c.strip()]
    if not all_configured:
        raise RuntimeError("BUFFER_CHANNEL_IDS is empty")
    body_raw = extract_body(post_file)
    body = sanitize(body_raw)
    if dry_run:
        print(f"--- DRY RUN: {post_file.name} ---")
        print(body)
        svc_label = service or "all"
        print(f"--- {len(body)} chars, service={svc_label} ---")
        return []
    channels = list_channels(creds["BUFFER_ACCESS_TOKEN"])
    service_map = {}
    for ch in channels:
        if ch["id"] in all_configured:
            svc_raw = (ch.get("service") or "").lower()
            service_map[ch["id"]] = SERVICE_NORMALIZE.get(svc_raw, svc_raw)
    if service:
        channel_ids = [cid for cid, svc in service_map.items() if svc == service]
        if not channel_ids:
            raise RuntimeError(f"no Buffer channel configured for service '{service}'")
    else:
        channel_ids = all_configured
    token = creds["BUFFER_ACCESS_TOKEN"]
    results = []
    for cid in channel_ids:
        svc = service_map.get(cid, "unknown")
        post_id, _ = create_post(token, cid, body, mode=mode)
        results.append({"channel_id": cid, "service": svc, "post_id": post_id})
        print(f"  \u2713 {svc:9s} ({cid}): post {post_id}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Publish to Buffer")
    parser.add_argument("post_file", help="Path to queue file")
    parser.add_argument("--queue", action="store_true", help="Add to queue")
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
        confirm = input(f"Post {post_file.name} via Buffer? (y/N): ")
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    mode = "queue" if args.queue else "now"
    results = publish(post_file, mode=mode, dry_run=args.dry_run)
    if results:
        archived = archive(post_file, results, extract_body(post_file), mode)
        print(f"  \u2713 archived: {archived.relative_to(VAULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
