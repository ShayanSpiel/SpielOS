#!/usr/bin/env python3
"""publisher/buffer.py — Buffer multi-platform publisher.

The Publisher role's primary dispatch path. One call fans a single draft
out to all configured Buffer channels (X + LinkedIn + Threads in one go).

CLI:
    python3 tools/publisher/buffer.py <post-file> [--dry-run] [--yes] [--queue]

Exit 0 on success, 1 on failure. Prints one-line result + archive path to stdout.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _common import (
    BANNERS_ROOT, ICONS_ROOT, VAULT, QUEUE_DIR,
    load_creds, extract_body, sanitize, archive,
)


BUFFER_API_URL = "https://api.buffer.com"
ASSETS_BASE_URL = os.environ.get("ASSETS_BASE_URL", "")
SMMS_API = "https://sm.ms/api/v2/upload"
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
                "organization_name": org.get("organization_name"),
            })
    return out


def _upload_to_smms(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        boundary = "----BOUNDARYBOUNDARY"
        filename = path.name
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="smfile"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            SMMS_API, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("success"):
            return result.get("data", {}).get("url")
        return None
    except Exception:
        return None


def _read_banner_rel(post_file: Path) -> str | None:
    try:
        text = post_file.read_text()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 2:
        return None
    for line in parts[1].splitlines():
        st = line.strip()
        if st.startswith("banner:"):
            return st.split(":", 1)[1].strip()
    return None


def _read_banner_url(post_file: Path) -> str | None:
    try:
        text = post_file.read_text()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 2:
        return None
    banner_rel = None
    for line in parts[1].splitlines():
        st = line.strip()
        if st.startswith("banner:"):
            banner_rel = st.split(":", 1)[1].strip()
            break
    if not banner_rel:
        return None
    if Path(banner_rel).is_absolute():
        return None
    banner_path = (VAULT / banner_rel).resolve()
    try:
        banner_path.relative_to(BANNERS_ROOT)
    except ValueError:
        try:
            banner_path.relative_to(ICONS_ROOT)
        except ValueError:
            return None
    if not banner_path.is_file():
        return None
    url = _upload_to_smms(banner_path)
    if url:
        return url
    if ASSETS_BASE_URL:
        if banner_rel.startswith("/"):
            banner_rel = banner_rel.lstrip("/")
        return f"{ASSETS_BASE_URL.rstrip('/')}/{banner_rel}"
    return None


def create_post(token: str, channel_id: str, text: str, *,
                mode: str = "now",
                assets: list[dict] | None = None) -> tuple[str, dict]:
    scheduling_input = {
        "text": text, "schedulingType": "automatic",
        "mode": "addToQueue" if mode == "queue" else "shareNow",
    }
    if assets:
        scheduling_input["assets"] = assets
    variables = {"input": {"channelId": channel_id, **scheduling_input}}
    data = buffer_request("""
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt status channelId } }
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
    creds = load_creds(list(REQUIRED_CREDS))
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
    banner_url = _read_banner_url(post_file)
    assets = None
    if banner_url:
        assets = [{"image": {"url": banner_url}}]
        print(f"  banner: {banner_url}")
    else:
        banner_path = _read_banner_rel(post_file)
        if banner_path:
            print(f"  banner NOT uploaded: file at {banner_path}")
            print(f"    set ASSETS_BASE_URL env var or check file exists")
        else:
            print(f"  no banner in frontmatter")
    token = creds["BUFFER_ACCESS_TOKEN"]
    results = []
    for cid in channel_ids:
        svc = service_map.get(cid, "unknown")
        post_id, _ = create_post(token, cid, body, mode=mode, assets=assets)
        results.append({"channel_id": cid, "service": svc, "post_id": post_id})
        print(f"  {svc:9s} ({cid}): post {post_id}")
    return results


def main() -> int:
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
        try:
            confirm = input(f"Post {post_file.name} via Buffer? (y/N): ")
        except EOFError:
            confirm = "y"
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    mode = "queue" if args.queue else "now"
    try:
        results = publish(post_file, mode=mode, dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if results:
        try:
            archived = archive(post_file, results, extract_body(post_file), mode)
            print(f"  archived: {archived.relative_to(VAULT)}")
        except Exception as e:
            print(f"WARN: archive failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
