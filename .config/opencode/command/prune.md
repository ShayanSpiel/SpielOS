# /prune

**State machine:** Wiki — maintenance state
**Template:** AGENTS.md

## Usage
```
/prune              # Archive stale pages, merge duplicates
```

## Actions
- Move stale pages (no update in 90+ days) to _archive/
- Merge duplicate pages with >60% overlap
- Remove orphan pages with no meaningful content
- Update all [[wikilinks]] pointing to archived pages → "(archived)"
- Rebuild index.md and log entries
