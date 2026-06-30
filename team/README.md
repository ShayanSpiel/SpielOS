# Team

The live product has 4 roles + 1 slash command. Each role is a single markdown file at `team/<name>.md`, templated with the absolute vault path and installed to every supported IDE by `tools/sync_adapters.py`.

| File | Type | Step in state machine |
|---|---|---|
| `team/post.md` | slash command (`/post`) | runs `capture` and invokes `@strategist` |
| `team/strategist.md` | subagent | `strategy` |
| `team/writer.md` | subagent | `draft` |
| `team/editor.md` | subagent | `edit` |
| `team/publisher.md` | subagent | `publish` |

## How the team is invoked

`/post` is the entry point. `bin/spiel post` (or `tools/post.py` directly) creates the run, writes `content/current.md`, and advances the state to `strategy`, then invokes `@strategist`. `@strategist` reads `content/current.md` + `content/.state.json`, writes `## Strategy`, runs `tools/advance.py --to draft --by strategist`, runs `spiel next`, and invokes `@writer`. The chain continues: writer → editor → publisher. Publisher asks the user for per-draft publish/hold/reject — that is the only human checkpoint.

```text
/post ──► capture ──► strategy ──► draft ──► edit ──► publish ──► complete
           (LLM+tools)   (LLM)      (LLM)     (LLM)   (LLM+human)    (script)
```

The 5 role prompts each end with the same shape: read state, do the work, call `tools/advance.py --to <next> --by <role>`, run `spiel next`, invoke the next role via the IDE's dispatch tool. There is no human typing `@role` between steps in the auto chain.

## Where the determinism lives

These tools the LLM cannot replace:

- `tools/post.py` — auto-resets prior state at the top of `main()`, generates run_id, writes `content/current.md`, initializes `content/.state.json`, advances to `strategy`.
- `tools/advance.py` — validates every state transition, atomic writes, append-only history. ~90 lines.
- `tools/capture-session.py` — atomic write of `content/sessions/<date>-session-current.md` with 5 signal fields + 6 body sections + transcript appendix.
- `tools/editor.py` — runs the 4 mechanical gates (`em_dash`, `banned_phrases`, `required_frontmatter`, `char_count`) and persists `gates_verdict: pass|fail` to draft frontmatter via `stamp`.
- `tools/publisher/{buffer,twitter,linkedin}.py` + `tools/publisher/blog.sh` — dispatchers; `tools/publisher/_common.py:check_gates_verdict()` refuses to ship a `gates_verdict: fail` draft.
- `tools/codex_hook.py` — the Codex `UserPromptSubmit` hook. Pre-resets state, runs `spiel post` for topic/file, prints the session-mode recipe for bare `@post`.
- `tools/{next,continue,guard,hook_log,doctor,sync_adapters}.py` — support tooling (`spiel next`, `spiel continue`, `spiel guard`, `spiel hook-log`, `spiel doctor`, `python3 tools/sync_adapters.py [--install]`).

The LLM is the orchestrator. `tools/` is the hands. `team/*.md` is the contract.

## Archived roles (kept for reference, not in the live loop)

- `archive/roles/researcher.md` — would have produced `## research` from session evidence. The capture work is now done directly by `team/post.md` via `tools/capture-session.py`.
- `archive/roles/analyst.md` — engagement-based template re-ranking (post-MVP).
- `archive/roles/designer.md` — banner PNG generation. `tools/designer.py` and `assets/icons/` are dormant; restore when needed.

## Archived skills (kept for reference)

- `archive/skills/icp_simulation/` — would have run an LLM-as-ICP simulation on a session log.
- `archive/skills/template_picker/` — would have ranked templates by archetype/axis/funnel (older vocabulary banned in production drafts by `system/rules.yaml`).

These are intentionally NOT in the live path. `tools/sync_adapters.py` will not generate them. The smoke test asserts they are absent from generated adapters.
