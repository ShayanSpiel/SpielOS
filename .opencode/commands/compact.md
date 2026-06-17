---
description: Compact wiki — merge redundant pages and refresh index
---

# /compact — Compact Wiki

Merges redundant or overlapping pages and compacts the wiki index.

Usage: `/compact`

## Run

```
spiel wiki validate
# Then review the redundancy candidates listed in the report and merge by hand.
```

For now, `/compact` is a manual review step. The engine surfaces candidates via `spiel wiki health` (redundancy section) but does not auto-merge.
