# /index

**State machine:** Wiki — INDEXING only
**Template:** AGENTS.md

## Usage
```
/index              # Rebuild index.md from scratch
```

## Action
- Scan all pages in concepts/, entities/, summaries/
- Categorize by type field in frontmatter
- Write to index.md under correct section heading
- Write log entry to log.md
- Update .wiki-state
