# /health

**State machine:** Wiki — VALIDATING (cross-page)
**Template:** AGENTS.md

## Usage
```
/health             # Run full wiki health check
```

## Checks
- Orphan pages (no inbound [[wikilinks]])
- Broken [[wikilinks]] (point to non-existent pages)
- Stale pages (no update in 90+ days)
- Missing frontmatter fields
- Redundancy (>60% overlap between pages)
