#!/usr/bin/env python3
"""wiki-health.py — Automated health checks for the Spiel Engine.

7 checks:
  1. Orphan pages (0 inbound wikilinks)
  2. Broken [[wikilinks]] (target doesn't exist)
  3. Frontmatter validation (required fields + taxonomy)
  4. Stale content (updated >90 days OR raw source newer)
  5. Redundancy scan (tag/source/name overlap — merge candidates)
  6. Index completeness (every page listed in index.md)
  7. Cross-link health (dead ends + thin links)

Does not modify any files.
"""

import os
import re
import sys
import yaml
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from logger import logged

# Import detect-redundancy (hyphen in filename, so use importlib)
_redundancy_spec = importlib.util.spec_from_file_location(
    "detect_redundancy",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "detect-redundancy.py"),
)
redundancy = importlib.util.module_from_spec(_redundancy_spec)
_redundancy_spec.loader.exec_module(redundancy)

VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).resolve().parent.parent))
WIKI_DIRS = ["concepts", "entities", "comparisons", "summaries", "templates"]
SPECIAL_PAGES = {"index": VAULT / "index.md", "log": VAULT / "log.md"}
STALE_DAYS = 90


@logged()
def get_markdown_files(directory):
    path = VAULT / directory
    if not path.exists():
        return []
    return sorted([f for f in path.iterdir() if f.suffix == ".md"])


@logged()
def read_frontmatter(filepath):
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    _, fm, _ = content.split("---", 2)
    try:
        return yaml.safe_load(fm)
    except yaml.YAMLError:
        return None


@logged()
def extract_wikilinks(content):
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)


@logged()
def load_valid_tags() -> set:
    """Parse valid tags from SCHEMA.md Tag Taxonomy section."""
    schema_path = VAULT / "SCHEMA.md"
    if not schema_path.exists():
        return set()
    content = schema_path.read_text()
    # Extract everything between "## Tag Taxonomy" and next "## "
    m = re.search(r"## Tag Taxonomy\n(.*?)(?=\n## )", content, re.DOTALL)
    if not m:
        return set()
    section = m.group(1)
    tags = set()
    for line in section.split("\n"):
        line = line.strip()
        line_match = re.match(r"^- (.+)$", line)
        if line_match:
            tag = line_match.group(1).strip()
            tags.add(tag)
    return tags


# ─── Check functions ─────────────────────────────────────────────────────────

@logged()
def check_orphans(all_pages, all_links):
    no_link_required = {"index", "log", "AGENTS", "README", "SCHEMA",
                        "comparison", "entity", "summary", "wiki-note"}
    inbound = defaultdict(int)
    for target in all_links:
        inbound[target] += 1
    orphans = []
    for page_key in all_pages:
        if page_key in no_link_required:
            continue
        if inbound.get(page_key, 0) == 0:
            orphans.append(page_key)
    return sorted(orphans)


@logged()
def check_broken_links(all_pages, all_page_links):
    broken = []
    for source, links in all_page_links.items():
        for target in links:
            if target not in all_pages:
                broken.append((source, target))
    return sorted(broken)


@logged()
def check_frontmatter(all_pages):
    issues = []
    valid_tags = load_valid_tags()
    required = ["title", "created", "updated", "type", "tags", "sources"]
    for page_key, filepath in sorted(all_pages.items()):
        fm = read_frontmatter(filepath)
        if fm is None:
            issues.append((page_key, "no frontmatter"))
            continue
        for field in required:
            if field not in fm or fm[field] is None:
                issues.append((page_key, f"missing field: {field}"))
        # Taxonomy check: validate tags against SCHEMA.md
        if valid_tags and fm.get("tags"):
            page_tags = fm["tags"]
            if isinstance(page_tags, str):
                page_tags = [page_tags]
            bad_tags = [t for t in page_tags if t not in valid_tags]
            if bad_tags:
                issues.append((page_key, f"tags not in taxonomy: {', '.join(bad_tags)}"))
    return issues


@logged()
def check_stale(all_pages):
    stale = []
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)
    for page_key, filepath in sorted(all_pages.items()):
        fm = read_frontmatter(filepath)
        if not fm:
            continue

        updated_str = fm.get("updated")
        if updated_str:
            try:
                updated = datetime.strptime(str(updated_str), "%Y-%m-%d")
                if updated < cutoff:
                    stale.append((page_key, f"last updated {(datetime.now() - updated).days} days ago"))
            except (ValueError, TypeError):
                stale.append((page_key, "bad updated date format"))

        # Raw source staleness: check if any source file is newer than page's updated date
        raw_sources = fm.get("sources", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        for src in raw_sources:
            src_path = VAULT / src if src.startswith("raw/") else VAULT / "raw" / src
            if not src_path.exists():
                continue
            src_mtime = datetime.fromtimestamp(src_path.stat().st_mtime)
            if updated_str:
                try:
                    updated = datetime.strptime(str(updated_str), "%Y-%m-%d")
                    if src_mtime > updated:
                        stale.append((page_key, f"source updated {src_path.name} (page not reconciled)"))
                except (ValueError, TypeError):
                    pass
    return stale


@logged()
def check_crosslink_health(all_pages, all_page_links):
    INFRA = {"index", "log", "AGENTS", "README", "SCHEMA",
             "comparison", "entity", "summary", "wiki-note"}
    dead_ends = []
    thin = []
    for page_key, links in sorted(all_page_links.items()):
        if page_key in INFRA:
            continue
        outbound = [l for l in links if l in all_pages]
        if len(outbound) == 0:
            dead_ends.append(page_key)
        elif len(outbound) == 1:
            thin.append(page_key)
    return dead_ends, thin


@logged()
def check_index_completeness(all_pages):
    index_path = VAULT / "index.md"
    if not index_path.exists():
        return list(all_pages.keys())
    index_content = index_path.read_text(encoding="utf-8")
    missing = []
    for page_key in all_pages:
        wikilink = f"[[{page_key}]]"
        if wikilink not in index_content:
            missing.append(page_key)
    return missing


# ─── Output ──────────────────────────────────────────────────────────────────

@logged()
def run():
    # Build page index
    all_pages = {}
    for d in WIKI_DIRS:
        for f in get_markdown_files(d):
            all_pages[f.stem] = f
    for key, path in SPECIAL_PAGES.items():
        all_pages[key] = path

    INFRA_PAGES = {"index", "log", "AGENTS", "README", "SCHEMA",
                   "comparison", "entity", "summary", "wiki-note"}
    all_links = []
    all_page_links = {}
    for page_key, filepath in all_pages.items():
        if page_key in INFRA_PAGES:
            all_page_links[page_key] = []
            continue
        content = filepath.read_text(encoding="utf-8")
        links = extract_wikilinks(content)
        all_links.extend(links)
        all_page_links[page_key] = links

    critical = []
    warnings = []
    info = []
    check_results = {}  # check_name -> True (ok) or False (has issues)

    # ─── Aggregation ───────────────────────────────────────────────────
    # Each check returns (has_critical_or_warning, items_by_severity)
    # The items list is appended to the global lists; the boolean tracks PASS count.

    def note(crit, warn, inf):
        critical.extend(crit)
        warnings.extend(warn)
        info.extend(inf)
        return len(crit) > 0 or len(warn) > 0

    # 1. Orphans
    orphans = check_orphans(all_pages, all_links)
    inf = [f"orphan: [[{p}]] has 0 inbound links" for p in orphans]
    failed = note([], [], inf)
    check_results["Orphans"] = not failed

    # 2. Broken links
    broken = check_broken_links(all_pages, all_page_links)
    crit = [f"broken-link: [[{s}]] \u2192 [[{t}]] (target missing)" for s, t in broken]
    failed = note(crit, [], [])
    check_results["Broken links"] = not failed

    # 3. Frontmatter validation
    fm_issues = check_frontmatter(all_pages)
    fm_warn = []
    fm_inf = []
    for page, issue in fm_issues:
        msg = f"frontmatter: [[{page}]] \u2014 {issue}"
        if "no frontmatter" in issue:
            fm_warn.append(msg)
        else:
            fm_inf.append(msg)
    failed = note([], fm_warn, fm_inf)
    check_results["Frontmatter"] = not failed

    # 4. Stale content
    stale = check_stale(all_pages)
    stale_items = [f"stale: [[{p}]] {reason}" for p, reason in stale]
    failed = note([], stale_items, [])
    check_results["Stale content"] = not failed

    # 5. Redundancy scan
    redun_candidates = redundancy.find_candidates()
    merge_candidates = [c for c in redun_candidates if c["score"] >= 0.6]
    redun_warn = []
    if merge_candidates:
        tops = merge_candidates[:3]
        pairs = [f"{c['a']} \u2194 {c['b']}" for c in tops]
        redun_warn.append(f"merge candidates: {', '.join(pairs)}")
    redun_inf = [f"redundant: {c['a']} \u2194 {c['b']} (score {c['score']:.2f})" for c in redun_candidates[:5]]
    failed = note([], redun_warn, redun_inf)
    check_results["Redundancy"] = not failed

    # 6. Index completeness
    index_missing = check_index_completeness(all_pages)
    index_inf = [f"index: [[{p}]] not listed in index.md" for p in index_missing]
    failed = note([], [], index_inf)
    check_results["Index"] = not failed

    # 7. Cross-link health
    dead_ends, thin = check_crosslink_health(all_pages, all_page_links)
    cross_warn = [f"dead-end: [[{p}]] has 0 outbound links" for p in dead_ends]
    cross_warn += [f"thin-link: [[{p}]] has only 1 outbound link" for p in thin]
    failed = note([], cross_warn, [])
    check_results["Cross-links"] = not failed

    # ── Output ──────────────────────────────────────────────────────────
    total_checks = 7
    passed = sum(1 for ok in check_results.values() if ok)

    print("/health \u2014 Full Wiki Health Check")
    print("\u2550" * 40)
    print(f"PASS: {passed}/{total_checks} checks")
    print("\u2500" * 12)
    print(f"Critical ({len(critical)}):")
    for c in critical:
        print(f"  \u00b7 {c}")
    print(f"Warnings ({len(warnings)}):")
    for w in warnings:
        print(f"  \u00b7 {w}")
    print(f"Info ({len(info)}):")
    for i in info:
        print(f"  \u00b7 {i}")
    print("\u2500" * 12)

    suggestions = []
    if orphans or merge_candidates:
        suggestions.append("/prune (review orphans + merges)")
    if critical:
        for c in critical:
            if "broken-link" in c:
                pages = re.findall(r"\[\[([^\]]+)\]\]", c)
                if len(pages) >= 2:
                    suggestions.append(f"/reconcile or create missing target for [[{pages[1]}]]")
    if warnings:
        for w in warnings:
            if w.startswith("stale:"):
                page = w.split("[[")[1].split("]]")[0]
                suggestions.append(f"/reconcile {page}")
            elif w.startswith("dead-end:"):
                page = w.split("[[")[1].split("]]")[0]
                suggestions.append(f"/relink {page}")
            elif w.startswith("thin-link:"):
                page = w.split("[[")[1].split("]]")[0]
                suggestions.append(f"/relink {page}")
    suggestions = suggestions[:5]

    if suggestions:
        print("Suggested actions:")
        for s in suggestions:
            print(f"  \u00b7 {s}")
    if not critical and not warnings and not info:
        print("No issues found.")


if __name__ == "__main__":
    run()
