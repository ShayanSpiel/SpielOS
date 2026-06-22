# AGENTS.md — SpielOS Governance

The canonical governance doc. **The state machine, the team, the role contracts.**

> **If you only read one file, read `system/state-machine.md`.**
> **If you only read two, also read `system/brief-schema.md`.**
> **If you only read three, also read this file.**
> **Everything else is reference.**

---

## What SpielOS is

A markdown-driven marketing team. You bring the work. The team — **MD, Strategist, Researcher, Copywriter, Editor, Designer, Publisher, Analyst** — turns it into posts for X, LinkedIn, and your blog. **You stay a builder.**

The 8 roles are `.md` files in `team/`. The 4 deterministic tools (gates, banner, publish, analyst) are small Python CLIs in `tools/`. The state machine is a single markdown table at `system/state-machine.md`. The handoff file is one `.brief.md` per run. **No central Python orchestrator.**

---

## The 8 roles

| Role | File | State machine states owned | Type |
|---|---|---|---|
| **MD** | [`team/md.md`](team/md.md) | IDLE, FORMAT_WIZARD, PUBLISH_REVIEW, COMPLETE_POST | LLM agent (the only one that knows the full state machine) |
| **Strategist** | [`team/strategist.md`](team/strategist.md) | COMPILE, SELECT | LLM agent (runs the 8-step / 6-question compiler, ranks templates) |
| **Researcher** | [`team/researcher.md`](team/researcher.md) | SESSION_CAPTURE | LLM agent + `tools/researcher.py` (synthesizes session log from opencode DB, classifies) |
| **Copywriter** | [`team/copywriter.md`](team/copywriter.md) | DRAFTING | LLM agent (writes drafts, applies voice register, 14 soft-gate self-check) |
| **Editor** | [`team/editor.md`](team/editor.md) | GATE_CHECK | LLM agent + `tools/editor.py` (15 mechanical + 14 soft gates) |
| **Designer** | [`team/designer.md`](team/designer.md) | BANNER | LLM agent + `tools/designer.py` (picks template + tokens, calls Playwright) |
| **Publisher** | [`team/publisher.md`](team/publisher.md) | PUBLISHING | LLM agent + `tools/publisher/*.py` (Buffer, X direct, LinkedIn direct, blog.sh) |
| **Analyst** | [`team/analyst.md`](team/analyst.md) | ANALYZING_POST | LLM agent + `tools/analyst.py` (engagement pull, perf re-rank) |

Every role is a subagent. The IDE invokes the MD subagent when you type `/post`. MD chains the other 7.

---

## The 12 states

```
IDLE → SESSION_CAPTURE → COMPILE → SELECT → FORMAT_WIZARD → DRAFTING → BANNER
     → GATE_CHECK → PUBLISH_REVIEW → PUBLISHING → ANALYZING_POST → COMPLETE_POST → IDLE
```

The state table is the **single source of truth** at `system/state-machine.md`. No Python enforces it. MD reads the table; nobody else needs to.

### State → role → action map

| # | State | Role | Action | Next states |
|---|---|---|---|---|
| 0 | IDLE | MD | reset brief, await intent | SESSION_CAPTURE / PUBLISH_REVIEW |
| 1 | SESSION_CAPTURE | Researcher | collect source + classify | COMPILE / IDLE |
| 2 | COMPILE | Strategist | 8-step (session) or 6-question (topic) compiler | SELECT / IDLE |
| 3 | SELECT | Strategist | rank templates by archetype/axis/funnel/ICP | FORMAT_WIZARD / IDLE |
| 4 | FORMAT_WIZARD | **MD (human gate)** | pick platforms (x, linkedin, blog) | DRAFTING / IDLE |
| 5 | DRAFTING | Copywriter | write drafts, soft-gate self-check | BANNER / IDLE |
| 6 | BANNER | Designer | pick template + tokens, call `tools/designer.py` | GATE_CHECK |
| 7 | GATE_CHECK | Editor | call `tools/editor.py` (15 mechanical) + 14 soft review | PUBLISH_REVIEW / DRAFTING |
| 8 | PUBLISH_REVIEW | **MD (human gate)** | per-draft p/h/r/s | PUBLISHING / IDLE |
| 9 | PUBLISHING | Publisher | dispatch via Buffer (or direct API) + archive | ANALYZING_POST |
| 10 | ANALYZING_POST | Analyst | pull engagement + re-rank templates | COMPLETE_POST |
| 11 | COMPLETE_POST | MD | archive `.brief.md` | IDLE |

---

## The handoff file: `.brief.md`

One `.brief.md` per `/post` run. Every role writes its `## <role>` section, appends the next state to `## state_history`, returns. Schema at `system/brief-schema.md`.

```markdown
---
run_id: 2026-06-22-001
state: GATE_CHECK
source: { kind: session, file: content/sessions/2026-06-22-session-...md }
formats: [x, linkedin, blog]
---

## strategist          <-- Strategist writes this
core_insight: ...
meanings: { systemic: ..., behavioral: ..., ... }
selected_meaning: { axis: human, rationale: ... }
template_selection: { x: [...], linkedin: [...], blog: [...] }

## researcher          <-- Researcher writes this
classification: { archetype: S1, funnel: MOFU, icp_layer: L3, vertical: ... }
evidence: { session: ..., topic_text: ..., key_facts: [...] }

## copywriter          <-- Copywriter writes this
drafts:
  - file: content/queue/2026-06-22-x-foo.md
    template: x-ship-01
    ...

## editor              <-- Editor writes this
gates: { ... }  # 15 mechanical
soft: { ... }   # 14 soft
verdict: pass

## designer            <-- Designer writes this
banners: [...]

## publisher           <-- Publisher writes this
posted: [...]
held: []
rejected: []

## analyst             <-- Analyst writes this
engagement: [...]

## state_history       <-- MD appends one line per transition
- 2026-06-22T18:08:00Z IDLE
- 2026-06-22T18:08:05Z SESSION_CAPTURE
- 2026-06-22T18:08:30Z COMPILE
- ...
```

**Field ownership** — each role writes its section once per state. Re-running is idempotent (read existing, diff, overwrite owned fields).

**Section missing** — if MD dispatches a role and the role's input section is missing, the role returns `error: <section> missing` and MD reverts to the previous state. This is the **only** atomicity guarantee.

**File location** — `content/.brief.md` while running, archived to `content/.brief/YYYY-MM-DD-NNN.md` on COMPLETE_POST. `.brief/` is gitignored.

**Crash recovery** — read the last line of `## state_history`, ask the user "continue from <state> or restart?"

---

## Two human checkpoints

| State | What the user does | Wizard banner source |
|---|---|---|
| FORMAT_WIZARD | Pick platforms: x, linkedin, blog | `system/prompts/wizards.md` |
| PUBLISH_REVIEW | Per-draft p/h/r/s | `system/prompts/wizards.md` |

**MD NEVER auto-picks at a checkpoint.** Always prints the banner verbatim and waits. The subagent in the IDE relays the banner to the user, pipes the answer back.

---

## Bounce rule

- **GATE_CHECK → DRAFTING** if any draft failed mechanical gates. Editor calls `tools/editor.py` once more after Copywriter's fix. Max 3 bounce rounds; after 3, MD moves to PUBLISH_REVIEW anyway with `verdict: warn`.

---

## Hold / Reject

- **Hold** — draft stays in `content/queue/`, decision is null. MD re-enters `PUBLISH_REVIEW` next time.
- **Reject** — draft moves to `content/rejected/` with `rejection_reason:` frontmatter.

---

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

# <Role>

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

---

## What stays deterministic

These 4 tools the LLM can't replace:

| Tool | Role | What |
|---|---|---|
| `tools/editor.py` | Editor | 15 mechanical gate checks (regex, length, structural) |
| `tools/designer.py` | Designer | Banner PNG render (Playwright + system Chrome) |
| `tools/publisher/{buffer,twitter,linkedin,blog.sh}` | Publisher | API dispatch + archive |
| `tools/analyst.py` | Analyst | Buffer engagement pull + perf ledger + re-rank |
| `tools/researcher.py` | Researcher | Session log synthesis from opencode DB + classify |

Everything else is LLM-driven (the 8 role `.md` files).

---

## How to extend the team

Adding a new role is **one file + one sync**:

1. Drop `team/<name>.md` with the structure above.
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, MCP.

Adding a new state is **one row in the table** + one role file (or a delegation to an existing role).

---

## Where everything lives

| What | Where |
|---|---|
| Role prompts (canonical) | `team/*.md` |
| State machine (canonical) | `system/state-machine.md` |
| Brief schema (canonical) | `system/brief-schema.md` |
| Pipeline map | `system/pipeline.md` |
| Brand (human) | `system/brand.md` |
| Brand (machine) | `system/brand.json` |
| LLM identity | `system/prompts/identity.md` |
| Compiler prompt | `system/prompts/compiler.md` |
| Leak guard | `system/prompts/leak-guard.md` |
| Wizard banners | `system/prompts/wizards.md` |
| Quality gates | `system/gates.md` |
| Mechanical config | `system/rules.yaml` |
| Knowledge base (user) | `strategy/*.md` (filled by wizard) |
| Post output shapes | `templates/*.md` |
| Templates + perf ledger | `templates/registry/*` |
| Deterministic tools | `tools/editor.py`, `tools/designer.py`, `tools/publisher/*`, `tools/analyst.py`, `tools/researcher.py` |
| Sync adapters | `tools/sync_adapters.py` |
| IDE adapter files | `adapters/` (auto-gen) |
| Live install | `~/.config/opencode/{agents,skill}/` |
| Vault shim | `bin/spiel` |
| Install + wizard | `install/install.sh`, `install/wizard/` |
| Brief file (active) | `content/.brief.md` |
| Brief archive | `content/.brief/YYYY-MM-DD-NNN.md` |
| Sessions / queue / posted / rejected | `content/{sessions,queue,posted,rejected}/` |
| Banners | `assets/banners/*.png` |
| Icons | `assets/icons/*.svg` |

---

## Hard rules across the system

- **NEVER** auto-pick at a human checkpoint. The wizard is a wizard.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** write a draft without the full 15-field frontmatter.
- **NEVER** advance the state without the previous role's section populated.
- **NEVER** publish a draft with `gates: fail`.
- **NEVER** publish a draft without `banner:`.

---

## The install flow

```bash
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
```

1. Installer downloads the repo (git clone preferred, tarball fallback)
2. Starts the local dashboard at `http://localhost:7331` (auto-opens in browser)
3. Installer polls for `.install-state.json` (the wizard writes this on Finish)
4. Wizard walks 10 steps: Welcome → Brand → Identity → ICP → Positioning → Offer → Funnel → Voice → Methodology → Connect
5. Wizard writes 8 strategy files + brand + .env on Finish, then auto-shuts down
6. Installer continues: shim at `~/.local/bin/spiel` + IDE adapters at `~/.config/opencode/`
7. Prints `DONE. Run 'spiel /post empty' from any IDE.`

The install is fully non-blocking — the user never has to type anything into the terminal during the install. They just fill the form in the browser.

### Install env vars

| Var | Default | What |
|---|---|---|
| `SPIELOS_INSTALL_DIR` | `~/.spiel` | Where to install the vault |
| `SPIELOS_WIZARD_PORT` | `7331` | Port for the local dashboard |
| `SPIELOS_WIZARD_TIMEOUT` | `1800` (30 min) | Max wait for the wizard to finish |
| `SPIELOS_VERSION` | `main` | Git branch / tag / tarball ref |

After install, the user never touches this repo. They edit `strategy/*.md` and `content/*` only.

---

## License

MIT.
