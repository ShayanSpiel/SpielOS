#!/usr/bin/env python3
"""publisher/blog.py — Universal blog publisher.

Publishes blog drafts to WordPress, dev.to, or custom platforms via
REST API or MCP. Platform config is read from .env.

CLI:
    python3 tools/publisher/blog.py <draft> [--platform wordpress|devto|hashnode|custom] [--publish] [--dry-run] [--yes] [--vault <path>]
    python3 tools/publisher/blog.py <draft> --custom-api <url> [--custom-header <name:value>]...
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import _common as common
from _common import VAULT, READY_DIR, POSTED_DIR, ENV_FILE, check_gates_verdict, write_frontmatter, set_vault


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def load_env(key: str, default: str = "") -> str:
    for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key, default)


def extract_title_body(draft: Path) -> tuple[str, str]:
    text = draft.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    title = fm.get("title", draft.stem.replace("-", " ").title())
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
    clean = re.sub(r"^## .*$", "", "\n".join(out), flags=re.MULTILINE)
    return title, clean.strip()


def publish_wordpress(draft: Path, *, publish: bool = True,
                      dry_run: bool = False) -> dict:
    url = load_env("WP_URL")
    username = load_env("WP_USERNAME")
    app_password = load_env("WP_APP_PASSWORD")
    if not url:
        raise RuntimeError("WP_URL not configured in .env")
    if not username or not app_password:
        raise RuntimeError("WP_USERNAME and WP_APP_PASSWORD required in .env")

    title, body = extract_title_body(draft)
    tags_str = load_env("WP_TAGS", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    api_url = url.rstrip("/") + "/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": body,
        "status": "publish" if publish else "draft",
    }
    if tags:
        payload["tags"] = tags

    if dry_run:
        print(f"--- DRY RUN: would post to WordPress ---")
        print(f"  URL: {api_url}")
        print(f"  title: {title[:80]}")
        print(f"  status: {'publish' if publish else 'draft'}")
        print(f"  body ({len(body)} chars)")
        print(f"  tags: {tags}")
        return {}

    creds = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"WordPress API HTTP {e.code}: {body}") from e

    post_id = result.get("id")
    link = result.get("link", "")
    return {"platform": "wordpress", "post_id": str(post_id), "url": link, "status": result.get("status")}


def publish_devto(draft: Path, *, publish: bool = True,
                  dry_run: bool = False) -> dict:
    api_key = load_env("DEVTO_API_KEY")
    if not api_key:
        raise RuntimeError("DEVTO_API_KEY not configured in .env")

    title, body = extract_title_body(draft)
    tags_str = load_env("DEVTO_TAGS", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] or ["blog"]

    payload = {
        "article": {
            "title": title,
            "body_markdown": body,
            "published": publish,
            "tags": tags,
        }
    }

    if dry_run:
        print(f"--- DRY RUN: would post to dev.to ---")
        print(f"  title: {title[:80]}")
        print(f"  published: {publish}")
        print(f"  body ({len(body)} chars)")
        print(f"  tags: {tags}")
        return {}

    req = urllib.request.Request(
        "https://dev.to/api/articles",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"dev.to API HTTP {e.code}: {body}") from e

    post_id = str(result.get("id", ""))
    url = result.get("url", "")
    return {"platform": "devto", "post_id": post_id, "url": url, "status": "published" if publish else "draft"}


HASHNODE_API = "https://gql.hashnode.com"


def _hashnode_gql(query: str, variables: dict) -> dict:
    api_key = load_env("HASHNODE_API_KEY")
    if not api_key:
        raise RuntimeError("HASHNODE_API_KEY not configured in .env")
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        HASHNODE_API, data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"Hashnode API HTTP {e.code}: {b}") from e


def _hashnode_publication_id() -> str:
    pid = load_env("HASHNODE_PUBLICATION_ID")
    if pid:
        return pid
    q = "query { me { publications(first: 5) { edges { node { id title } } } } }"
    data = _hashnode_gql(q, {})
    me = (data.get("data") or {}).get("me") or {}
    publications = me.get("publications") or {}
    edges = publications.get("edges") or []
    if not edges:
        raise RuntimeError("No Hashnode publication found. Set HASHNODE_PUBLICATION_ID in .env")
    return edges[0]["node"]["id"]


def publish_hashnode(draft: Path, *, publish: bool = True,
                     dry_run: bool = False) -> dict:
    title, body = extract_title_body(draft)
    publication_id = _hashnode_publication_id()
    tags_str = load_env("HASHNODE_TAGS", "")
    tags = [{"slug": t.strip().lower(), "name": t.strip()}
            for t in tags_str.split(",") if t.strip()]

    if dry_run:
        print(f"--- DRY RUN: would post to Hashnode ---")
        print(f"  publication: {publication_id}")
        print(f"  title: {title[:80]}")
        print(f"  status: {'PUBLISH' if publish else 'DRAFT'}")
        print(f"  body ({len(body)} chars)")
        print(f"  tags: {tags}")
        return {}

    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
        createPost(input: $input) {
            post { id title url slug }
        }
    }
    """
    variables = {
        "input": {
            "publicationId": publication_id,
            "title": title,
            "contentMarkdown": body,
            "tags": tags,
            "settings": {"isRepublished": False},
        }
    }
    data = _hashnode_gql(mutation, variables)
    result = (data.get("data") or {}).get("createPost") or {}
    post = result.get("post") or {}
    if not post:
        errs = data.get("errors") or []
        msg = errs[0].get("message", str(data)) if errs else str(data)
        raise RuntimeError(f"Hashnode create failed: {msg}")

    return {
        "platform": "hashnode",
        "post_id": post.get("id", ""),
        "url": post.get("url", ""),
        "slug": post.get("slug", ""),
        "status": "published" if publish else "draft",
    }


def publish_custom_api(draft: Path, url: str, headers: list[str] | None = None,
                       publish: bool = True, dry_run: bool = False) -> dict:
    title, body = extract_title_body(draft)
    method = load_env("CUSTOM_BLOG_API_METHOD", "POST")
    auth_header = load_env("CUSTOM_BLOG_API_AUTH_HEADER", "")
    body_template = load_env("CUSTOM_BLOG_API_BODY_TEMPLATE",
                             '{"title":"{{title}}","content":"{{body}}"}')

    payload_str = body_template.replace("{{title}}", title).replace("{{body}}", body)
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        payload = {"title": title, "content": body}

    if dry_run:
        print(f"--- DRY RUN: would post to custom API ---")
        print(f"  URL: {url}")
        print(f"  method: {method}")
        print(f"  title: {title[:80]}")
        print(f"  payload: {json.dumps(payload, indent=2)[:300]}")
        return {}

    req_headers = {"Content-Type": "application/json"}
    if auth_header:
        if ":" in auth_header:
            k, v = auth_header.split(":", 1)
            req_headers[k.strip()] = v.strip()
    if headers:
        for h in headers:
            if ":" in h:
                k, v = h.split(":", 1)
                req_headers[k.strip()] = v.strip()

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=req_headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")[:500]
        raise RuntimeError(f"Custom API HTTP {e.code}: {body_text}") from e

    return {"platform": "custom", "raw": result}


def publish_custom_mcp(draft: Path, server_name: str, *,
                       dry_run: bool = False) -> dict:
    title, body = extract_title_body(draft)
    tool_name = load_env("CUSTOM_BLOG_MCP_TOOL", "create_post")

    if dry_run:
        print(f"--- DRY RUN: would post via MCP ---")
        print(f"  MCP server: {server_name}")
        print(f"  tool: {tool_name}")
        print(f"  title: {title[:80]}")
        print(f"  body ({len(body)} chars)")
        return {}

    raise RuntimeError(
        f"MCP-based custom publishing requires the MCP server '{server_name}' "
        f"to be installed in your IDE. Run this tool manually or configure "
        f"a direct API via CUSTOM_BLOG_API_URL in .env"
    )


def archive_post(draft: Path, result: dict, platform: str):
    text = draft.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    fm["status"] = "posted"
    fm["posted_at"] = datetime.now().isoformat(timespec="seconds")
    fm["blog_platform"] = platform
    fm["blog_post_id"] = result.get("post_id", "")
    fm["blog_url"] = result.get("url", "")
    fm["body"] = body
    posted_path = POSTED_DIR / draft.name
    posted_path.parent.mkdir(parents=True, exist_ok=True)
    write_frontmatter(posted_path, fm, body)
    draft.unlink(missing_ok=True)
    return posted_path


def main() -> int:
    global VAULT, READY_DIR, POSTED_DIR, ENV_FILE
    parser = argparse.ArgumentParser(description="Publish a blog draft")
    parser.add_argument("draft", nargs="?",
                        help="Path to draft file in content/ready/")
    parser.add_argument("--platform", choices=["wordpress", "devto", "hashnode", "custom"],
                        default=None, help="Target blog platform")
    parser.add_argument("--publish", action="store_true",
                        help="Publish immediately (default: draft)")
    parser.add_argument("--custom-api", metavar="URL",
                        help="Custom API endpoint URL")
    parser.add_argument("--custom-header", action="append", default=[],
                        help="Custom header (name:value, repeatable)")
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

    if not args.draft:
        parser.print_help()
        return 1

    draft = Path(args.draft)
    if not draft.is_absolute():
        resolved = READY_DIR / draft.name
        if resolved.exists():
            draft = resolved

    if not draft.exists():
        print(f"ERROR: not found: {draft}", file=sys.stderr)
        return 1

    ok, gate_msg = check_gates_verdict(draft)
    if not ok:
        print(f"ERROR: refusing to publish: {gate_msg}", file=sys.stderr)
        return 1

    platform = args.platform or "wordpress"
    if platform == "custom" and args.custom_api:
        platform = "custom_api"
    elif platform == "custom" and load_env("CUSTOM_BLOG_API_URL"):
        platform = "custom_api"
    elif platform == "custom" and load_env("CUSTOM_BLOG_MCP_SERVER"):
        platform = "custom_mcp"

    if not args.yes and not args.dry_run:
        try:
            confirm = input(f"Post {draft.name} to {platform}? (y/N): ")
        except EOFError:
            confirm = "y"
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    try:
        if platform == "wordpress":
            result = publish_wordpress(draft, publish=args.publish,
                                       dry_run=args.dry_run)
        elif platform == "devto":
            result = publish_devto(draft, publish=args.publish,
                                   dry_run=args.dry_run)
        elif platform == "hashnode":
            result = publish_hashnode(draft, publish=args.publish,
                                      dry_run=args.dry_run)
        elif platform == "custom_api":
            url = args.custom_api or load_env("CUSTOM_BLOG_API_URL")
            if not url:
                print("ERROR: --custom-api URL required for custom platform",
                      file=sys.stderr)
                return 1
            result = publish_custom_api(draft, url, headers=args.custom_header,
                                        publish=args.publish,
                                        dry_run=args.dry_run)
        elif platform == "custom_mcp":
            server = load_env("CUSTOM_BLOG_MCP_SERVER")
            result = publish_custom_mcp(draft, server, dry_run=args.dry_run)
        else:
            print(f"ERROR: unknown platform {platform!r}", file=sys.stderr)
            return 1
    except (RuntimeError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not args.dry_run and result:
        post_id = result.get("post_id") or result.get("url", "")
        url = result.get("url", "")
        print(f"  ✓ posted to {platform}: {url or post_id}")
        try:
            p = archive_post(draft, result, platform)
            print(f"  archived: content/posted/{draft.name}")
        except Exception as e:
            print(f"  WARN: archive failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
