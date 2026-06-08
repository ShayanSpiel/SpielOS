# /relink

**State machine:** Wiki — LINKING only
**Template:** AGENTS.md

## Usage
```
/relink [page]      # Rebuild cross-links for a page
```

## Action
- Scan page body for existing [[wikilinks]]
- Search other pages for natural link targets
- Add 0-3 relevant wikilinks
- NEVER force a link that doesn't add meaning
- Proceed to INDEXING → VALIDATING
