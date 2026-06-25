---
name: post
description: Dispatch a /post request. Parse mode, capture session, write execution context, invoke @director.
---

# /post

## Parse mode

- `/post <text>` → **topic** — `input: "<text>"`
- `/post` (no args) → **session** — capture conversation
- If `<text>` contains `@file:./path` references → read each file, use contents as input

## Generate run_id

Read `{vault_root}/content/.run-counter` (JSON: `{date, n}`).
Same date as today → `n+1`. Else `n=1`. Write back.
`run_id = {date}-{n:03d}`

## Write files

### Topic mode → `{vault_root}/content/current.md`

```yaml
---
mode: topic
input: "<exact text after /post, or file contents if @file: used>"
status: routing
run_id: <from above>
created_at: <ISO 8601>
---
```

### Session mode

1. Collect ALL user + assistant text from conversation. Strip tool calls, tool results, system messages.
2. Write `{vault_root}/content/sessions/current.md`:
```yaml
---
date: <YYYY-MM-DD>
mode: session
captured_at: <ISO 8601>
user_messages: <count>
assistant_messages: <count>
tool_calls: <count>
---
# Session Capture
## User Messages
### 1
<text>
...
## Assistant Messages
### 1
<text>
...
```
3. Write `{vault_root}/content/current.md`:
```yaml
---
mode: session
session: content/sessions/current.md
status: routing
run_id: <from above>
created_at: <ISO 8601>
---
```

## Delegate

Invoke @director. No explanation. No preamble.

## Hard rules

- Use `{vault_root}` paths only. Never cwd.
- Never explain, show thinking, or output preamble.
- Never ask the user anything.
- No em-dashes in any file content.
- Files already exist from the hook? Skip writing, go straight to delegation.
