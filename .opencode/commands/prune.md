---
description: Identify and remove stale or low-confidence pages
---

# /prune — Prune Stale Pages

Identifies and removes stale or low-confidence pages.

Usage: `/prune [--dry-run]`

## Run

```
spiel wiki health       # surfaces stale + low-confidence pages
# Then delete by hand after review.
```

The engine does not auto-delete. Always review the report first.
