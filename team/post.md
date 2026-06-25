---
name: post
description: Dispatch a /post request. Always captures the current session, writes the execution context to content/current.md, then invokes @director.
---

# /post

You are the parent agent. You HAVE the live transcript of this conversation.

## Step 1 — Capture the session (always)

From your own context, compile a structured digest:

- Built / changed: ...
- Shipped: ...
- Decisions: ...
- Discoveries / surprises: ...
- Open questions: ...

Run:

```bash
python3 tools/capture-session.py \
  --vault "$VAULT_DIR" \
  --transcript-string "<your digest>" \
  --status complete
```

Capture the `path` field from the JSON output (e.g. `content/sessions/2026-06-25-session-current.md`).

If the conversation is genuinely empty, pass a single line like "empty session" as the digest — the tool will still write a log so the Director knows there was nothing to capture.

## Step 2 — Build execution context

Parse the args after `/post`:

- **No args** → `mode: session`, `input: ""`
- **Args present** → `mode: topic`, `input: "<args>"`

Write `content/current.md`:

```yaml
---
mode: session | topic
input: "<args or empty>"
session: content/sessions/YYYY-MM-DD-session-current.md
status: routing
run_id: YYYY-MM-DD-NNN
---
```

## Step 3 — Dispatch

Invoke `@director` with:

> "Read `content/current.md` and run the pipeline."

## Hard rules

- ALWAYS run capture-session.py, even when args are present.
- Parent does NOT decide content — only the execution context shape.
- Director does NOT ask the user what mode — `mode:` in current.md is the source of truth.
- Do NOT pass raw chat history. Always compile a structured digest first.
- Do NOT skip Step 1.
