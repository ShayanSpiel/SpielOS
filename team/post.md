---
name: post
description: Route /post to the content pipeline. Write context, invoke @director.
---

# /post

## Parse mode

| Input | Mode |
|---|---|
| `/post <text>` | **topic** — `input: "<text>"` |
| `/post` (no args) | **session** — capture conversation |

## Generate run_id

Read `{vault_root}/content/.run-counter` (JSON: `{date, n}`).
Same date as today → `n+1`. Else `n=1`. Write back.
`run_id = {date}-{n:03d}`

## Write files

### Topic mode → `{vault_root}/content/current.md`

```yaml
---
mode: topic
input: "<exact text after /post>"
status: routing
run_id: <from above>
created_at: <ISO 8601>
---
```

### Session mode

1. Collect ALL user + assistant messages from conversation. Strip tool calls, tool results, system messages. Keep text only.
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
<message text>
### 2
...
## Assistant Messages
### 1
<message text>
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

Invoke @director. No explanation. No output.

## Hard rules

- Use `{vault_root}` paths only. Never cwd.
- Never explain actions, show thinking, or output preamble.
- Never ask the user anything.
- No em-dashes in any file content.
- `/post <text>` where `text` contains file references (e.g. `@file:./notes.md`) — open the file, read it, use its contents as the input. The prompt must treat `@file:` links as input to research and incorporate.
