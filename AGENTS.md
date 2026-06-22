# AGENTS.md — SpielOS Governance

The canonical governance doc. **The state machine, the team, and the role contracts.**

> **If you only read one file, read `system/state-machine.md`.**
> **If you only read two, also read `system/brief-schema.md`.**
> **Everything else in this doc is reference.**

---

## What SpielOS is

A markdown-driven marketing team. You bring the work. The team — MD, Strategist, Researcher, Copywriter, Editor, Designer, Publisher, Analyst — turns it into posts for X, LinkedIn, and your blog. **You stay a builder.**

## The 8 roles

| Role | File | Owns |
|---|---|---|
| **MD** | [`team/md.md`](team/md.md) | State machine, handoffs, human checkpoints, IDLE / FORMAT_WIZARD / PUBLISH_REVIEW / COMPLETE_POST |
| **Strategist** | [`team/strategist.md`](team/strategist.md) | Compiler, axis selection, template ranking (COMPILE, SELECT) |
| **Researcher** | [`team/researcher.md`](team/researcher.md) | Session synthesis, archetype classification (SESSION_CAPTURE) |
| **Copywriter** | [`team/copywriter.md`](team/copywriter.md) | Drafts, voice register, soft-gate self-check (DRAFTING) |
| **Editor** | [`team/editor.md`](team/editor.md) | 15 mechanical gates + 14 soft gates (GATE_CHECK) |
| **Designer** | [`team/designer.md`](team/designer.md) | Banner tokens, render PNG via `tools/designer.py` (BANNER) |
| **Publisher** | [`team/publisher.md`](team/publisher.md) | Buffer / X / LinkedIn / blog dispatch (PUBLISHING) |
| **Analyst** | [`team/analyst.md`](team/analyst.md) | Engagement pull, perf re-rank (ANALYZING_POST) |

Each role is a subagent. The IDE invokes the MD subagent when you type `/post`. MD chains the other 7.

## The 12 states

```
IDLE → SESSION_CAPTURE → COMPILE → SELECT → FORMAT_WIZARD → DRAFTING → BANNER
     → GATE_CHECK → PUBLISH_REVIEW → PUBLISHING → ANALYZING_POST → COMPLETE_POST → IDLE
```

The state table is the **single source of truth** at `system/state-machine.md`. No Python enforces it. MD reads the table; nobody else needs to.

## The handoff file

One `.brief.md` per run, in `content/.brief.md`. Every role writes its `## <role>` section, appends the next state to `## state_history`, returns. Schema at `system/brief-schema.md`.

Crash recovery: read the last line of `## state_history`, resume from there.

## Two human checkpoints

| State | What the user does |
|---|---|
| FORMAT_WIZARD | Pick platforms: x, linkedin, blog |
| PUBLISH_REVIEW | Per-draft p/h/r/s decision |

**MD NEVER auto-picks at a checkpoint.** Always prints the banner verbatim and waits.

## What stays deterministic

These are the 4 tools the LLM can't replace:

| Tool | Role | What it does |
|---|---|---|
| `tools/editor.py` | Editor | 15 mechanical gate checks (regex, length, structural) |
| `tools/designer.py` | Designer | Banner PNG render (Playwright + system Chrome) |
| `tools/publisher/{buffer,twitter,linkedin,blog.sh}` | Publisher | API dispatch + archive |
| `tools/analyst.py` | Analyst | Buffer engagement pull + perf ledger + re-rank |

Plus one tool that supports the LLM roles:

| Tool | Role | What it does |
|---|---|---|
| `tools/researcher.py` | Researcher | Synthesize session log from opencode DB + classify |

Everything else (compiler, voice register, template selection, draft generation, gate review) is LLM-driven.

## How a role is structured

Every `team/<role>.md` has the same shape:

```markdown
---
name: <role>
description: <one-line>
mode: subagent
role_in_pipeline: [<state>, ...]
reads: [<list of files / sections>]
writes: [<list of files / sections>]
tools: [<list of CLI tools>]
---

# <Role> — <Title>

## Mission
[What this role owns]

## Handoff IN
[What I read from the previous role]

## Handoff OUT
[What I write to the brief + any files]

## <role-specific guidance>
[State machine / compiler / drafting / etc.]

## Voice
[Tone, register, status line format]

## Hard rules
[What I never do]

## Failure modes
[What I do when X]
```

When you add a new role, copy this structure. The handoff contract (`reads:` / `writes:`) is what makes the chain work.

## How to extend the team

Adding a new role is **one file + one sync**:

1. Drop `team/<role>.md` with the structure above.
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, MCP.

Adding a new state is **one row in the table** + one role file.

## Where everything lives

| What | Where |
|---|---|
| Role prompts | `team/*.md` |
| State machine | `system/state-machine.md` |
| Brief schema | `system/brief-schema.md` |
| Pipeline map | `system/pipeline.md` |
| Brand | `system/brand.md` + `system/brand.json` |
| LLM identity | `system/prompts/identity.md` |
| Compiler | `system/prompts/compiler.md` |
| Leak guard | `system/prompts/leak-guard.md` |
| Wizard banners | `system/prompts/wizards.md` |
| Quality gates | `system/gates.md` |
| Mechanical config | `system/rules.yaml` |
| ICP / positioning / offer / funnel / voice / methodology / archetypes / corpus | `strategy/*.md` (filled by wizard) |
| Post output shapes | `templates/*.md` |
| Templates + perf ledger | `templates/registry/*` |
| Deterministic tools | `tools/editor.py`, `tools/designer.py`, `tools/publisher/*`, `tools/analyst.py`, `tools/researcher.py` |
| IDE adapter files | `adapters/` (auto-gen) |
| Live install | `~/.config/opencode/{agents,skill}/` |
| Vault shim | `bin/spiel` |
| Install + wizard | `install/install.sh`, `install/wizard/` |
| Brief file | `content/.brief.md` (active) → `content/.brief/YYYY-MM-DD-NNN.md` (archive) |
| Sessions / queue / posted / rejected | `content/{sessions,queue,posted,rejected}/` |
| Banners | `assets/banners/*.png` |

## State transitions in detail

See `system/state-machine.md` for the full table. Two LLM handoffs and two human pauses are the only non-mechanical steps:

| # | State | Actor | Action |
|---|---|---|---|
| 1 | SESSION_CAPTURE | Researcher | Collect source + classify |
| 2 | COMPILE | Strategist | 8-step / 6-question compiler |
| 3 | SELECT | Strategist | Rank templates |
| 4 | FORMAT_WIZARD | **human** | Pick platforms |
| 5 | DRAFTING | Copywriter | Write drafts |
| 6 | BANNER | Designer | Render PNGs |
| 7 | GATE_CHECK | Editor | Run 15 mechanical + 14 soft |
| 8 | PUBLISH_REVIEW | **human** | Per-draft p/h/r/s |
| 9 | PUBLISHING | Publisher | Dispatch via Buffer |
| 10 | ANALYZING_POST | Analyst | Engagement + re-rank |
| 11 | COMPLETE_POST | MD | Archive brief |
| 0 | IDLE | MD | Reset, wait |

## Hard rules across the system

- **NEVER** auto-pick at a human checkpoint. The wizard is a wizard.
- **NEVER** use em-dashes. Use →, colons, commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** write a draft without the full 15-field frontmatter.
- **NEVER** advance the state without the previous role's section populated.
- **NEVER** publish a draft with `gates: fail`.
- **NEVER** publish a draft without `banner:`.

## The install flow

1. `curl -fsSL https://spielos.xyz/install.sh | bash` (or `brew install spielos/tap/spiel`)
2. Installer downloads the repo, opens the local dashboard at `http://localhost:7331`
3. Wizard walks 10 steps: Welcome → Brand → Identity → ICP → Positioning → Offer → Funnel → Voice → Methodology → Connect
4. Wizard writes 8 strategy files + brand + .env + installs `spiel` shim
5. User runs `spiel /post empty` from any IDE

After install, the user never touches this repo. They edit `strategy/*.md` and `content/*` only.

## License

MIT.
