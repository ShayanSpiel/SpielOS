# /extract — Ingest Raw → Wiki Pages

Extracts content from raw notes and creates wiki pages.

Usage: /extract [file]

1. Runs `bash scripts/pipeline.sh wiki-extract <file>`
2. Advances through INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE
3. Creates or updates wiki pages in pages/
4. Updates index.md and log.md
