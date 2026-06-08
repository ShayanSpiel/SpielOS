# /extract

**State machine:** Wiki — INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE
**Template:** AGENTS.md

## Usage
```
/extract [source]       # Ingest a raw source file
/extract --link         # Same + run LINKING sub-step
```

## States
- INGESTING: read source, add frontmatter, validate
- ANALYZING: extract entities/concepts, apply threshold rules
- RECONCILING: create/update pages, append never overwrite
- (LINKING): add 0-3 semantic wikilinks
- INDEXING: update index.md and log.md
- VALIDATING: check frontmatter, links, redundancy

## Gates
- Threshold: 2+ sources or core to one → create page
- Redundancy: >60% overlap → update, don't create
- Domain: content must be within wiki domain
- Link health: all [[wikilinks]] point to existing pages
