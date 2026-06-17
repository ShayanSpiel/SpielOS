---
description: Set publish timestamps for queued content
---

# /schedule — Schedule Content

Sets publish timestamps for queued content (Buffer handles the actual scheduling).

Usage: `/schedule <file> <datetime>`

## Run

```
spiel content publish <file> --queue
```

`--queue` mode adds the draft to Buffer's queue without sending immediately. Buffer schedules the post per its own queue rules.
