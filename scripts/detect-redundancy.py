#!/usr/bin/env python3
"""Content overlap detection — find pages with >60% content overlap."""

import os
import re
import sys
from pathlib import Path

WIKI_ROOT = Path(os.environ.get("WIKI_ROOT", ".")).resolve()
OVERLAP_THRESHOLD = float(os.environ.get("OVERLAP_THRESHOLD", "0.6"))
DIRS = ["concepts", "entities", "summaries"]

def tokenize(content):
    content = re.sub(r"^---.*?---", "", content, flags=re.DOTALL)
    content = re.sub(r"[^a-zA-Z0-9\s]", "", content)
    return set(content.lower().split())

def jaccard_similarity(tokens1, tokens2):
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1 & tokens2) / len(tokens1 | tokens2)

def main():
    pages = {}
    for d in DIRS:
        dir_path = WIKI_ROOT / d
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.md"):
            content = f.read_text()
            pages[f.name] = {"path": f, "tokens": tokenize(content)}

    names = list(pages.keys())
    overlaps = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            sim = jaccard_similarity(pages[names[i]]["tokens"], pages[names[j]]["tokens"])
            if sim >= OVERLAP_THRESHOLD:
                overlaps.append((names[i], names[j], sim))

    overlaps.sort(key=lambda x: -x[2])

    print(f"Content overlap check — {len(pages)} pages\n")
    print(f"Overlap threshold: {OVERLAP_THRESHOLD:.0%}")
    print(f"Overlapping pairs: {len(overlaps)}\n")

    for a, b, sim in overlaps:
        print(f"  {sim:.0%}  {a}  ↔  {b}")

    if overlaps:
        print(f"\nSuggestion: consider merging or clarifying these pairs.")
        sys.exit(1)

if __name__ == "__main__":
    main()
