---
description: Remove a draft from the queue
---

# /reject — Reject a Draft

Removes a draft from the queue.

Usage: `/reject <file>`

## Run

```
rm "$(spiel --where)/content/queue/<file>.md"
```

Drafts are plain markdown files — removing the file is the rejection. To reject and archive, move it to `content/rejected/` instead.
