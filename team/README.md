# Team

The live product has 5 roles + 1 slash command.

| File | Type | Step in state machine |
|---|---|---|
| `team/post.md` | slash command (`/post`) | runs `capture` and delegates to `director` |
| `team/director.md` | subagent | `director` |
| `team/strategist.md` | subagent | `strategy` |
| `team/writer.md` | subagent | `draft` |
| `team/editor.md` | subagent | `edit` |
| `team/publisher.md` | subagent | `publish` |

## How the team is invoked

The IDE invokes the `Director` subagent when you type `/post`. The Director chains the other 4 in order. Every role's last action is to call `tools/advance.py --to <next>` to validate the transition and update `content/.state.json` atomically.

```text
/post  ──►  capture  ──►  director  ──►  strategy  ──►  draft  ──►  edit  ──►  publish  ──►  complete
            (LLM)        (LLM)         (LLM)         (LLM)        (LLM)        (LLM)          (script)
```

`capture` runs the session-capture tool (`tools/capture-session.py`) — a deterministic write, not an LLM step. All other steps are LLM-driven.

## No nested subagents

There are no nested subagents. The Director does not invoke the Strategist subagent; it writes the next handoff and the IDE runtime advances. This keeps the role prompts simple and the failure modes local.

## Archived roles (kept for reference)

- `archive/roles/researcher.md` — would have used `tools/capture-session.py` (the file it owns is now called by `team/post.md` directly)
- `archive/roles/analyst.md` — engagement-based template re-ranking (post-MVP)
- `archive/roles/designer.md` — banner PNG generation (dormant; `tools/designer.py` exists but is not wired)

## Archived skills (kept for reference)

- `archive/skills/icp_simulation/` — would have run an LLM-as-ICP simulation
- `archive/skills/template_picker/` — would have ranked templates

These are intentionally NOT in the live path. `tools/sync_adapters.py` will refuse to generate them.
