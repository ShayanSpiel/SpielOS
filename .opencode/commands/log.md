---
description: Show recent activity log entries
---

# /log — Recent Log Entries

Shows recent JSONL log entries from `logs/`.

Usage: `/log [flags]`

## Run

```
spiel log --tail 20
spiel log --days 7
spiel log --level ERROR
spiel log --source pipeline.sh
```

## Flags

- `--days N`      look back N days (default 7)
- `--tail N`      show last N entries (default 30)
- `--level X`     filter by level (INFO, WARN, ERROR, ...)
- `--source X`    filter by source module
