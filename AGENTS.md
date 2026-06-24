# AGENTS.md — SpielOS Governance

The canonical governance doc. **The pipeline, the team, the role contracts.**

> **If you only read one file, read `system/pipeline.md`.**
> **If you only read two, also read `system/draft-schema.md`.**
> **If you only read three, also read this file.**
> **Everything else is reference.**

---

## What SpielOS is

A markdown-driven marketing team. You bring the work. The team — **Director, Strategist, Writer, Editor, Publisher** — turns it into posts for X, LinkedIn, and your blog. **You stay a builder.**

The 5 roles are `.md` files in `team/`. The 2 deterministic tools (gates, publish) are small Python CLIs in `tools/`. The pipeline is a single markdown file at `system/pipeline.md`. The handoff file is one `content/current.md` per run. **No central Python orchestrator.**

---

## The 5 roles

| Role | File | Pipeline step | Type |
|---|---|---|---|
| **Director** | [`team/director.md`](team/director.md) | 1. Route | LLM agent (routes source, delegates in order, no copy) |
| **Strategist** | [`team/strategist.md`](team/strategist.md) | 2. Brief | LLM agent (compiles reader, pain, point, proof, angle, formats) |
| **Writer** | [`team/writer.md`](team/writer.md) | 3. Draft | LLM agent (writes one draft per format to `content/drafts/`) |
| **Editor** | [`team/editor.md`](team/editor.md) | 4. Sharpen | LLM agent + `tools/editor.py` (4 mechanical checks + taste review) |
| **Publisher** | [`team/publisher.md`](team/publisher.md) | 5. Ship | LLM agent + `tools/publisher/*.py` (per-draft p/h/r, then dispatch) |

Every role is a subagent. The IDE invokes the Director subagent when you type `/post`. Director chains the other 4 in order.

---

## The 5 steps

```text
IDLE → Director → Strategist → Writer → Editor → Publisher → IDLE
```

The pipeline table is the **single source of truth** at `system/pipeline.md`. No Python enforces it. Director reads the table; nobody else needs to.

### Step → role → action map

| # | Step | Role | Action | Next |
|---|---|---|---|---|
| 0 | IDLE | Director | nothing — wait for `/post` | 1 |
| 1 | Director | Director | accept source, write `content/current.md`, delegate to Strategist | 2 / 0 |
| 2 | Strategist | Strategist | compile reader, pain, point, proof, angle, formats into `content/current.md` | 3 / 0 |
| 3 | Writer | Writer | write one draft per format to `content/drafts/`, list paths in `content/current.md` | 4 / 0 |
| 4 | Editor | Editor | run `tools/editor.py` + taste review, move passing drafts to `content/ready/` | 5 / 3 |
| 5 | Publisher | Publisher | per-draft p/h/r via wizard, dispatch, archive | 0 |

---

## The handoff file: `content/current.md`

One `content/current.md` per `/post` run. Each role writes its own section, appends the next state to `## state_history`, returns. Schema at `system/draft-schema.md`.

```markdown
---
run_id: 2026-06-24-001
status: drafting
source: { kind: topic, raw: "we shipped v2" }
formats: [x, linkedin]
---

## Source

we shipped v2

## Strategy

reader: ...
pain: ...
point: ...
proof: [...]
angle: ...

## Drafts

- content/drafts/2026-06-24-x.md
- content/drafts/2026-06-24-linkedin.md

## Editorial

tools/editor.py: pass on all 4 drafts

## Publish

- 2026-06-24-x.md → published (Buffer)
- 2026-06-24-linkedin.md → hold
```

**Field ownership** — each role writes its section once per step. Re-running is idempotent (read existing, diff, overwrite owned fields).

**File location** — `content/current.md` while running. The file is overwritten on each new run.

**Crash recovery** — read the `## state_history` lines, ask the user "continue from <step> or restart?"

---

## Human interaction (embedded in roles)

Two roles interact with the user directly via the `question` tool:

| Role | Step | What the user does | Source |
|---|---|---|---|
| **Writer** | 3 (Draft) | Pick platforms: x, linkedin, blog | `skill/format_wizard/SKILL.md` |
| **Publisher** | 5 (Ship) | Per-draft p/h/r | `skill/publish_wizard/SKILL.md` |

Roles NEVER auto-pick at a human checkpoint. Always use the `question` tool and wait for the user's answer. Director is never involved in human interaction.

---

## Bounce rule

- **Editor → Writer** if any draft failed mechanical gates. Writer fixes, Editor runs `tools/editor.py` once more. Max 3 bounce rounds; after 3, Publisher ships anyway with `verdict: warn`.

---

## Hold / Reject

- **Hold** — draft stays in `content/ready/`, decision is null. Publisher handles it. Next `/post` run enters Publishing for those held drafts.
- **Reject** — draft moves to `content/rejected/` with `rejection_reason:` frontmatter.

---

## How a role is structured

Every `team/<role>.md` has the same shape:

```markdown
---
name: <role>
description: <one-line>
mode: subagent
role_in_pipeline: [<step>, ...]
status: active
reads:
  - "<list of files / sections>"
writes:
  - "<list of files / sections>"
---

# <Role>

## Mission
[What this role owns]

## Handoff IN
[What I read from the previous role]

## Handoff OUT
[What I write to the brief + any files]

## <role-specific guidance>

## Hard rules
[What I never do]

## Failure modes
[What I do when X]
```

When you add a new role, copy this structure. The handoff contract (`reads:` / `writes:`) is what makes the chain work.

---

## What stays deterministic

These tools the LLM can't replace:

| Tool | Role | What |
|---|---|---|
| `tools/editor.py` | Editor | 4 mechanical checks (em-dash, banned phrases, required frontmatter, char count) |
| `tools/publisher/buffer.py` | Publisher | Multi-platform dispatch via Buffer |
| `tools/publisher/twitter.py` | Publisher | Direct X dispatch (fallback) |
| `tools/publisher/linkedin.py` | Publisher | Direct LinkedIn dispatch (fallback) |
| `tools/publisher/blog.sh` | Publisher | Blog commit + push |

`tools/designer.py` (banner PNG renderer) and `assets/icons/` exist as dormant infrastructure for when the Designer role is restored.

Everything else is LLM-driven (the 5 role `.md` files).

---

## How to extend the team

Adding a new role is **one file + one sync**:

1. Drop `team/<name>.md` with the structure above.
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, Codex, MCP.

---

## Where everything lives

| What | Where |
|---|---|
| Role prompts (canonical) | `team/*.md` |
| Pipeline map (canonical) | `system/pipeline.md` |
| Draft schema (canonical) | `system/draft-schema.md` |
| Brand (human + machine) | `system/brand.md`, `system/brand.json` |
| Mechanical config | `system/rules.yaml` |
| Strategy files (filled by wizard) | `strategy/{audience,offer,voice,examples}.md` |
| Post output shapes | `templates/{x-post,linkedin-post,blog-post}.md` |
| Deterministic tools | `tools/editor.py`, `tools/publisher/*.py` |
| Sync adapters | `tools/sync_adapters.py` |
| IDE adapter files (auto-gen) | `adapters/{opencode,claude,cursor,codex,mcp}/` |
| Live install | `~/.config/opencode/`, `~/.cursor/skills/`, `~/.claude/`, `~/.codex/` |
| Vault shim | `bin/spiel` (installed to `~/.local/bin/spiel`) |
| Global config | `~/.config/spielos/config` (vault pointer, set by installer) |
| Vault pointer | `<vault>/.spiel-vault` |
| Install + wizard | `install/install.sh`, `install/wizard/` |
| Handoff file | `content/current.md` |
| Source notes | `content/inbox/` |
| Writer output | `content/drafts/` |
| Editor-approved | `content/ready/` |
| Published archive | `content/posted/` |
| Rejected archive | `content/rejected/` |
| Skills (human checkpoints) | `skills/{format_wizard,publish_wizard,voice_match}/` |
| Archived roles + skills | `archive/` |
| Banners (dormant) | `assets/banners/`, `assets/icons/`, `tools/banner-templates/`, `tools/designer.py` |

---

## Hard rules across the system

- **NEVER** auto-pick at a human checkpoint. Use the `question` tool. Wait for the user.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** write a draft without the full 8-field frontmatter.
- **NEVER** advance the step without the previous role's section populated.
- **NEVER** publish a draft that failed `tools/editor.py`.

---

## The install flow

```bash
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
```

1. Installer downloads the repo into the **current directory** (your project root becomes the vault, marked by `.spiel-vault`).
2. Starts the local dashboard at `http://localhost:7331` (auto-opens in browser).
3. Installer polls for `.install-state.json` (the wizard writes this on Finish).
4. Wizard walks 6 steps: Welcome → Brand → Audience → Offer → Voice → Examples → Connect.
5. Wizard writes 4 strategy files (textarea-based) + brand + .env on Finish, then auto-shuts down.
6. Installer continues: writes `<vault>/.spiel-vault` (vault pointer), `~/.config/spielos/config` (global config — makes vault resolvable from ANY directory), shim at `~/.local/bin/spiel` + IDE adapters at all 4 IDEs (opencode, Cursor, Claude Code, Codex — whichever is installed).
7. Prints `DONE. From any IDE, type /post to ship a post.`

The install is fully non-blocking — the user never has to type anything into the terminal during the install. They just fill the form in the browser.

### Install env vars

| Var | Default | What |
|---|---|---|
| `SPIELOS_INSTALL_DIR` | `$PWD` | Where to install the vault (default: current directory) |
| `SPIELOS_WIZARD_PORT` | `7331` | Port for the local dashboard |
| `SPIELOS_WIZARD_TIMEOUT` | `1800` (30 min) | Max wait for the wizard to finish |
| `SPIELOS_VERSION` | `main` | Git branch / tag / tarball ref |

After install, the user never touches this repo. They edit `strategy/*.md` and `content/*` only.

If they ever install to the wrong directory or move the vault, run:
```
spiel set-vault /path/to/vault
```
This rewrites `~/.config/spielos/config` to point to the correct vault. No re-install needed.

### Vault resolution order

The vault is resolved (first match wins):

1. **`$VAULT_DIR` env var** — explicit per-session override.
2. **`~/.config/spielos/config`** — global config (set by installer, persistent).
3. **`<cwd>/.spiel-vault`** — cwd walk-up for `.spiel-vault` file.
4. **`<cwd>/team/director.md`** — cwd walk-up for the new vault marker.
5. **`<shim>/..`** — detected when shim lives at `<vault>/bin/spiel`.

After install, step 2 (`~/.config/spielos/config`) is always set, so `spiel` resolves the vault regardless of your current working directory. `/post` content always saves to the vault, even when your IDE is open in a different project.

---

## License

MIT.
