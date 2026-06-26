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
    {"from": "capture", "to": "director", "at": "2026-06-26T12:00:05", "by": "post"}
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

The pipeline has 9 steps. They map 1:1 to the 5 roles + capture + complete + error.

| Step | Owner | What happens here |
|---|---|---|
| `idle` | (none) | No active run. `content/.state.json` does not exist, or its `status` is `shipped`/`failed`. |
| `capture` | `/post` | Session capture in progress. Calls `tools/capture-session.py` then advances to `director`. |
| `director` | `@director` | Reads `content/current.md`, resolves the source (session or topic), writes `source:` back, sets `status: drafting`, advances to `strategy`. |
| `strategy` | `@strategist` | Writes `## Strategy` to `content/current.md` (reader, pain, point, proof, angle, formats). Advances to `draft`. |
| `draft` | `@writer` | Writes one draft per format to `content/drafts/`. Appends paths to `state.drafts`. Advances to `edit`. |
| `edit` | `@editor` | Runs `tools/editor.py stamp` on each draft. Moves passing drafts to `content/ready/`. Appends paths to `state.ready`. Advances to `publish`. |
| `publish` | `@publisher` | Per-draft p/h/r. Publishes approved drafts. Archives to `content/posted/` or `content/rejected/`. Advances to `complete`. |
| `complete` | `tools/advance.py` | Sets `status: shipped`, writes `updated_at`, run is done. Next `/post` overwrites the state. |
| `error` | `tools/advance.py --set-error` | Captures the last error. Stays at this step until the user runs `tools/advance.py --reset` or `--recover-from <step>`. |

## Allowed transitions

```
idle       -> capture
capture    -> director
director   -> strategy
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
- `step` is the pipeline step: `idle`, `capture`, `director`, `strategy`, `draft`, `edit`, `publish`, `complete`, `error`.

A paused run is still on a step (e.g. `step: edit, status: paused` means Editor is waiting for human approval before stamping).

## Crash recovery

On `/post` start, if `content/.state.json` exists and `status` is `active` or `paused`, read the `history` array to find the last successful step. Ask the user: "continue from `<step>` or restart?" If continue, jump to that step. If restart, run `tools/advance.py --reset` and start fresh.

The old promise in `AGENTS.md:98` ("read the `## state_history` lines, ask the user") is now real because the state is real.

## `bin/spiel status` (display)

`status` should print:
- The current `step`
- The `run_id`
- `drafts` count
- `ready` count
- `error` if set
- The age of `updated_at`
