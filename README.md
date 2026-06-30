# SpielOS

**A lean markdown-driven marketing team that lives in your IDE.**

SpielOS turns one `/post` command into platform-native content for X, LinkedIn, and your blog. The team — Strategist, Writer, Editor, Publisher — is just `.md` files. The deterministic runtime (`spiel post`, state, logs, quality gates, publishing) is Python. The LLM only owns judgment and writing.

```text
/post  ──► capture ──► strategy ──► draft ──► edit ──► publish ──► complete
            (tools)      (LLM)       (LLM)    (LLM)   (LLM+human)   (script)
```

Single human checkpoint: per-draft publish/hold/reject in the Publisher step. Everything else is fully automatic.

---

## Install

One command. Any Mac/Linux. Any IDE.

```bash
curl -fsSL https://spielos.xyz/install | bash
```

The installer:
1. Detects arch, python, git, curl/wget
2. Downloads the vault to the **current directory** (your project root becomes the vault)
3. Starts the setup wizard at `http://localhost:7331` (auto-opens in your browser)
4. Waits for you to click **Finish** in the wizard
5. Installs the `spiel` shim to `~/.local/bin/spiel`
6. Writes `~/.config/spielos/config` — a **global config** that makes the vault resolvable from ANY working directory, not just inside the vault
7. Syncs role adapter files (subagents + slash commands + skills) to all 4 IDEs: opencode, Claude Code, Cursor, Codex
8. Mirrors the Codex plugin package (`plugins/spielos/`) to `~/.codex/plugins/cache/<marketplace>/spielos/<version>/`
9. Runs 12 tool sanity checks so install-time failures are caught immediately
10. Prints `DONE. From any IDE, type /post to ship a post.`

For Codex, the first `/post` triggers a one-time prompt to **trust the new hook** (use `/hooks` in Codex CLI). The hook is the only deterministic surface in Codex — it pre-resets state, runs `spiel post` for topic/file invocations, and prints the session-mode recipe for bare `@post`.

If someone installs only the Codex plugin before running the installer, `/post` does not create files in the current project. It stops with a setup CTA. Use the plugin prompt `Set up SpielOS in ~/SpielOS`, or run:

```bash
SPIELOS_INSTALL_DIR="$HOME/SpielOS" bash <(curl -fsSL https://spielos.xyz/install)
```

Setup is separate from `/post`: setup creates/selects the vault, `/post` only runs the content pipeline once a vault resolves.

Override the install path: `SPIELOS_INSTALL_DIR=/some/path bash <(curl ...)`. Override the wizard port: `SPIELOS_WIZARD_PORT=8080`. Override the timeout (default 30 min): `SPIELOS_WIZARD_TIMEOUT=300`.

The vault is the directory you ran the installer from. A global config at `~/.config/spielos/config` stores the vault path and is used by `spiel` and all tools — **no cwd walk-up needed**. `/post` content always saves to the vault, even when your IDE is open in a different project.

Brew (when published):

```bash
brew install spielos/tap/spiel
```

---

## The commands

| Command | What | When |
|---|---|---|
| `curl https://spielos.xyz/install \| bash` | Fresh install: clone vault → run wizard → write global config → sync to IDEs | First time only |
| `spiel set-vault <path>` | Change which vault `spiel` resolves to (rewrites `~/.config/spielos/config`) | Moved vault or installed to wrong dir |
| `spiel set-source <path>` | Point updates at a local source repo (faster, no GitHub roundtrip) | You have the SpielOS repo checked out locally |
| `spiel init` | Re-run the wizard (rewrites `.env`, `strategy/`, `system/brand.*`) | Want to redo setup |
| `spiel update` | Pull latest tools/install/wizards + role prompts + system playbook → sync to IDEs. **Preserves ONLY personal data: `strategy/`, `content/`, `.env`, `system/brand.*`, `system/rules.yaml`** | When a new version ships |
| `spiel post <topic>` | Start a deterministic content run and leave state at `strategy` | CLI, Codex skill, or adapter entrypoint |
| `spiel doctor` | Check vault, runtime, and Codex plugin health | Debug install/runtime issues |

`spiel set-vault /path/to/vault` changes the global config. After running it, every `spiel` invocation and every `/post` resolves to the new vault — regardless of your current directory or which project your IDE is open to.

`spiel update` is the one to use after we push a new tool, gate, role prompt, or wizard. It preserves your personal data (strategy, content, brand, gates config, .env) and refreshes everything else (role prompts, system playbook, tools, install scripts, IDE adapters). Local customizations to role prompts in `team/*.md` will be overwritten — move personal voice/rules to `strategy/voice.md` instead.

---

## After install

From a Codex plugin/skill or supported IDE adapter, type:

```bash
/post                       # session mode if the adapter can pass a transcript
/post "Just shipped v2"     # topic mode — ship an announcement
/post @file:./notes.md      # topic mode from a file
```

Under the hood, adapters call `spiel post`. The CLI creates `content/current.md`, initializes `content/.state.json`, writes `content/runs/<run_id>/events.jsonl`, and leaves the run at `strategy`. The roles then continue the pipeline: **Strategist → Writer → Editor → Publisher**. Formats default to X, LinkedIn, and blog for MVP. The only in-run human pause is publish/hold/reject per ready draft.

CLI shortcuts (work from any terminal — **not cwd-dependent**):

```bash
spiel --version             # show version + vault path
spiel --where               # print resolved vault path
spiel set-vault <path>      # change which vault spiel resolves to
spiel config                # show vault + tool paths
spiel status                # show current pipeline state
spiel post "Just shipped v2" # start a deterministic topic run
spiel doctor                # check install + Codex plugin health
spiel check <draft.md>      # run the 4 mechanical gates
spiel sync                  # regenerate IDE adapter files (no pull)
spiel init                  # re-open the setup wizard
spiel update                # pull latest + sync to IDEs (preserves your data)
```

All CLI commands resolve the vault from `~/.config/spielos/config` (set once at install time). You can run `spiel --where` from `/tmp`, `/home/project-x`, or any IDE project directory — it always returns the same vault path.

---

## The team

| Role | Type | Owns |
|---|---|---|---|
| **Strategist** | LLM agent + `tools/simulator.py` | Session mode: runs the ICP World Simulator (script + prompt) to produce `content/.icp-world.json`. Compiles reader, pain, point, proof, angle, formats into the brief via the strategy→brief mapping. Editor's `grounding_check` gate (5th) validates the brief traces to the simulator. |
| **Writer** | LLM agent | Writes platform-native drafts |
| **Editor** | LLM + tool | 4 mechanical gates + taste review |
| **Publisher** | LLM + tool | Publish / hold / reject per draft, then dispatch |

Each role is a single `.md` file in `team/`. `spiel post` starts the deterministic run and hands off to the Strategist. The Strategist chains the other 3.

---

## The setup wizard

The wizard at `http://localhost:7331` (7 steps):

1. **Welcome** — overview, target, time
2. **Brand** — name, handle, tagline, colors + live banner preview
3. **Audience** — who you write for (markdown editor with skeleton)
4. **Offer** — what you sell (markdown editor with skeleton)
5. **Voice** — how posts read (markdown editor with skeleton)
6. **Examples** — your best posts (markdown editor with skeleton)
7. **Connect** — Buffer / X / LinkedIn / blog tokens (all skippable)

The wizard uses a minimal design system with a live banner preview and color pickers. Every input shows a `→ file/path` chip so you know where each value lands. The 7-step stepper at the top is clickable. The bottom nav is sticky.

On Finish, the wizard writes 4 strategy files (textarea-based editors) + brand + .env, then auto-shuts down. The installer then installs the `spiel` shim to `~/.local/bin/spiel`, syncs IDE adapter files, and exposes the Codex plugin package. From then on, `/post` works through adapters that call `spiel post`.

---

## Project structure

```
spielos/
├── team/                  # 5 role .md files (the marketing team)
│   ├── strategist.md      # brief
│   ├── writer.md          # drafts
│   ├── editor.md          # mechanical + taste
│   ├── publisher.md       # dispatch
│   └── post.md            # /post slash command
│
├── system/                # the playbook
│   ├── pipeline.md        # the 5-step table (single source of truth)
│   ├── draft-schema.md    # content/current.md + draft frontmatter
│   ├── brand.md           # brand tokens (human-readable)
│   ├── brand.json         # brand tokens (machine-readable)
│   └── rules.yaml         # mechanical config values
│
├── strategy/              # 4 knowledge files (filled by wizard)
│   ├── audience.md        # who you write for
│   ├── offer.md           # what you sell
│   ├── voice.md           # how posts read
│   └── examples.md        # your best posts
│
├── templates/             # post output shapes
│   ├── x-post.md
│   ├── linkedin-post.md
│   └── blog-post.md
│
├── tools/                 # deterministic tools
│   ├── post.py            # deterministic /post runtime
│   ├── advance.py         # state machine
│   ├── capture-session.py # session log writer
│   ├── doctor.py          # install/runtime diagnostics
│   ├── editor.py          # 4 mechanical gates (CLI)
│   ├── codex_hook.py      # Codex UserPromptSubmit hook
│   ├── next.py            # `spiel next` / `spiel continue` (next role / continue guidance)
│   ├── guard.py           # `spiel guard` (orphan content check)
│   ├── hook_log.py        # `spiel hook-log`
│   ├── publisher/         # Buffer / X direct / LinkedIn direct / blog.sh
│   ├── designer.py        # banner PNG render (dormant — Designer archived)
│   ├── sync_adapters.py   # generates IDE adapter files
│   └── _vault.py          # shared vault resolver
│
├── content/               # generated content
│   ├── sessions/          # captured session logs (one per day)
│   ├── drafts/            # writer output
│   ├── ready/             # editor-approved
│   ├── posted/            # published archive
│   ├── rejected/          # rejected archive
│   └── runs/              # per-run event logs
│
├── assets/                # design assets (dormant)
│   ├── icons/             # 17 SVG icons
│   └── banners/           # generated banner PNGs
│
├── plugins/spielos/       # Codex plugin package
│   ├── .codex-plugin/plugin.json
│   ├── hooks.json
│   ├── scripts/post-hook.sh
│   └── assets/            # icon, logos
│
├── .agents/plugins/       # repo Codex marketplace
│   └── marketplace.json
│
├── bin/spiel              # vault-resolver shim + CLI
│                          # (~/.config/spielos/config is the global vault pointer)
│
├── install/               # single-command install
│   ├── install.sh         # curl | bash entry
│   ├── uninstall.sh
│   ├── wizard/            # the localhost:7331 setup wizard
│   │   ├── serve.py       # stdlib http.server
│   │   ├── index.html     # 7-step form
│   │   ├── design-system.css
│   │   ├── steps.js
│   │   └── skeletons/     # 4 skeleton files for textarea defaults
│   └── brew/spiel.rb      # homebrew formula
│
├── archive/               # archived roles + skills (not in live path)
│   ├── roles/             # analyst, designer, researcher
│   └── skills/            # icp_simulation, template_picker
│
├── adapters/              # auto-gen per-IDE agent files
│   ├── opencode/{agents,skill,commands}
│   ├── claude/{agents,commands}
│   ├── cursor/commands/
│   ├── codex/agents/
│   └── mcp/server.json
│
├── AGENTS.md              # role registry + pipeline
├── README.md              # you are here
├── tests/                 # smoke + adapter tests
└── package.json
```

---

## What stays deterministic

These tools the LLM can't replace:

| Tool | Role | What |
|---|---|---|
| `tools/post.py` | `/post` | Deterministic run start: auto-resets prior state, generates run_id, writes handoff, initializes `content/.state.json`, advances to `strategy` |
| `tools/advance.py` | state machine | Validates transitions and writes `content/.state.json` atomically |
| `tools/capture-session.py` | `/post` | Atomic write of `content/sessions/<date>-session-current.md` with 5 signal fields + 6 body sections + transcript appendix |
| `tools/editor.py` | Editor | 4 mechanical gates (em-dash, banned phrases, required frontmatter, char count) + `stamp` subcommand |
| `tools/publisher/*.py` | Publisher | API dispatch + archive (Buffer primary, X/LinkedIn direct fallback, blog.sh). Refuses `gates_verdict: fail`. |
| `tools/codex_hook.py` | Codex | The `UserPromptSubmit` hook: pre-resets state, runs `spiel post` for topic/file, prints the session-mode recipe for bare @post |
| `tools/next.py` | support | `spiel next` / `spiel continue` — prints next role, also provides continue guidance via `--continue` |
| `tools/guard.py` | support | `spiel guard` — detects orphan drafts/ready files vs `state.{drafts,ready}` |
| `tools/hook_log.py` | support | `spiel hook-log` — append-only JSONL of every Codex hook invocation |
| `tools/doctor.py` | support | `spiel doctor` — vault, runtime, and Codex plugin install health |
| `tools/sync_adapters.py` | build | Generates IDE adapter files from `team/*.md` + mirrors Codex plugin to the plugin cache |
| `tools/designer.py` | (dormant) | Banner PNG render — Designer role is archived, kept for restore |

Everything else is LLM-driven (the 4 role `.md` files + the post slash command).

---

## The pipeline (8 steps, 4 LLM roles)

```text
IDLE → CAPTURE → STRATEGY → DRAFT → EDIT → PUBLISH → COMPLETE → IDLE
                   ↑                                              ↓
                   └───────────  ERROR  ←──────────────────────────┘
```

The 4 LLM roles (Strategist, Writer, Editor, Publisher) are linked by the state machine in `content/.state.json`. The `/post` command (capture) advances directly to strategy. Every role's last action is to call `tools/advance.py --to <next> --by <role>`, run `spiel next`, then invoke the next role via the IDE's dispatch tool. The LLM is the loop driver; the IDE handles the dispatch. There is no human typing `@role` between steps in the auto chain.

The single human checkpoint is in the Publisher: per-draft publish/hold/reject.

| # | Step | Owner | Action |
|---|---|---|---|
| 1 | `capture` | `tools/post.py` (via `spiel post`) | Normalize topic/file/session input, capture session if needed, write `content/current.md`, initialize state, advance to `strategy`. |
| 2 | `strategy` | `@strategist` | In session mode: call `tools/simulator.py show` + run 4 steps in reasoning + call `tools/simulator.py write` (writes `content/.icp-world.json`). Then map simulator output + 4 strategy files to the 6 brief fields. **Default formats to `[x, linkedin, blog]`.** Topic mode skips the simulator. Write `## Strategy` to `content/current.md`. Advance to `draft`. |
| 3 | `draft` | `@writer` | Write one draft per format to `content/drafts/`. Append paths to `state.drafts` via `--add-draft` flag. Advance to `edit`. |
| 4 | `edit` | `@editor` | Run 4 mechanical gates per draft via `tools/editor.py stamp`. Run 5th gate (`grounding_check`) on the brief via `tools/editor.py check-brief`. Move passing drafts to `content/ready/`. Append paths to `state.ready` via `--add-ready` flag. Advance to `publish`. |
| 5 | `publish` | `@publisher` | **HUMAN CHECKPOINT.** Per-draft publish/hold/reject. Publishers refuse `gates_verdict: fail`. Archive to `content/posted/` or `content/rejected/`. Advance to `complete`. |
| 6 | `complete` | `tools/advance.py` | Set `status: shipped`. Run is done. Next `/post` overwrites the state. |

---

## Hard rules

- **NEVER** ask mid-pipeline format questions in MVP. Formats default to X, LinkedIn, and blog unless runtime config narrows them.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor's `em_dash` gate will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight" as a label, "the engine" as a label, "the pipeline" as a label) in public posts. `system/rules.yaml` enforces this in the `banned.regex` list.
- **NEVER** write a draft without the full 8-field frontmatter (title, created, platform, status, source, reader, point, angle).
- **NEVER** advance the state without calling `tools/advance.py`. The state machine is the only writer of `content/.state.json`.
- **NEVER** publish a draft that failed `tools/editor.py stamp`. The publishers refuse — trust the script, don't override.
- **NEVER** ship with `gates_verdict: fail` or missing `gates_verdict`. The publishers refuse.
- **NEVER** run a role out of order. Each role checks `state.step` first; if it's not the role's step, return without doing anything.
- **NEVER** write to `content/drafts/`, `content/ready/`, `content/posted/`, or `content/rejected/` from a role that doesn't own that step. Drafts are Writer's; ready/ is Editor's; posted/ and rejected/ are Publisher's.

---

## Add a new role

1. Drop `team/<name>.md` with the standard structure (see `team/README.md`).
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, Codex, MCP.

---

## License

MIT.
