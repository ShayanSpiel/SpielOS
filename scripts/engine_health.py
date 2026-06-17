#!/usr/bin/env python3
"""engine_health.py — Wiki health checks + redundancy detection.

Pure functions. No file I/O. Kernel loads data and calls these.
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations


def extract_wikilinks(content: str) -> list[str]:
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)


def check_orphans(all_pages: dict[str, any], all_links: list[str]) -> list[str]:
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


def check_broken_links(all_pages: dict[str, any],
                       all_page_links: dict[str, list[str]]) -> list[tuple[str, str]]:
    broken = []
    for source, links in all_page_links.items():
        for target in links:
            if target not in all_pages:
                broken.append((source, target))
    return sorted(broken)


def check_stale(all_pages: dict[str, any],
                stale_days: int = 90) -> list[tuple[str, str]]:
    stale = []
    cutoff = datetime.now() - timedelta(days=stale_days)
    for page_key, (fm, _) in all_pages.items():
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
        raw_sources = fm.get("sources", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        for src in raw_sources:
            pass  # stale source check requires file mtime, done by kernel
    return stale


def check_crosslink_health(all_pages: dict[str, any],
                           all_page_links: dict[str, list[str]]) -> tuple[list[str], list[str]]:
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


def check_index_completeness(all_pages: dict[str, any],
                             index_content: str) -> list[str]:
    missing = []
    for page_key in all_pages:
        wikilink = f"[[{page_key}]]"
        if wikilink not in index_content:
            missing.append(page_key)
    return missing


def word_overlap(name1: str, name2: str) -> float:
    words1 = set(name1.lower().replace("-", " ").split())
    words2 = set(name2.lower().replace("-", " ").split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    return len(intersection) / min(len(words1), len(words2))


def tag_overlap(tags1: list, tags2: list) -> float:
    set1, set2 = set(tags1 or []), set(tags2 or [])
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def source_overlap(sources1: list, sources2: list) -> float:
    return tag_overlap(sources1, sources2)


def find_redundancy_candidates(pages: list[dict],
                               min_score: float = 0.4) -> list[dict]:
    candidates = []
    for a, b in combinations(pages, 2):
        w_score = word_overlap(a["slug"], b["slug"])
        t_score = tag_overlap(a["tags"], b["tags"])
        s_score = source_overlap(a["sources"], b["sources"])
        combined = (w_score * 0.3) + (t_score * 0.4) + (s_score * 0.3)
        if combined >= min_score:
            candidates.append({
                "a": a["slug"],
                "b": b["slug"],
                "score": combined,
                "word_overlap": w_score,
                "tag_overlap": t_score,
                "source_overlap": s_score,
            })
    return sorted(candidates, key=lambda x: x["score"], reverse=True)
