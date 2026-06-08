# /publish

**State machine:** Content — QUEUE → PUBLISH → ARCHIVE
**Template:** AGENTS.md

## Usage
```
/publish [id|all]   # Publish specific draft or all queued
```

## Behavior
- Checks .content-config for posting mode (manual/auto-threshold/auto-always)
- Manual mode: shows draft, waits for "yes" before API call
- Auto-threshold: auto-publishes if composite gate score >= threshold
- Posts to platform API (X, LinkedIn) or keeps as ready-to-publish (blog)
- On failure: sets status: api-failed, reports to user
- On success: moves to content/posted/, updates frontmatter
