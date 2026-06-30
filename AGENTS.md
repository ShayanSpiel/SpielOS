# AGENTS.md — SpielOS Governance

The canonical governance doc. **The state machine, the team, the role contracts.**

> **If you only read one file, read `system/pipeline.md`.**
> **If you only read two, also read `system/run-state.md`.**
> **If you only read three, also read this file.**
> **Everything else is reference.**

---

## What SpielOS is

A markdown-driven marketing team with a deterministic state machine. You bring the work. The team — **Strategist, Writer, Editor, Publisher** — turns it into posts for X, LinkedIn, and your blog. **You stay a builder.**

The 4 roles are `.md` files in `team/`. The deterministic tools (`tools/post.py`, `tools/advance.py`, `tools/capture-session.py`, `tools/editor.py`, `tools/codex_hook.py`, `tools/next.py`, `tools/guard.py`, `tools/hook_log.py`, `tools/doctor.py`, `tools/sync_adapters.py`, `tools/publisher/*.py`) are small Python CLIs. The pipeline is a single markdown file at `system/pipeline.md`. The handoff is two files: `content/current.md` (creative artifact) and `content/.state.json` (mechanical state). `tools/post.py` owns deterministic run start; role prompts own judgment and writing.

---

## The 4 roles

| Role | File | State step | Type |
|---|---|---|---|
| **Strategist** | [`team/strategist.md`](team/strategist.md) | `strategy` | LLM agent (session mode: runs ICP World Simulator; compiles reader, pain, point, proof, meaning, angle, formats) |
| **Writer** | [`team/writer.md`](team/writer.md) | `draft` | LLM agent (writes one draft per format to `content/drafts/`) |
| **Editor** | [`team/editor.md`](team/editor.md) | `edit` | LLM agent + `tools/editor.py stamp` (4 mechanical gates + taste review) |
| **Publisher** | [`team/publisher.md`](team/publisher.md) | `publish` | LLM agent + `tools/publisher/*.py` (per-draft p/h/r, then dispatch) |

The slash command is `team/post.md` — it is a thin adapter over `spiel post`, which starts the run deterministically and then delegates to `@strategist`.

Every role is a subagent. The post agent dispatches the first role (`@strategist`), and every role's last action is to call `tools/advance.py --to <next> --by <role>`, then run `spiel next`, then invoke the next role via the IDE's subagent / task tool. The LLM is the loop driver; the IDE handles the dispatch.

---

## The state machine (8 steps)

```text
IDLE → CAPTURE → STRATEGY → DRAFT → EDIT → PUBLISH → COMPLETE → IDLE
                       ↑                                              ↓
                       └───────────  ERROR  ←──────────────────────────┘
```

The state machine is the **single source of truth** for where a run is. The full table is in `system/run-state.md`. The transitions are enforced by `tools/advance.py` — every transition is validated, atomic, and append-only to `state.history`.

### Step → role → action map

| # | Step | Owner | Action | Next |
|---|---|---|---|---|
| 0 | `idle` | (none) | nothing — wait for `/post` | `capture` |
| 1 | `capture` | `tools/post.py` via `spiel post` | Normalize topic/file/session input, capture session if needed, write `content/current.md`, initialize state, and log events. | `strategy` |
| 2 | `strategy` | `@strategist` | In session mode, run `tools/simulator.py show` + the 4 simulator steps (Build Worldview, Build Failure Mode, Extract Meaning, Anchor to Evidence) + `tools/simulator.py write` to atomically save `content/.icp-world.json`. Then map simulator output + 4 strategy files to the 7 brief fields per the strategy→brief mapping table. Also write a `## Trace` block documenting which axis was selected, which example pattern it matches, and which offer.md lines were lifted into the brief. Topic mode skips the simulator. The Editor's `grounding_check` gate (5th gate) validates the brief + trace trace to the simulator. Formats default to x, LinkedIn, and blog unless runtime config narrows them. | `draft` |
| 3 | `draft` | `@writer` | Write one draft per format to `content/drafts/`. Append paths to `state.drafts`. | `edit` |
| 4 | `edit` | `@editor` | Run `tools/editor.py stamp` on each draft (4 mechanical gates). Move passing drafts to `content/ready/`. Append paths to `state.ready`. | `publish` |
| 5 | `publish` | `@publisher` | Per-draft p/h/r. **HUMAN CHECKPOINT** — p/h/r per ready draft. Publish via `tools/publisher/buffer.py` (or fallback). Publishers refuse `gates_verdict: fail`. Archive to `content/posted/` or `content/rejected/`. | `complete` |
| 6 | `complete` | `tools/advance.py` | Set `status: shipped`. Run is done. Next `/post` overwrites the state. | `idle` |
| 7 | `error` | `tools/advance.py --set-error` | Capture the last error. Stay at this step until `--reset` or `--recover-from <step>`. | `idle` or any |

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
formats: [x, linkedin, blog]

## Drafts

- content/drafts/2026-06-26-x.md
- content/drafts/2026-06-26-linkedin.md

## Editorial

<editor's notes, e.g. "tools/editor.py stamp: pass on 2 drafts">

## Publish

- 2026-06-26-x.md → published (Buffer, post_id: ...)
- 2026-06-26-linkedin.md → hold
```

**Field ownership** — each role writes its section once per step. Re-running is idempotent (read existing, diff, overwrite owned fields). The `content/.state.json` is the single source of truth for run state.

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
    {"from": "capture", "to": "strategy", "at": "2026-06-26T12:00:01", "by": "post"},
    {"from": "strategy", "to": "draft", "at": "2026-06-26T12:00:02", "by": "strategist"}
  ]
}
```

**Crash recovery** — on `/post` re-run, the adapter **always resets and starts fresh.** `tools/post.py` auto-resets at the top of `main()`. Do not ask the user whether to continue or restart; bare `/post` and any `/post <topic>` discards the prior run, if any, and starts a new one. There is no resume. To continue a paused run, the user invokes the per-role commands (`@strategist`, `@writer`, `@editor`, `@publisher`) or runs `spiel continue` from outside the `/post` adapter.

---

## Session capture (the input to /post)

`/post` (no args) is **session mode** when the adapter can pass a real transcript to `spiel post --mode session`. The work session is the source. The capture flow is documented in `system/session-schema.md`.

The adapter/LLM collects clean user/assistant text from the live conversation, extracts 5 signal fields (`decision`, `number`, `lesson`, `pattern`, `ship`) and 6 body sections (`Patterns recognized`, `Decisions made`, `What we did`, `Shipped`, `Numbers`, `Lesson`), then calls `spiel post --mode session` with the transcript and structured JSON. `tools/post.py` calls `tools/capture-session.py` and writes `content/sessions/YYYY-MM-DD-session-current.md` atomically. The next `/post` overwrites it.

`/post <text>` or `/post @file:./path` is **topic mode**. The input text is the source. Session capture is skipped.

---

## Human interaction (embedded in roles)

One role interacts with the user directly in MVP:

| Role | Step | What the user does |
|---|---|---|
| **Publisher** | `publish` | Per-draft publish, hold, or reject |

Strategist does not ask a format question in MVP. It defaults to `x`, `linkedin`, and `blog` unless runtime config supplied a narrower list. This keeps the pipeline from losing state across freeform checkpoint replies.

---

## The ICP World Simulator (session mode only)

When the run is in session mode, the Strategist runs the ICP World Simulator **before** writing the brief. The simulator is a deterministic script + prompt pair:

- **Script:** `tools/simulator.py` (the deterministic half)
- **Prompt:** `system/prompts/simulator.md` (the canonical 4-step instructions)
- **Output:** `content/.icp-world.json` (atomic, validated, schema at `system/icp-world-schema.md`)

The simulator is run as a sub-step of the `strategy` step. The Strategist calls:

```bash
python3 {vault_root}/tools/simulator.py show     # load the system prompt + inject context
python3 {vault_root}/tools/simulator.py write ...  # validate + atomically write .icp-world.json
```

The 4 steps the Strategist runs in its reasoning:

| Step | Output | Feeds brief field |
|---|---|---|
| 1. Build the ICP Worldview from `audience.md` | `worldview` | `reader` |
| 2. Build the Failure Mode (`.belief`, `.consequence`, `.mapping`) | `failure_mode` | `pain` ← `.consequence`, `point` ← `.mapping` |
| 3. Extract the Meaning in the ICP's own language | `meaning` | `point`, `angle` |
| 4. Anchor to Evidence (session signal fields + `offer.md` "Proof") | `evidence` | `proof` |

The strategy → brief mapping is enforced as a contract:

| Brief field | Source |
|---|---|
| `reader` | `strategy/audience.md` |
| `pain` | Simulator `failure_mode.consequence` |
| `point` | Simulator `failure_mode.mapping` + `strategy/offer.md` "Why it is different" |
| `proof` | Simulator `evidence` (session + offer) |
| `meaning` | Simulator `meaning` (synthesized from 6-axis analysis) |
| `angle` | Simulator `selected_axis` (systemic/behavioral/philosophical/contrarian/leverage/human) + `strategy/examples.md` pattern matching the axis |
| `formats` | Deterministic. Default `["x", "linkedin", "blog"]` |

After writing the brief, the Strategist writes a `## Trace` block with 6 fields documenting how the brief was assembled:

| Trace field | Source |
|---|---|
| `selected_axis` | One of: systemic, behavioral, philosophical, contrarian, leverage, human |
| `example_pattern` | Specific example from `strategy/examples.md` matching the selected axis |
| `offer_lift` | Token from `offer.md` "Why it is different" that bled into `point` |
| `worldview_brief` | One-line digest of ICP worldview from simulator |
| `failure_mode_brief` | One-line digest of belief + consequence + mapping from simulator |
| `meaning_synthesis` | Which 1-2 axes from the 6-axis analysis were blended to produce `meaning` |

**Topic mode** skips the simulator entirely. The Strategist still reads the 4 strategy files, but uses them directly to build the brief.

### The grounding_check gate (5th gate)

The Editor runs `tools/editor.py check-brief` after the 4 draft gates pass. This 5th gate validates the brief in `## Strategy` and the `## Trace` block are grounded in the simulator's output. Nine checks:

1. **brief_complete** — all 7 brief fields present (`reader`, `pain`, `point`, `proof`, `meaning`, `angle`, `formats`)
2. **simulator_present** (session mode) — `content/.icp-world.json` exists and is complete
3. **pain_traces_to_consequence** (session mode) — Jaccard token overlap ≥ 0.25
4. **point_traces_to_mapping** (session mode) — Jaccard token overlap ≥ 0.25
5. **meaning_traces_to_simulator** (session mode) — Jaccard token overlap ≥ 0.25
6. **point_blends_offer** (both modes) — Jaccard token overlap between `point` and `offer.md` "Why it is different" ≥ 0.15
7. **proof_grounded** (both modes) — `proof` has at least 1 ICP-language marker (e.g. `session`, `min`, `avg`, `visitor`, `traffic`, `conversion`, `engagement`, `experiment`, `6-7 min`) AND no build-log banned words (e.g. `tests`, `adapters`, `doctor`, `pipeline`, `shim`, `vault`, `IDE`, `git`, `commit`)
8. **trace_present** — `## Trace` block has all 6 required fields
9. **axis_valid** — `selected_axis` is one of the 6 valid ICP-World-Simulator axes

If any check fails, the Editor sets the error and stops. Drafts cannot ship without a grounded brief + trace. This prevents the failure mode where the LLM writes a build log disguised as content, or skips the simulator's `meaning` field that the writer needs to anchor the draft's core takeaway.

The internal labels (`worldview`, `failure_mode`, `belief`, `consequence`, `mapping`, `meaning`, `evidence`) MUST NOT appear in the brief or in any draft. The `banned.regex` list in `system/rules.yaml` enforces this.

---

## Failure on a step

- If the Editor finds all drafts failed mechanical gates (`gates_verdict: fail`), it sets the error via `tools/advance.py --set-error` and stops. The user inspects the drafts in `content/drafts/` and either fixes them manually and re-runs `/post`, or accepts the loss. The pipeline does not auto-bounce — bounce loops are a source of state drift.

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
role_in_pipeline: [<step>, ...]   # one of: idle, capture, strategy, draft, edit, publish, complete, error
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
2. Read the handoff (`content/current.md`).
3. Do your work. (Writer / Editor pass `--add-draft` / `--add-ready` flags; Publisher asks the user p/h/r.)
4. Call `python3 tools/advance.py --to <next> --by <role> [--add-draft <path>...] [--add-ready <path>...] --vault {vault_root}`.
5. Run `spiel next` to get the next role name.
6. Invoke the next role via the IDE's subagent / task tool. (Do NOT type `@<role>` as text — that does not dispatch.)

## Hard rules
[What I never do]
```

The `tools/advance.py` call is the last deterministic action of every role. The transition is validated, atomic, and append-only. `spiel next` and the IDE dispatch follow it; after invoking the next role, this role's turn is over.

---

## What stays deterministic

These tools the LLM can't replace:

| Tool | Owner | What |
|---|---|---|
| `tools/post.py` | `/post` runtime | Creates run IDs, writes `content/current.md`, initializes and advances state to `strategy`, writes `content/runs/<run_id>/events.jsonl`. |
| `tools/advance.py` | state machine | Validates transitions, atomic writes to `content/.state.json`, append-only history. ~90 lines. |
| `tools/capture-session.py` | `/post` (capture) | Atomic write of the session log with 5 signal fields + 6 body sections + transcript. |
| `tools/doctor.py` | support | Checks vault, runtime tools, and Codex plugin distribution files. |
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
| Deterministic /post runtime | `tools/post.py` |
| Diagnostics | `tools/doctor.py` |
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
| Writer output | `content/drafts/` |
| Editor-approved | `content/ready/` |
| Published archive | `content/posted/` |
| Rejected archive | `content/rejected/` |
| Archived roles + skills | `archive/` |
| Banners (dormant) | `assets/banners/`, `assets/icons/`, `tools/banner-templates/`, `tools/designer.py` |
| Tests | `tests/smoke.py`, `tests/test_advance.py`, `tests/test_stamp_and_gates.py` |
| Codex plugin | `plugins/spielos/`, `.agents/plugins/marketplace.json` |

---

## Hard rules across the system

- **NEVER** ask mid-pipeline format questions in MVP. Formats default to x, linkedin, and blog unless runtime config narrows them.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts. `system/rules.yaml` enforces this in the `banned.regex` list.
- **NEVER** write a draft without the full 8-field frontmatter (title, created, platform, status, source, reader, point, angle).
- **NEVER** advance the state without calling `tools/advance.py`. The state machine is the only writer of `content/.state.json`.
- **NEVER** publish a draft that failed `tools/editor.py stamp`. The publishers refuse — trust the script, don't override.
- **NEVER** ship with `gates_verdict: fail` or missing `gates_verdict`. The publishers refuse.
- **NEVER** run a role out of order. Each role checks `state.step` first; if it's not the role's step, return without doing anything.
- **NEVER** write to `content/drafts/`, `content/ready/`, `content/posted/`, or `content/rejected/` from a role that doesn't own that step. Drafts are Writer's; ready/ is Editor's; posted/ and rejected/ are Publisher's.

---

## The install flow

```bash
curl -fsSL https://spielos.xyz/install | bash
```

1. Installer downloads the repo into the **current directory** (your project root becomes the vault, marked by `.spiel-vault`).
2. Starts the local dashboard at `http://localhost:7331` (auto-opens in browser).
3. Installer polls for `.install-state.json` (the wizard writes this on Finish).
4. Wizard walks 6 steps: Welcome → Brand → Audience → Offer → Voice → Examples → Connect.
5. Wizard writes 4 strategy files (textarea-based) + brand + .env on Finish, then auto-shuts down.
6. Installer continues: writes `<vault>/.spiel-vault` (vault pointer), `~/.config/spielos/config` (global config — makes vault resolvable from ANY directory), shim at `~/.local/bin/spiel` + IDE adapters at all 4 IDEs (opencode, Cursor, Claude Code, Codex — whichever is installed).
7. Prints `DONE. From any IDE, type /post to ship a post.`

The install is fully non-blocking — the user never has to type anything into the terminal during the install. They just fill the form in the browser.

### How `/post` is wired per IDE (deterministic vs prompt-based)

The CLI (`bin/spiel` → `tools/post.py`) is the **single source of truth** for `/post`. The IDE is just the entry surface. The mechanism differs:

| IDE | Mechanism | Where |
|---|---|---|
| **Codex** | **Deterministic plugin hook** — `UserPromptSubmit` fires `plugins/spielos/scripts/post-hook.sh` BEFORE the LLM turn. The CLI runs regardless of what the LLM does next. | `plugins/spielos/hooks.json` |
| opencode | Prompt-based slash command | `~/.config/opencode/commands/post.md` |
| Cursor | Prompt-based slash command | `~/.cursor/commands/post.md` |
| Claude Code | Prompt-based slash command | `~/.claude/commands/post.md` |

The Codex path is the only one with a true deterministic surface. On all other IDEs the slash command is a prompt the LLM may or may not follow — those stay prompt-based until/unless each IDE adds a comparable hook API.

First-time Codex hook install: the hook is bundled in the plugin cache at `~/.codex/plugins/cache/<marketplace>/spielos/<version>/hooks.json`. Codex will ask the user to **trust** the new hook the first time it fires (Codex CLI: `/hooks`). Until trusted, the hook is skipped and the LLM-prompted `post.toml` agent takes over (and may behave unreliably for bare `/post`).

Plugin install is not vault setup. If the Codex plugin is installed before the user runs the curl installer, `/post` must stop with a setup CTA and must not create files in the current project. The setup path is separate: `Set up SpielOS in ~/SpielOS` (plugin setup skill) or `SPIELOS_INSTALL_DIR="$HOME/SpielOS" bash <(curl -fsSL https://spielos.xyz/install)`. `/post` assumes a vault resolves and only runs the content pipeline.

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
4. **`<cwd>/team/strategist.md`** — cwd walk-up for the vault marker.
5. **`<shim>/..`** — detected when shim lives at `<vault>/bin/spiel`.

After install, step 2 (`~/.config/spielos/config`) is always set, so `spiel` resolves the vault regardless of your current working directory. `/post` content always saves to the vault, even when your IDE is open in a different project.

---

## License

MIT.
