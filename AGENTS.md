# AGENTS.md — SpielOS Governance

The canonical governance doc. **The state machine, the team, the role contracts.**

> **If you only read one file, read `system/pipeline.md`.**
> **If you only read two, also read `system/run-state.md`.**
> **If you only read three, also read this file.**
> **Everything else is reference.**

---

## What SpielOS is

A markdown-driven marketing team with a deterministic state machine. You bring the work. The team — **Director, Strategist, Writer, Editor, Publisher** — turns it into posts for X, LinkedIn, and your blog. **You stay a builder.**

The 5 roles are `.md` files in `team/`. The deterministic tools (`tools/advance.py`, `tools/editor.py`, `tools/capture-session.py`, `tools/publisher/*.py`) are small Python CLIs. The pipeline is a single markdown file at `system/pipeline.md`. The handoff is two files: `content/current.md` (creative artifact) and `content/.state.json` (mechanical state). **No central Python orchestrator.** The state machine is a 90-line tool with a transition table.

---

## The 5 roles

| Role | File | State step | Type |
|---|---|---|---|
| **Director** | [`team/director.md`](team/director.md) | `director` | LLM agent (routes source, delegates in order, no copy) |
| **Strategist** | [`team/strategist.md`](team/strategist.md) | `strategy` | LLM agent (compiles reader, pain, point, proof, angle, formats) |
| **Writer** | [`team/writer.md`](team/writer.md) | `draft` | LLM agent (writes one draft per format to `content/drafts/`) |
| **Editor** | [`team/editor.md`](team/editor.md) | `edit` | LLM agent + `tools/editor.py stamp` (4 mechanical gates + taste review) |
| **Publisher** | [`team/publisher.md`](team/publisher.md) | `publish` | LLM agent + `tools/publisher/*.py` (per-draft p/h/r, then dispatch) |

The slash command is `team/post.md` — it runs the `capture` step (calling `tools/capture-session.py`) and then delegates to `@director`.

Every role is a subagent. The IDE invokes the Director subagent when you type `/post`. Director chains the other 4 in order. Every role's last action is to call `tools/advance.py --to <next>` to validate the transition.

---

## The state machine (9 steps)

```text
IDLE → CAPTURE → DIRECTOR → STRATEGY → DRAFT → EDIT → PUBLISH → COMPLETE → IDLE
                       ↑                                                       ↓
                       └────────────────  ERROR  ←────────────────────────────┘
```

The state machine is the **single source of truth** for where a run is. The full table is in `system/run-state.md`. The transitions are enforced by `tools/advance.py` — every transition is validated, atomic, and append-only to `state.history`.

### Step → role → action map

| # | Step | Owner | Action | Next |
|---|---|---|---|---|
| 0 | `idle` | (none) | nothing — wait for `/post` | `capture` |
| 1 | `capture` | `team/post.md` (LLM) | Build clean transcript + 5 signal fields + 6 body sections. Call `tools/capture-session.py` to write the session log atomically. | `director` |
| 2 | `director` | `@director` | Read `content/current.md`, resolve source (session or topic), write `source:` back, set `status: drafting`, delegate. | `strategy` |
| 3 | `strategy` | `@strategist` | Compile reader, pain, point, proof, angle, formats into `## Strategy` in `content/current.md`. **HUMAN CHECKPOINT** — pick platforms. | `draft` |
| 4 | `draft` | `@writer` | Write one draft per format to `content/drafts/`. Append paths to `state.drafts`. | `edit` |
| 5 | `edit` | `@editor` | Run `tools/editor.py stamp` on each draft (4 mechanical gates). Move passing drafts to `content/ready/`. Append paths to `state.ready`. | `publish` |
| 6 | `publish` | `@publisher` | Per-draft p/h/r. **HUMAN CHECKPOINT** — p/h/r per ready draft. Publish via `tools/publisher/buffer.py` (or fallback). Publishers refuse `gates_verdict: fail`. Archive to `content/posted/` or `content/rejected/`. | `complete` |
| 7 | `complete` | `tools/advance.py` | Set `status: shipped`. Run is done. Next `/post` overwrites the state. | `idle` |
| 8 | `error` | `tools/advance.py --set-error` | Capture the last error. Stay at this step until `--reset` or `--recover-from <step>`. | `idle` or any |

The state machine is enforced by `tools/advance.py`. It is the only tool that mutates `content/.state.json`. Role files call it; nothing else writes to it.

---

## The two handoff files

A run has two handoff files. The state machine is one of them. The creative content is the other. They are not the same.

### `content/current.md` (creative artifact)

One `content/current.md` per `/post` run. Each role writes its own section, returns. Schema at `system/draft-schema.md`.

```markdown
---
mode: session | topic
session: content/sessions/2026-06-26-session-current.md   # if mode=session
input: "Just shipped v2"                                   # if mode=topic
status: routing | drafting | editing | ready | publishing | shipped | failed
run_id: 2026-06-26-001
created_at: 2026-06-26T12:00:00
source: <absolute path to the resolved source>
---

## Source

<one line>

## Strategy

reader: ...
pain: ...
point: ...
proof: [...]
angle: ...
formats: [x, linkedin]

## Drafts

- content/drafts/2026-06-26-x.md
- content/drafts/2026-06-26-linkedin.md

## Editorial

<editor's notes, e.g. "tools/editor.py stamp: pass on 2 drafts">

## Publish

- 2026-06-26-x.md → published (Buffer, post_id: ...)
- 2026-06-26-linkedin.md → hold
```

**Field ownership** — each role writes its section once per step. Re-running is idempotent (read existing, diff, overwrite owned fields). The `status:` field in the frontmatter is advisory; `content/.state.json` is the truth.

### `content/.state.json` (mechanical state)

Owned by `tools/advance.py`. Schema at `system/run-state.md`. Atomic writes. Append-only history.

```json
{
  "run_id": "2026-06-26-001",
  "status": "active",
  "step": "draft",
  "mode": "session",
  "current": "content/current.md",
  "session": "content/sessions/2026-06-26-session-current.md",
  "drafts": ["content/drafts/2026-06-26-x.md", "content/drafts/2026-06-26-linkedin.md"],
  "ready": [],
  "updated_at": "2026-06-26T12:00:00",
  "error": null,
  "history": [
    {"from": "idle", "to": "capture", "at": "2026-06-26T12:00:00", "by": "post"},
    {"from": "capture", "to": "director", "at": "2026-06-26T12:00:01", "by": "post"},
    {"from": "director", "to": "strategy", "at": "2026-06-26T12:00:02", "by": "director"},
    {"from": "strategy", "to": "draft", "at": "2026-06-26T12:00:03", "by": "strategist"}
  ]
}
```

**Crash recovery** — on `/post` re-run, if `content/.state.json` exists with `status: active` or `paused`, read `state.history` to find the last successful step. Ask the user "continue from `<step>` or restart?" If continue, jump to that step. If restart, run `tools/advance.py --reset` and start fresh. The promise in the previous version of this file is now real because the state is real.

---

## Session capture (the input to /post)

`/post` (no args) is **session mode**. The work session is the source. The capture flow is documented in `system/session-schema.md`.

The LLM collects clean user/assistant text from the live conversation, extracts 5 signal fields (`decision`, `number`, `lesson`, `pattern`, `ship`) and 6 body sections (`Patterns recognized`, `Decisions made`, `What we did`, `Shipped`, `Numbers`, `Lesson`), then calls `tools/capture-session.py` with the structured JSON. The tool writes `content/sessions/YYYY-MM-DD-session-current.md` atomically. The next `/post` overwrites it.

`/post <text>` or `/post @file:./path` is **topic mode**. The input text is the source. Session capture is skipped.

---

## Human interaction (embedded in roles)

Two roles interact with the user directly via the `question` tool:

| Role | Step | What the user does |
|---|---|---|
| **Strategist** | `strategy` | Pick platforms: x, linkedin, blog (sets `formats: [...]` in the brief) |
| **Publisher** | `publish` | Per-draft publish, hold, or reject |

Roles NEVER auto-pick at a human checkpoint. Always use the `question` tool and wait for the user's answer. Director is never involved in human interaction.

---

## Bounce rule

- **Editor → Writer** if any draft failed mechanical gates (`gates_verdict: fail`). Writer fixes, Editor runs `tools/editor.py stamp` again. Max 3 bounce rounds; after 3, Publisher ships anyway with `verdict: warn` (TODO: post-MVP).

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
role_in_pipeline: [<step>, ...]   # one of: idle, capture, director, strategy, draft, edit, publish, complete, error
status: active
reads:
  - "{vault_root}/content/current.md"
  - "{vault_root}/content/.state.json"
  - ... (others)
writes:
  - "{vault_root}/content/current.md"           # section append
  - "{vault_root}/content/.state.json"          # via tools/advance.py only
  - ... (others)
permission:
  task:
    "*": allow
---

# <Role>

## Mission
[What this role owns]

## Steps
1. Read `content/.state.json` to confirm the current step. If it's not <step>, return — not your turn.
2. Read the handoff.
3. Do your work.
4. Call `python3 tools/advance.py --to <next> --by <role> --vault {vault_root}`.
5. Invoke the next role.

## Hard rules
[What I never do]
```

The `tools/advance.py` call is the last action of every role. The transition is validated, atomic, and append-only.

---

## What stays deterministic

These tools the LLM can't replace:

| Tool | Owner | What |
|---|---|---|
| `tools/advance.py` | state machine | Validates transitions, atomic writes to `content/.state.json`, append-only history. ~90 lines. |
| `tools/capture-session.py` | `/post` (capture) | Atomic write of the session log with 5 signal fields + 6 body sections + transcript. |
| `tools/editor.py` | Editor | 4 mechanical gates (`em_dash`, `banned_phrases`, `required_frontmatter`, `char_count`) + `stamp` subcommand (persists verdict to draft frontmatter). |
| `tools/editor.py` → `check_gates_verdict()` in `tools/publisher/_common.py` | Publisher | Refuses to dispatch a draft with `gates_verdict: fail` or missing. Script check, not LLM wish. |
| `tools/publisher/buffer.py` | Publisher | Multi-platform dispatch via Buffer. |
| `tools/publisher/twitter.py` | Publisher | Direct X dispatch (fallback). |
| `tools/publisher/linkedin.py` | Publisher | Direct LinkedIn dispatch (fallback). |
| `tools/publisher/blog.sh` | Publisher | Blog commit + push. |

`tools/designer.py` (banner PNG renderer) and `assets/icons/` exist as dormant infrastructure for when the Designer role is restored.

Everything else is LLM-driven (the 5 role `.md` files + the `team/post.md` slash command).

---

## How to extend the team

Adding a new role is **one file + one sync**:

1. Drop `team/<name>.md` with the structure above.
2. Add the new step to the transition table in `system/run-state.md` and `tools/advance.py` (`ALLOWED_TRANSITIONS` and `STEP_TO_STATUS`).
3. Add the new step to `system/pipeline.md`.
4. Update the role that hands off to it.
5. Run `python3 tools/sync_adapters.py --install`.
6. The new role is now available in opencode, Claude Code, Cursor, Codex, MCP.

---

## Where everything lives

| What | Where |
|---|---|
| Role prompts (canonical) | `team/*.md` |
| Slash command | `team/post.md` |
| Pipeline map (canonical) | `system/pipeline.md` |
| State machine schema (canonical) | `system/run-state.md` |
| Session log schema (canonical) | `system/session-schema.md` |
| Draft schema (canonical) | `system/draft-schema.md` |
| Brand (human + machine) | `system/brand.md`, `system/brand.json` |
| Mechanical config | `system/rules.yaml` |
| Strategy files (filled by wizard) | `strategy/{audience,offer,voice,examples}.md` |
| Post output shapes | `templates/{x-post,linkedin-post,blog-post}.md` |
| State machine tool | `tools/advance.py` |
| Session capture tool | `tools/capture-session.py` |
| Editor gates + stamp | `tools/editor.py` |
| Publisher dispatchers | `tools/publisher/{buffer,twitter,linkedin}.py`, `tools/publisher/blog.sh` |
| Publisher gate check | `tools/publisher/_common.py:check_gates_verdict()` |
| Sync adapters | `tools/sync_adapters.py` |
| IDE adapter files (auto-gen) | `adapters/{opencode,claude,cursor,codex,mcp}/` |
| Live install | `~/.config/opencode/`, `~/.cursor/skills/`, `~/.claude/`, `~/.codex/` |
| Vault shim | `bin/spiel` (installed to `~/.local/bin/spiel`) |
| Global config | `~/.config/spielos/config` (vault pointer, set by installer) |
| Vault pointer | `<vault>/.spiel-vault` |
| Install + wizard | `install/install.sh`, `install/wizard/` |
| Handoff (creative) | `content/current.md` |
| Handoff (state) | `content/.state.json` |
| Session log | `content/sessions/YYYY-MM-DD-session-current.md` |
| Source notes | `content/inbox/` |
| Writer output | `content/drafts/` |
| Editor-approved | `content/ready/` |
| Published archive | `content/posted/` |
| Rejected archive | `content/rejected/` |
| Archived roles + skills | `archive/` |
| Banners (dormant) | `assets/banners/`, `assets/icons/`, `tools/banner-templates/`, `tools/designer.py` |
| Tests | `tests/smoke.py`, `tests/test_advance.py`, `tests/test_stamp_and_gates.py` |

---

## Hard rules across the system

- **NEVER** auto-pick at a human checkpoint. Use the `question` tool. Wait for the user.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** write a draft without the full 8-field frontmatter.
- **NEVER** advance the state without calling `tools/advance.py`. The state machine is the only writer of `content/.state.json`.
- **NEVER** publish a draft that failed `tools/editor.py stamp`. The publishers refuse — trust the script, don't override.
- **NEVER** ship with `gates_verdict: fail` or missing `gates_verdict`. The publishers refuse.
- **NEVER** run a role out of order. Each role checks `state.step` first; if it's not the role's step, return without doing anything.

---

## The install flow

```bash
curl -fsSL https://spiel.xyz/install | bash
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

If they have a source repo (this one) locally and want updates to flow from it (faster, no GitHub roundtrip), run:
```
spiel set-source /path/to/SpielOS
spiel update
```

### What `spiel update` and re-install preserve vs refresh

The skip list is the **only** thing that protects user data. The principle: protect personal data, refresh project data. Project data is anything the project (SpielOS) owns; personal data is anything the user (vault owner) owns.

| Scope | Personal (preserved) | Project (refreshed) |
|---|---|---|
| **Strategy** | `strategy/{audience,offer,voice,examples}.md` (filled by wizard) | — |
| **Brand** | `system/brand.md`, `system/brand.json` (tokens) | — |
| **Gates** | `system/rules.yaml` (mechanical config the user may tune) | — |
| **Identity** | `.env` (credentials) | — |
| **Content** | `content/{inbox,drafts,ready,posted,rejected,sessions}/` (user-generated posts + captured sessions) | — |
| **Role prompts** | — | `team/*.md` (5 role `.md` files + `post.md` slash command) |
| **Playbook** | — | `system/{pipeline,run-state,session-schema,draft-schema}.md` |
| **Tools** | — | `tools/{advance,editor,capture-session,sync_adapters}.py`, `tools/publisher/*` |
| **Shim** | — | `bin/spiel` |
| **Installer** | — | `install/install.sh`, `install/wizard/*` |
| **Tests** | — | `tests/*.py` |
| **Adapters** | — | `adapters/{opencode,claude,cursor,codex,mcp}/` (also re-synced to `~/.config/*` and `~/.codex/agents/`) |
| **Reference** | — | `archive/{roles,skills}/` (canonical, not user-touched) |
| **Docs** | — | `AGENTS.md`, `README.md`, `package.json` |

If the user has customized a role prompt (e.g. `team/editor.md` for a project-specific voice), the customization is **overwritten** on every `spiel update`. This is by design — role prompts are project-level, not personal. To preserve a local customization, move it to `strategy/voice.md` (which is preserved) and reference it from the role prompt.

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
