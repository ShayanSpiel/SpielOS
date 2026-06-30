# Run State

One state file per vault. Atomic writes. Vault-resolved.

**Path:** `content/.state.json`

**Writer:** `tools/advance.py` (validates transitions, atomic write).

## Shape

```json
{
  "run_id": "2026-06-26-001",
  "status": "routing",
  "step": "capture",
  "mode": "session",
  "current": "content/current.md",
  "session": "content/sessions/2026-06-26-session-current.md",
  "drafts": [],
  "ready": [],
  "updated_at": "2026-06-26T12:00:00",
  "error": null,
  "history": [
    {"from": "idle", "to": "capture", "at": "2026-06-26T12:00:00", "by": "post"},
    {"from": "capture", "to": "strategy", "at": "2026-06-26T12:00:05", "by": "post"}
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | `YYYY-MM-DD-NNN`, from `content/.run-counter` |
| `status` | string | `routing` (not yet started), `active` (in progress), `paused` (waiting human), `shipped` (complete), `failed` (error) |
| `step` | string | Current pipeline step (see below) |
| `mode` | string | `session` (from `/post` no args) or `topic` (from `/post "text"`) |
| `current` | string | Relative path to the handoff file (`content/current.md`) |
| `session` | string | Relative path to the session log (only when `mode: session`) |
| `drafts` | list[str] | Relative paths to drafts written by the Writer |
| `ready` | list[str] | Relative paths to drafts that passed Editor gates |
| `updated_at` | string | ISO 8601 timestamp of last transition |
| `error` | string\|null | Last error message (or null) |
| `history` | list[obj] | Append-only log of every transition |

## Steps

The pipeline has 7 steps. They map 1:1 to the 4 roles + capture + complete + error.

| Step | Owner | What happens here |
|---|---|---|
| `idle` | (none) | No active run. `content/.state.json` does not exist, or its `status` is `shipped`/`failed`. |
| `capture` | `spiel post` | Runtime input capture in progress. `tools/post.py` normalizes topic/file/session input, calls `tools/capture-session.py` for session mode, then advances to `strategy`. |
| `strategy` | `@strategist` | Writes `## Strategy` to `content/current.md` (reader, pain, point, proof, angle, formats). Advances to `draft`. |
| `draft` | `@writer` | Writes one draft per format to `content/drafts/`. Appends paths to `state.drafts`. Advances to `edit`. |
| `edit` | `@editor` | Runs `tools/editor.py stamp` on each draft. Moves passing drafts to `content/ready/`. Appends paths to `state.ready`. Advances to `publish`. |
| `publish` | `@publisher` | Per-draft p/h/r. Publishes approved drafts. Archives to `content/posted/` or `content/rejected/`. Advances to `complete`. |
| `complete` | `tools/advance.py` | Sets `status: shipped`, writes `updated_at`, run is done. Next `/post` overwrites the state. |
| `error` | `tools/advance.py --set-error` | Captures the last error. Stays at this step until the user runs `tools/advance.py --reset` or `--recover-from <step>`. |

## Allowed transitions

```
idle       -> capture
capture    -> strategy
strategy   -> draft
draft      -> edit
edit       -> publish
publish    -> complete
complete   -> idle

any step   -> error
error      -> idle       (via --reset)
error      -> <previous> (via --recover-from <step>)
```

`tools/advance.py --to <step>` validates the transition. If the transition is not allowed, exit code 2 and a clear error.

## What "status" means vs "step"

- `status` is the run-level lifecycle: `routing` (not started), `active` (in progress), `paused` (waiting human), `shipped` (done), `failed` (errored).
- `step` is the pipeline step: `idle`, `capture`, `strategy`, `draft`, `edit`, `publish`, `complete`, `error`.

A paused run is still on a step (e.g. `step: edit, status: paused` means Editor is waiting for human approval before stamping).

## Crash recovery

On `/post` start, `tools/post.py` **auto-resets and starts fresh.** At the top of `main()` it deletes `content/.state.json` and `content/current.md` if they exist, then begins the new run. The LLM never has to reason about a stuck prior state. Bare `/post` and any `/post <topic>` invocation discards the prior run, if any, and starts a new one. There is no resume; to continue a paused run the user must use the per-role commands (`@strategist`, `@writer`, `@editor`, `@publisher`) or `spiel continue` from outside the `/post` adapter.

## `bin/spiel status` (display)

`status` should print:
- The current `step`
- The `run_id`
- `drafts` count
- `ready` count
- `error` if set
- The age of `updated_at`
