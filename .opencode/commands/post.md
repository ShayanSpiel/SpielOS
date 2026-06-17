---
description: Start content pipeline — session or topic mode. Drives the full engine from IDLE through publish.
---

# /post — Start Content Pipeline

Delegates to the `@post` subagent, which runs the full orchestrator loop end-to-end. The shim `spiel` is path-independent, so this works from any project or IDE.

## How it runs

The subagent invokes `spiel content run` once per turn. `spiel` is a thin wrapper at `~/.local/bin/spiel` that resolves `VAULT_DIR` from `~/.config/opencode/.env` and execs the engine inside the vault — from any cwd.

```
spiel content run          # IDLE → SESSION_CAPTURE → COMPILE (handoff)
...LLM runs 8-step Compiler...
spiel content compile-write --core-insight "..." --meaning-systemic "..." ... --selected-axis human --selected-rationale "..."
spiel content run          # SELECT → FORMAT_WIZARD (human checkpoint)
spiel content wizard       # human picks x/linkedin/blog
spiel content run          # DRAFTING (handoff)
...LLM writes drafts to content/queue/...
spiel content draft-write --file content/queue/<name>.md   # repeat per draft
spiel content draft-done
spiel content run          # BANNER → GATE_CHECK → QUEUE (human checkpoint)
spiel content publish-wizard   # human picks publish/hold per draft
spiel content run          # PUBLISHING → ARCHIVING → COMPLETE
```

After the loop, run `spiel content banner` (already auto-invoked) and then `spiel content publish` if you held any drafts.

## Mode 1 (empty): session from today's log

If today's session log exists, the engine auto-loads it. If not, a stub is created and the human fills it in (this is by design — never ask "what did you work on?").

## Mode 2 (`/post <topic>`): topic mode

Creates a brief for the given topic. The Compiler runs on the topic instead of a session.

## Full pipeline spec

`~/.config/opencode/skill/spiel-content/SKILL.md` — the subagent owns the pipeline; the LLM never interprets `/post` itself.
