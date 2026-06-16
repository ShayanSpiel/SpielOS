---
description: Publish queued content to production (X / LinkedIn)
---

# /publish — Queue → Production

Publishes queued content to production endpoints.

Usage: /publish [id|all]

1. Shows draft and waits for confirmation (manual mode)
2. Posts to platform API
3. Archives to content/posted/
4. Updates frontmatter with published_at and platform-specific IDs

Configure posting mode in rules.yaml: manual | auto-threshold | auto-always.
