# Pipeline

SpielOS is a lean role-based marketing team with a deterministic post runtime and state machine.

```text
IDLE → CAPTURE → STRATEGY → DRAFT → EDIT → PUBLISH → COMPLETE → IDLE
                       ↑                                              ↓
                       └───────────  ERROR  ←──────────────────────────┘
```

The state machine is defined in `system/run-state.md` and enforced by `tools/advance.py`. Each transition is validated atomically. State lives in `content/.state.json`.

**The 4 roles:** Strategist, Writer, Editor, Publisher — each owns one step of the pipeline.

The 7 happy-path transitions are:

```
idle     → capture    (spiel post)
capture  → strategy   (spiel post)
strategy → draft      (@strategist)
draft    → edit       (@writer)
edit     → publish    (@editor)
publish  → complete   (@publisher)
complete → idle       (advance.py)
```

Plus: `any step → error`, `error → idle` (via `--reset`), `error → <previous>` (via `--recover-from <step>`).

## What does the state machine do?

- **No skipped steps.** `tools/advance.py` rejects invalid transitions with exit 2.
- **Atomic writes.** Every transition uses `tmp + fsync + rename`. Survives crashes mid-write.
- **History is append-only.** Every transition appends `{from, to, at, by}` to `state.history`.
- **Auto-reset on `/post`.** `tools/post.py` clears `content/.state.json` and `content/current.md` at the top of `main()` so the LLM never has to reason about a stuck prior state. There is no resume; every `/post` is a fresh run.
- **Visible.** `bin/spiel status` shows the current step, run_id, drafts, ready, error, and age.

## Human checkpoints

MVP has one human checkpoint:

| Role | Step | What the user does |
|---|---|---|
| **Publisher** | `publish` | Per-draft publish, hold, or reject |

Format selection is deterministic (defaults to `x`, `linkedin`, `blog`) to avoid losing state across freeform replies.

## Two handoff files

| File | What | Owner |
|---|---|---|
| `content/current.md` | The creative handoff. Roles append their sections (Source, Strategy, Drafts, Editorial, Publish). | Each role writes its section. |
| `content/.state.json` | The mechanical state. Current step, run_id, drafts list, ready list, error, history. | `tools/advance.py` (only). |

The state machine is the truth. The handoff is the artifact. Python owns validation and durable state. The LLM is the agent for judgment and writing.

## Rule

Bare `/post` is session mode. The current conversation is the source.

For topic mode, the source is the provided text or `@file:` reference. For session mode, the adapter compiles the visible conversation and passes it to `spiel post --mode session`, which writes the session through `tools/capture-session.py`.
