# /schedule

**State machine:** Content — QUEUE (with scheduled field)
**Template:** AGENTS.md

## Usage
```
/schedule [id] [date]   # Schedule draft for later publish
```

## Action
- Read draft from content/queue/
- Add scheduled_at field to frontmatter
- Draft stays in queue but with future publish date
- /publish honors scheduled_at (skips until date)
