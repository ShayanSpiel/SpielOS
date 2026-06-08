# /reconcile

**State machine:** Wiki — RECONCILING only
**Template:** AGENTS.md

## Usage
```
/reconcile [page]   # Re-read source → update existing page
```

## Action
- Read the page's source file from raw/
- Diff current page content with source
- Append new information (never overwrite)
- Preserve contradictions with date-stamped notes
- Bump frontmatter updated date
- Proceed to INDEXING → VALIDATING
