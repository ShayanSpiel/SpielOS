---
description: Run wiki health checks (orphans, links, frontmatter, redundancy)
---

# /health — Wiki Health Check

Read-only health check. Safe to run any time.

Usage: `/health`

## Run

```
spiel wiki health
```

## What it checks

1. Orphans (pages with no inbound links)
2. Broken wikilinks
3. Frontmatter completeness
4. Stale pages (low confidence, no recent update)
5. Redundancy candidates (overlap >60%)
6. Missing-from-index pages
