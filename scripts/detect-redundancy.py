#!/usr/bin/env python3
"""detect-redundancy.py — Find near-duplicate pages across all wiki directories.

Uses tag overlap, source overlap, and name similarity to flag merge candidates.
Can be imported as a module or run as CLI.

Usage:
    ./scripts/detect-redundancy.py                    # Full report
    ./scripts/detect-redundancy.py --min-score 0.5    # Raise threshold
"""

import os
import yaml
from pathlib import Path
from itertools import combinations

from logger import logged

VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).resolve().parent.parent))
WIKI_DIRS = ["concepts", "entities", "comparisons", "summaries"]

DEFAULT_MIN_SCORE = 0.4
MERGE_THRESHOLD = 0.6


@logged()
def read_frontmatter(filepath):
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return None, ""
    if not content.startswith("---"):
        return None, content
    try:
        _, fm_str, body = content.split("---", 2)
        fm = yaml.safe_load(fm_str)
        return fm, body.strip()
    except (yaml.YAMLError, ValueError):
        return None, content


@logged()
def word_overlap(name1, name2):
    words1 = set(name1.lower().replace("-", " ").split())
    words2 = set(name2.lower().replace("-", " ").split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    return len(intersection) / min(len(words1), len(words2))


@logged()
def tag_overlap(tags1, tags2):
    set1, set2 = set(tags1 or []), set(tags2 or [])
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


@logged()
def source_overlap(sources1, sources2):
    return tag_overlap(sources1, sources2)


@logged()
def load_pages() -> list[dict]:
    """Load all wiki pages with frontmatter data."""
    pages = []
    for dir_name in WIKI_DIRS:
        dir_path = VAULT / dir_name
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.md")):
            fm, body = read_frontmatter(f)
            if fm:
                pages.append({
                    "slug": f"{dir_name}/{f.stem}",
                    "tags": fm.get("tags", []),
                    "sources": fm.get("sources", []),
                    "filepath": f,
                })
    return pages


@logged()
def find_candidates(pages: list[dict] = None, min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """Return sorted list of near-duplicate candidate pairs (score >= min_score)."""
    if pages is None:
        pages = load_pages()
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


@logged()
def run():
    pages = load_pages()
    candidates = find_candidates(pages)
    print("═══ Redundancy Detection ═══")
    print(f"Scanning {len(pages)} pages across: {', '.join(WIKI_DIRS)}")
    print()
    if not candidates:
        print("No near-duplicate pairs found.")
        return
    print(f"Found {len(candidates)} candidate pairs (score >= {DEFAULT_MIN_SCORE}):")
    print()
    for c in candidates[:20]:
        flag = "⚠ MERGE" if c["score"] >= MERGE_THRESHOLD else "  review"
        print(f"{flag}  {c['a']} ↔ {c['b']}")
        print(f"       score: {c['score']:.2f}  (words: {c['word_overlap']:.2f}, "
              f"tags: {c['tag_overlap']:.2f}, sources: {c['source_overlap']:.2f})")
    if len(candidates) > 20:
        print(f"\n... and {len(candidates) - 20} more.")


if __name__ == "__main__":
    import sys
    if "--min-score" in sys.argv:
        idx = sys.argv.index("--min-score")
        DEFAULT_MIN_SCORE = float(sys.argv[idx + 1])
    run()
