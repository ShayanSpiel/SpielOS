#!/usr/bin/env python3
"""publisher/buffer.py — Buffer publisher via MCP subprocess.

Spawns @damusix/buffer-mcp as an MCP child process and uses it to
list channels, create posts, and delete posts. No direct Buffer API calls.

CLI:
    python3 tools/publisher/buffer.py <post-file> [--dry-run] [--yes] [--queue]
    python3 tools/publisher/buffer.py --list-channels [--vault <path>]
    python3 tools/publisher/buffer.py --delete <post-id> [--vault <path>]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import _common as common
from _common import (
    VAULT, READY_DIR, POSTED_DIR, ENV_FILE,
    extract_body, sanitize, archive, check_gates_verdict, write_frontmatter,
    set_vault,
)
from _mcp_client import MCPClient, MCPError


MCP_PACKAGE = "@damusix/buffer-mcp@latest"
ORG_ID = "62f24e9ed7fef68ddf794937"

CHANNELS_CACHE: list[dict] | None = None


def _get_mcp_client() -> MCPClient:
    token = ""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("BUFFER_ACCESS_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not token:
        import os as _os
        token = _os.environ.get("BUFFER_ACCESS_TOKEN", "")
    if not token:
        raise MCPError("BUFFER_ACCESS_TOKEN not found in .env or environment")
    return MCPClient(
        command=["npx", "-y", MCP_PACKAGE],
        env={"BUFFER_ACCESS_TOKEN": token},
        name="spielos-buffer",
    )


def list_channels() -> list[dict]:
    global CHANNELS_CACHE
    if CHANNELS_CACHE is not None:
        return CHANNELS_CACHE
    with _get_mcp_client() as mcp:
        result = mcp.call_tool("use_buffer_api", {
            "action": "listOrganizations",
        })
        orgs = (result.get("data") or {}).get("account", {}).get("organizations", [])
        org_id = orgs[0]["id"] if orgs else ORG_ID
        chan_result = mcp.call_tool("use_buffer_api", {
            "action": "listChannels",
            "payload": {"organizationId": org_id},
        })
        channels = (chan_result.get("data") or {}).get("channels", [])
        CHANNELS_CACHE = channels
    return CHANNELS_CACHE


def find_channel_id(service: str) -> str | None:
    for ch in list_channels():
        if ch.get("service", "").lower() == service.lower():
            return ch.get("id")
    return None


def _read_platform(post_file: Path) -> str:
    text = post_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("missing frontmatter; cannot infer Buffer platform")
    parts = text.split("---", 2)
    if len(parts) < 2:
        raise ValueError("invalid frontmatter; cannot infer Buffer platform")
    for line in parts[1].splitlines():
        st = line.strip()
        if st.startswith("platform:"):
            platform = st.split(":", 1)[1].strip().lower()
            if platform:
                return platform
    raise ValueError("missing platform in frontmatter; cannot infer Buffer channel")


PLATFORM_TO_SERVICE = {
    "x": "twitter",
    "twitter": "twitter",
    "linkedin": "linkedin",
    "threads": "threads",
}


def publish_via_mcp(post_file: Path, *, mode: str = "now") -> dict:
    with _get_mcp_client() as mcp:
        body_raw = extract_body(post_file)
        body = sanitize(body_raw)
        platform = _read_platform(post_file)
        service = PLATFORM_TO_SERVICE.get(platform, platform)
        channel_id = find_channel_id(service)
        if not channel_id:
            raise MCPError(f"No {service} channel found in Buffer account")
        result = mcp.call_tool("use_buffer_api", {
            "action": "createPost",
            "payload": {
                "channelId": channel_id,
                "text": body,
                "schedulingType": "automatic",
                "mode": "addToQueue" if mode == "queue" else "shareNow",
            },
        })
        post_data = (result.get("data") or {}).get("createPost", {}).get("post", {})
        post_id = post_data.get("id", "")
        if not post_id:
            raise MCPError(f"Buffer did not return a post id: {result}")
        return {
            "channel_id": channel_id,
            "service": service,
            "post_id": post_id,
            "post_data": post_data,
        }


def delete_post(post_id: str) -> bool:
    with _get_mcp_client() as mcp:
        result = mcp.call_tool("use_buffer_api", {
            "action": "deletePost",
            "payload": {"postId": post_id},
        })
        typename = (result.get("data") or {}).get("deletePost", {}).get("__typename", "")
        return typename == "DeletePostSuccess"


def main() -> int:
    global VAULT, READY_DIR, POSTED_DIR, ENV_FILE
    parser = argparse.ArgumentParser(description="Publish to Buffer via MCP")
    parser.add_argument("post_file", nargs="?", help="Path to draft file")
    parser.add_argument("--list-channels", action="store_true",
                        help="List available Buffer channels")
    parser.add_argument("--delete", metavar="POST_ID",
                        help="Delete a Buffer post by ID")
    parser.add_argument("--queue", action="store_true",
                        help="Add to queue instead of posting now")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--vault", help="SpielOS vault root")
    args = parser.parse_args()

    if args.vault:
        v = Path(args.vault).expanduser().resolve()
        if (v / "team" / "strategist.md").is_file():
            set_vault(v)
            VAULT = common.VAULT
            READY_DIR = common.READY_DIR
            POSTED_DIR = common.POSTED_DIR
            ENV_FILE = common.ENV_FILE
        else:
            print(f"ERROR: {v} is not a SpielOS vault (no team/strategist.md)", file=sys.stderr)
            return 3

    if args.list_channels:
        channels = list_channels()
        if not channels:
            print("No channels found.")
            return 0
        for ch in channels:
            sid = ch.get("id", "?")
            svc = ch.get("service", "?")
            name = ch.get("name", "?")
            locked = " 🔒" if ch.get("isLocked") else ""
            print(f"  {svc:10s} {sid}  {name}{locked}")
        return 0

    if args.delete:
        ok = delete_post(args.delete)
        if ok:
            print(f"  ✓ deleted post {args.delete}")
            return 0
        else:
            print(f"  ✗ failed to delete post {args.delete}", file=sys.stderr)
            return 1

    if not args.post_file:
        parser.print_help()
        return 1

    post_file = Path(args.post_file)
    if not post_file.is_absolute():
        resolved = READY_DIR / post_file.name
        if resolved.exists():
            post_file = resolved

    if not post_file.exists():
        print(f"ERROR: not found: {post_file}", file=sys.stderr)
        return 1

    ok, gate_msg = check_gates_verdict(post_file)
    if not ok:
        print(f"ERROR: refusing to publish: {gate_msg}", file=sys.stderr)
        return 1

    if args.dry_run:
        body = extract_body(post_file)
        try:
            platform = _read_platform(post_file)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        service = PLATFORM_TO_SERVICE.get(platform, platform)
        print(f"--- DRY RUN: {post_file.name} ---")
        print(f"  platform: {service} (via Buffer MCP)")
        print(f"  body ({len(body)} chars):")
        print(body[:500] + ("..." if len(body) > 500 else ""))
        print(f"---")
        return 0

    if not args.yes:
        try:
            platform = _read_platform(post_file)
            service = PLATFORM_TO_SERVICE.get(platform, platform)
            confirm = input(f"Post {post_file.name} to {service} via Buffer? (y/N): ")
        except EOFError:
            confirm = "y"
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    mode = "queue" if args.queue else "now"
    try:
        result = publish_via_mcp(post_file, mode=mode)
    except MCPError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    post_id = result["post_id"]
    print(f"  posted to {result['service']}: post_id={post_id}")
    if args.queue:
        print(f"  (queued — scheduled for later delivery)")

    try:
        body = extract_body(post_file)
        fm, _ = __import__("_common", fromlist=["parse_frontmatter"]).parse_frontmatter(
            post_file.read_text()
        )
        fm["status"] = "posted"
        fm["posted_at"] = datetime.now().isoformat(timespec="seconds")
        fm["buffer_post_id"] = post_id
        fm["buffer_channel_id"] = result["channel_id"]
        fm["buffer_mode"] = mode
        fm["body"] = body
        posted = POSTED_DIR / post_file.name
        posted.parent.mkdir(parents=True, exist_ok=True)
        write_frontmatter(posted, fm, body)
        post_file.unlink(missing_ok=True)
        print(f"  archived: content/posted/{post_file.name}")
    except Exception as e:
        print(f"  WARN: archive failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
