---
description: Ingest raw notes and create wiki pages
---

# /extract — Ingest Raw → Wiki Pages

Extracts content from `raw/*.md` notes and reconciles into wiki pages.

Usage: `/extract [file]`

## Run

```
spiel wiki extract                    # ingest all unprocessed files in raw/
spiel wiki extract notes/foo.md       # ingest one specific file (path relative to vault)
```

## What happens

1. Adds frontmatter to each file; validates domain against the allow-list.
2. Advances through INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE.
3. Creates or updates wiki pages in `entities/`, `concepts/`, etc.
4. Updates `index.md` and `log.md`.

`spiel` resolves the vault from `~/.config/opencode/.env`, so this works from any project cwd.
