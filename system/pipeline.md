# Pipeline

SpielOS is a lean role-based marketing team with a deterministic state machine.

```text
IDLE → CAPTURE → DIRECTOR → STRATEGY → DRAFT → EDIT → PUBLISH → COMPLETE → IDLE
                          ↑                                                          ↓
                          └────────────────  ERROR  ←──────────────────────────────┘
```

## State machine (canonical)

The 9 steps are defined in `system/run-state.md` and enforced by `tools/advance.py`. Each transition is validated atomically. State lives in `content/.state.json`.

| Step | Role | Owner | What happens |
|---|---|---|---|
| `idle` | — | (none) | No active run. `content/.state.json` does not exist, or its status is `shipped`/`failed`. |
| `capture` | — | `/post` (no args) | LLM builds clean transcript + 5 signal fields + 6 body sections, then calls `tools/capture-session.py` to write `content/sessions/YYYY-MM-DD-session-current.md` atomically. |
| `director` | Director | `@director` | Reads `content/current.md`, resolves source (session or topic), writes `source:` back, sets `status: drafting`, delegates. |
| `strategy` | Strategist | `@strategist` | Maps source → brief (reader, pain, point, proof, angle, formats). Writes `## Strategy` to `content/current.md`. **Human checkpoint: pick platforms.** |
| `draft` | Writer | `@writer` | Writes one draft per format to `content/drafts/`. Appends paths to `state.drafts`. |
| `edit` | Editor | `@editor` | Runs `tools/editor.py stamp` on each draft (4 mechanical gates + verdict). Moves passing drafts to `content/ready/`. |
| `publish` | Publisher | `@publisher` | Per-draft p/h/r. Publishes approved drafts. Publishers refuse `gates_verdict: fail`. Archives to `content/posted/` or `content/rejected/`. **Human checkpoint: p/h/r per draft.** |
| `complete` | — | `tools/advance.py` | Sets `status: shipped`, run is done. Next `/post` overwrites the state. |
| `error` | — | `tools/advance.py --set-error` | Captures the last error message. Recover via `--recover-from <step>` or `--reset`. |

## Transition table

The full table of allowed transitions is in `system/run-state.md`. The 8 happy-path transitions are:

```
idle     → capture
capture  → director
director → strategy
strategy → draft
draft    → edit
edit     → publish
publish  → complete
complete → idle
```

Plus: `any step → error`, `error → idle` (via `--reset`), `error → <previous>` (via `--recover-from <step>`).

## What does the state machine do?

- **No skipped steps.** `tools/advance.py` rejects `idle → publish` with exit 2.
- **Atomic writes.** Every transition uses `tmp + fsync + rename`. Survives crashes mid-write.
- **History is append-only.** Every transition appends `{from, to, at, by}` to `state.history`.
- **Recoverable.** On `/post` re-run, read `state.history` to find the last good step. Ask the user: continue or restart.
- **Visible.** `bin/spiel status` shows the current step, run_id, drafts, ready, error, and age.

## Human checkpoints (embedded in roles)

Two roles interact with the user via the `question` tool:

| Role | Step | What the user does |
|---|---|---|
| **Strategist** | `strategy` | Pick platforms: x, linkedin, blog (`formats: [...]` in the brief) |
| **Publisher** | `publish` | Per-draft publish, hold, or reject |

Roles NEVER auto-pick. Always use the `question` tool and wait for the user's answer. Director is never involved in human interaction.

## Two handoff files

A run has two handoff files:

| File | What | Owner |
|---|---|---|
| `content/current.md` | The creative handoff. Roles append their sections (Source, Strategy, Drafts, Editorial, Publish). | Each role writes its section. |
| `content/.state.json` | The mechanical state. Current step, run_id, drafts list, ready list, error, history. | `tools/advance.py` writes (only). |

The state machine is the truth. The handoff is the artifact. The LLM is the agent. The Python tool is the validator.

## Rule

No source, no post.

If `/post` has no concrete source, the LLM stops and asks for one.
