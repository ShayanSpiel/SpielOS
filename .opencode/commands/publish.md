---
description: Publish queued content to production (X / LinkedIn / Buffer)
---

# /publish — Queue → Production

Publishes queued drafts to the configured platforms.

Usage: `/publish [id|all]`

## Run

```
spiel content publish                # publish all (manual mode asks for confirm)
spiel content publish <id>           # publish one draft (filename, stem, or short ref)
```

## What happens

1. In `manual` mode (default), `spiel` shows the draft and waits for "yes" before the API call.
2. Posts to the platform API (Buffer fan-out → X + LinkedIn + Threads in one call; or direct X/LinkedIn as fallbacks).
3. Archives the draft to `content/posted/`.
4. Updates frontmatter with `posted_at` and platform-specific IDs.

Configure posting mode in `rules.yaml` → `posting.mode` (manual | auto-threshold | auto-always).
