#!/usr/bin/env python3
"""post_linkedin.py — LinkedIn UGC post publisher (extract → sanitize → validate → POST → archive).

Replaces `post-linkedin.sh` (467 LOC) with one Python module.
Honors rules.yaml §char_limits.linkedin_polished, the 15-mechanical-gate rules,
and LinkedIn's UGC Posts API.

Usage:
    python3 scripts/post_linkedin.py <post-file>
    python3 scripts/post_linkedin.py <post-file> --dry-run
    python3 scripts/post_linkedin.py <post-file> --yes
    python3 scripts/post_linkedin.py <post-file> --image <path>
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from state import (
    BANNERS_DIR, BRAND_CONFIG, ENV_FILE, POSTED_DIR, QUEUE_DIR,
    SCREENSHOTS_DIR, VAULT, now_iso, parse_frontmatter, write_frontmatter,
)
import yaml

REQUIRED_CREDS = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN")
LEAKED_MARKDOWN = re.compile(r"\*\*|\[\[|]]")
EMDASH = "\u2014"
LEAKED_LINE = re.compile(r"^\s*[-*•#]+\s*")
URL_LINE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
UNICODE_OPENER = re.compile(r"^[\U0001f91d\u2713\u2718\u2192\U0001f3af\u274c\u2705\U0001f447\U0001f4ac]")


def load_env() -> dict:
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


def extract_body(post_file: Path) -> str:
    """LinkedIn body: between the frontmatter closer and the first `## ` or `---` divider.

    Strips `## Hook` / `## Setup` style section headers (they were internal markers).
    """
    content = post_file.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    # Walk line by line, find first `## ` or `---` divider after the frontmatter
    out = []
    started = False
    for line in body.splitlines():
        if not started:
            if line.startswith("## "):
                started = True
                continue
            if line.strip() == "---":
                started = True
                continue
            out.append(line)
        else:
            if line.strip() == "---":
                break
            out.append(line)
    text = "\n".join(out)
    text = re.sub(r"^## .*$", "", text, flags=re.MULTILINE)
    return text.strip()


def sanitize(body: str) -> str:
    """Strip markdown codes; preserve paragraphs + Unicode voice markers."""
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    out = re.sub(r"(^|[\s(>])_([^_\s][^_]*?)_([\s.,)!?>]|$)", r"\1\2\3", out)
    out = re.sub(r"(^|[\s(>])\*([^*\s][^*]*?)\*([\s.,)!?>]|$)", r"\1\2\3", out)
    out = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"^>\s+", "", out, flags=re.MULTILINE)
    return out


def validate(body: str, char_limit: int) -> tuple[bool, str]:
    n = len(body)
    if n > char_limit:
        return False, f"body is {n} chars (limit {char_limit})"
    if not re.search(r"^[[:space:]]*$", body, flags=re.MULTILINE):
        return False, "no paragraph breaks"
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
        return False, "em-dash present"
    return True, "ok"


def capture_window(app: str, out_path: Path, wait: float = 1.5) -> bool:
    """Activate an app, verify it is frontmost, screenshot its front window."""
    subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], check=False, capture_output=True)
    import time
    time.sleep(wait)
    frontmost = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of (first process whose frontmost is true)'],
        capture_output=True, text=True,
    ).stdout.strip()
    if app not in frontmost:
        return False
    win_id = subprocess.run(
        ["osascript", "-e", f'tell application "{app}" to get id of front window'],
        capture_output=True, text=True,
    ).stdout.strip()
    if not win_id:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["screencapture", "-l", win_id, "-o", "-x", str(out_path)], check=False, capture_output=True)
    return out_path.exists()


def image_ok(path: Path) -> tuple[bool, str]:
    """Validate image exists, ≤5MB, ≥100x100, png/jpg/gif."""
    if not path.exists():
        return False, "file not found"
    size = path.stat().st_size
    if size > 5_242_880:
        return False, f"image {size//1024//1024}MB > 5MB limit"
    fmt = subprocess.run(["sips", "-g", "format", str(path)], capture_output=True, text=True).stdout
    fmt_match = re.search(r"format:\s*(\S+)", fmt)
    fmt_str = fmt_match.group(1).lower() if fmt_match else ""
    if fmt_str not in ("png", "jpeg", "jpg", "gif"):
        return False, f"format {fmt_str} not supported"
    dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                          capture_output=True, text=True).stdout
    w_match = re.search(r"pixelWidth:\s*(\d+)", dims)
    h_match = re.search(r"pixelHeight:\s*(\d+)", dims)
    w = int(w_match.group(1)) if w_match else 0
    h = int(h_match.group(1)) if h_match else 0
    if w < 100 or h < 100:
        return False, f"image too small ({w}x{h})"
    return True, f"{w}x{h} {fmt_str.upper()}"


def get_char_limit() -> int:
    rules_file = VAULT / "rules.yaml"
    if rules_file.exists():
        try:
            rules = yaml.safe_load(rules_file.read_text())
            return rules.get("char_limits", {}).get("linkedin_polished", 3000)
        except Exception:
            pass
    return 3000


def linkedin_register_upload(token: str, urn: str) -> tuple[str, str]:
    """Register an image upload. Returns (upload_url, asset_urn)."""
    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": urn,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    upload_url = body["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset_urn = body["value"]["asset"]
    return upload_url, asset_urn


def linkedin_upload_binary(upload_url: str, token: str, image_path: Path, content_type: str) -> bool:
    with open(image_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        upload_url, data=data, method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status in (200, 201)


def linkedin_post(token: str, urn: str, text: str, asset_urn: str = "",
                  image_title: str = "Image", image_desc: str = "Attached image") -> str:
    """Returns the share URN."""
    specific = {
        "com.linkedin.ugc.ShareContent": {
            "shareCommentary": {"text": text},
        }
    }
    if asset_urn:
        specific["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "IMAGE"
        specific["com.linkedin.ugc.ShareContent"]["media"] = [{
            "status": "READY",
            "description": {"text": image_desc},
            "media": asset_urn,
            "title": {"text": image_title},
        }]
    else:
        specific["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "NONE"
    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": specific,
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/ugcPosts",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["id"]


def archive(post_file: Path, share_urn: str, body: str) -> Path:
    posted_file = POSTED_DIR / post_file.name
    fm, _ = parse_frontmatter(post_file.read_text(encoding="utf-8"))
    fm["status"] = "posted"
    fm["posted_at"] = now_iso()
    fm["linkedin_share_urn"] = share_urn
    fm["linkedin_url"] = f"https://www.linkedin.com/feed/update/{share_urn}"
    fm["body"] = body
    write_frontmatter(posted_file, fm, body)
    post_file.unlink()
    return posted_file


def main():
    parser = argparse.ArgumentParser(description="Post a draft to LinkedIn.")
    parser.add_argument("post_file", help="Path to a queue file")
    parser.add_argument("--image", help="Attach an existing image (PNG/JPG/GIF, max 5MB)")
    parser.add_argument("--capture", help="Activate an app, capture its front window as image")
    parser.add_argument("--image-title", default="Image")
    parser.add_argument("--image-desc", default="Attached image")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Validate + preview only")
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
        return 2

    body_raw = extract_body(post_file)
    body = sanitize(body_raw)
    char_limit = get_char_limit()
    n = len(body)

    print(f"═══ LinkedIn Publish: {post_file.name} ═══")
    print(f"  raw:   {len(body_raw)} chars")
    print(f"  clean: {n} chars (limit {char_limit})")

    ok, msg = validate(body, char_limit)
    if not ok:
        print(f"  ✗ validate: {msg}")
        return 1
    print(f"  ✓ validate: {msg}")

    image_path = None
    if args.capture:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        out = SCREENSHOTS_DIR / f"{ts}-{args.capture}.png"
        if not capture_window(args.capture, out):
            print(f"  ✗ capture: app '{args.capture}' not frontmost or capture failed")
            return 1
        image_path = out
        print(f"  ✓ captured: {image_path.relative_to(VAULT)}")

    if args.image:
        image_path = Path(args.image)
        ok, info = image_ok(image_path)
        if not ok:
            print(f"  ✗ image: {info}")
            return 1
        print(f"  ✓ image: {info}")

    print()
    print("─" * 60)
    print("POST PREVIEW")
    print("─" * 60)
    print(body)
    print("─" * 60)
    print(f"  Length: {n} chars (limit {char_limit})")
    if image_path:
        print(f"  Image: {image_path}")
    print("─" * 60)

    if args.dry_run:
        print("--dry-run: NOT posting.")
        return 0

    if not args.yes:
        confirm = input("Post to LinkedIn? (y/N): ")
        if confirm.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    token = creds["LINKEDIN_ACCESS_TOKEN"]
    urn = creds["LINKEDIN_PERSON_URN"]
    asset_urn = ""
    if image_path:
        ext = image_path.suffix.lower().lstrip(".")
        content_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        upload_url, asset_urn = linkedin_register_upload(token, urn)
        if not linkedin_upload_binary(upload_url, token, image_path, content_type):
            print("  ✗ image upload failed")
            return 1
        print(f"  ✓ asset uploaded: {asset_urn}")

    share_urn = linkedin_post(token, urn, body, asset_urn,
                              image_title=args.image_title, image_desc=args.image_desc)
    posted = archive(post_file, share_urn, body)
    print(f"  ✓ posted: https://www.linkedin.com/feed/update/{share_urn}")
    print(f"  ✓ archived: {posted.relative_to(VAULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
