#!/usr/bin/env python3
"""Wiki health checker — orphan pages, broken links, stale pages, frontmatter completeness."""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WIKI_ROOT = Path(os.environ.get("WIKI_ROOT", ".")).resolve()
STALE_DAYS = int(os.environ.get("STALE_DAYS", "90"))
DIRS = ["concepts", "entities", "summaries"]

def find_all_pages():
    pages = {}
    for d in DIRS:
        dir_path = WIKI_ROOT / d
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.md"):
            content = f.read_text()
            frontmatter = extract_frontmatter(content)
            pages[f.name] = {
                "path": f,
                "links": extract_wikilinks(content),
                "frontmatter": frontmatter,
                "content": content,
            }
    return pages

def extract_frontmatter(content):
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
    return fm

def extract_wikilinks(content):
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)

def find_orphans(pages):
    all_links = set()
    for name, data in pages.items():
        all_links.update(data["links"])
    orphans = []
    for name in pages:
        if name.replace(".md", "") not in all_links and name != "index.md":
            orphans.append(name)
    return orphans

def find_broken_links(pages):
    page_names = {p.replace(".md", "") for p in pages}
    broken = []
    for name, data in pages.items():
        for link in data["links"]:
            if link not in page_names:
                broken.append((name, link))
    return broken

def find_stale(pages):
    now = datetime.now(timezone.utc)
    stale = []
    for name, data in pages.items():
        updated = data["frontmatter"].get("updated", "")
        if not updated:
            stale.append((name, "no updated date"))
            continue
        try:
            updated_date = datetime.strptime(updated.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            stale.append((name, f"invalid updated date: {updated}"))
            continue
        days_old = (now - updated_date).days
        if days_old > STALE_DAYS:
            stale.append((name, f"{days_old} days since update"))
    return stale

def check_frontmatter(pages):
    required = ["title", "created", "updated", "type", "tags"]
    issues = []
    for name, data in pages.items():
        fm = data["frontmatter"]
        for field in required:
            if field not in fm or not fm[field]:
                issues.append((name, f"missing frontmatter field: {field}"))
    return issues

def main():
    pages = find_all_pages()
    if not pages:
        print("No pages found.")
        sys.exit(0)

    orphans = find_orphans(pages)
    broken_links = find_broken_links(pages)
    stale = find_stale(pages)
    fm_issues = check_frontmatter(pages)

    print(f"Wiki health check — {len(pages)} pages\n")
    print(f"Orphans: {len(orphans)}")
    for o in orphans:
        print(f"  - {o}")
    print(f"\nBroken links: {len(broken_links)}")
    for src, tgt in broken_links:
        print(f"  - {src} → [[{tgt}]]")
    print(f"\nStale pages (>={STALE_DAYS} days): {len(stale)}")
    for name, reason in stale:
        print(f"  - {name} ({reason})")
    print(f"\nFrontmatter issues: {len(fm_issues)}")
    for name, issue in fm_issues:
        print(f"  - {name}: {issue}")

    if any([orphans, broken_links, stale, fm_issues]):
        sys.exit(1)

if __name__ == "__main__":
    main()
