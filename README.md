# SpielOS

**A markdown-driven marketing team that lives in your IDE.**

SpielOS turns one `/post` command into platform-native content for X, LinkedIn, and your blog. The team — Managing Director, Strategist, Researcher, Copywriter, Editor, Designer, Publisher, Analyst — is just `.md` files. The deterministic parts (banner design, publishing, quality gates) are tiny Python tools. Everything else is LLM-orchestrated markdown.

```
WORK SESSION → [Strategist] → [Copywriter] → [Editor] → [Publisher] → [Analyst]
                            → [Designer]  →  ↑             ↑
                                                                  │
                                       you stay a builder ────────┘
```

---

## Install

One command. Any Mac/Linux. Any IDE.

```bash
curl -fsSL https://spielos.xyz/spielos | bash
```

The installer:
1. Detects arch, python, git, curl/wget
2. Downloads the vault to the **current directory** (your project root becomes the vault)
3. Starts the setup wizard at `http://localhost:7331` (auto-opens in your browser)
4. Waits for you to click **Finish** in the wizard
5. Installs the `spiel` shim to `~/.local/bin/spiel`
6. Writes `~/.config/spielos/config` — a **global config** that makes the vault resolvable from ANY working directory, not just inside the vault
7. Syncs the 8 role agents + 5 skills to `~/.config/opencode/`, `~/.claude/`, `~/.cursor/`
8. Prints `DONE. From any IDE, type /post to ship a post.`

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
| `curl ... \| bash` | Fresh install: clone vault → run wizard → write global config → sync to IDEs | First time only |
| `spiel set-vault <path>` | Change which vault `spiel` resolves to (rewrites `~/.config/spielos/config`) | Moved vault or installed to wrong dir |
| `spiel init` | Re-run the wizard (rewrites `.env`, `strategy/`, `system/brand.*`) | Want to redo setup |
| `spiel update` | Pull latest tools/install/wizards → sync to IDEs. **Preserves `team/`, `skills/`, `strategy/`, `content/`, `.env`, `system/brand.*`** | When a new version ships |

`spiel set-vault /path/to/vault` changes the global config. After running it, every `spiel` invocation and every `/post` resolves to the new vault — regardless of your current directory or which project your IDE is open to.

`spiel update` is the one to use after we push a new tool, gate, or wizard. It does NOT touch your prompts, strategies, drafts, or brand — only the tool sources, install scripts, and IDE adapters.

---

## After install

From any IDE (opencode, Claude Code, Cursor, MCP), type:

```bash
/post                       # use today's session log (session mode)
/post "Just shipped v2"     # topic mode — ship an announcement
/post @file:./notes.md      # topic mode from a file
```

The MD subagent picks the right next role, hands off via `.brief.md`, and chains the full pipeline: **Researcher → Strategist → Copywriter → Designer → Editor → Publisher → Analyst**. You get two human pauses — pick platforms, pick publish/hold/reject per draft.

CLI shortcuts (work from any terminal — **not cwd-dependent**):

```bash
spiel --version             # show version + vault path
spiel --where               # print resolved vault path
spiel set-vault <path>      # change which vault spiel resolves to
spiel config                # show vault + tool paths
spiel status                # show current pipeline state
spiel check <draft.md>      # run the 15 mechanical gates
spiel analyze               # pull engagement, re-rank templates
spiel sync                  # regenerate IDE adapter files (no pull)
spiel init                  # re-open the setup wizard
spiel update                # pull latest + sync to IDEs (preserves your data)
```

All CLI commands resolve the vault from `~/.config/spielos/config` (set once at install time). You can run `spiel --where` from `/tmp`, `/home/project-x`, or any IDE project directory — it always returns the same vault path.

---

## The team

| Role | Type | Owns |
|---|---|---|
| **MD** | LLM agent | State machine, handoffs, human checkpoints |
| **Strategist** | LLM agent | Compiler, axis selection, template ranking |
| **Researcher** | LLM + tool | Session synthesis, archetype classification |
| **Copywriter** | LLM agent | Drafts, voice register, soft-gate self-check |
| **Editor** | LLM + tool | 15 mechanical gates + 14 soft gates |
| **Designer** | LLM + tool | Banner tokens, render PNG via Playwright |
| **Publisher** | LLM + tool | Buffer / X / LinkedIn / blog dispatch |
| **Analyst** | LLM + tool | Engagement pull, perf re-rank |

Each role is a single `.md` file in `team/`. The IDE invokes the MD subagent when you type `/post`. MD chains the other 7.

---

## The setup wizard

The 10-step wizard at `http://localhost:7331`:

1. **Welcome** — overview, target, time
2. **Brand** — name, handle, tagline, colors + live banner preview
3. **ICP** — your audience profile (markdown editor with skeleton)
4. **Positioning** — your one-liner, category, insight (markdown editor)
5. **Offer** — what you sell (markdown editor)
6. **Funnel + Archetypes** — distribution sliders + archetype toggles (hybrid)
7. **Voice + Corpus** — register, style rules, voice examples (hybrid)
8. **Methodology** — name, sources, platforms (markdown editor)
9. **Rules** — mechanical config defaults (markdown editor)
10. **Connect** — Buffer / X / LinkedIn / blog tokens (all skippable)

The wizard uses a minimal design system with live banner previews, color pickers, and toggle groups. Every input shows a `→ file/path` chip so you know where each value lands. The 10-step stepper at the top is clickable. The bottom nav is sticky.

On Finish, the wizard auto-installs the `spiel` shim to `~/.local/bin/spiel`, syncs the IDE adapter files, and installs the 8 agent + 8 skill stubs to `~/.config/opencode/`. From then on, `/post` works from any IDE.

---

## Project structure

```
spielos/
├── team/                  # 8 role .md files (the marketing team)
│   ├── md.md              # orchestrator
│   ├── strategist.md      # compile + select
│   ├── researcher.md      # capture + classify
│   ├── copywriter.md      # drafting
│   ├── editor.md          # gate instructions
│   ├── designer.md        # banner instructions
│   ├── publisher.md       # dispatch instructions
│   └── analyst.md         # engagement + re-rank
│
├── system/                # the playbook
│   ├── state-machine.md   # the 12-state table (single source of truth)
│   ├── brief-schema.md    # .brief.md template (handoff file)
│   ├── pipeline.md        # role ↔ state map
│   ├── brand.md           # brand tokens (human-readable)
│   ├── brand.json         # banner tokens (machine-readable)
│   ├── gates.md           # 15 mechanical + 14 soft gates
│   ├── rules.yaml         # mechanical config values
│   └── prompts/           # LLM-facing text per role
│       ├── identity.md    # LLM-facing runtime identity + hard constraints
│
├── strategy/              # 8 knowledge files (filled by wizard)
│   ├── icp.md             # Ideal Customer Profile
│   ├── positioning.md     # your one-liner
│   ├── offer.md           # what you sell
│   ├── funnel.md          # how readers move through
│   ├── voice.md           # how posts read
│   ├── methodology.md     # where content comes from
│   ├── archetypes.md      # session types (S1–S10 + custom)
│   └── corpus.md          # 8 canonical voice examples
│
├── templates/             # post output shapes
│   ├── x-post.md
│   ├── linkedin-post.md
│   ├── blog-post.md
│   ├── session-log.md
│   └── registry/
│       ├── viral-templates.yaml
│       ├── performance.json
│       └── rank-history.jsonl
│
├── tools/                 # deterministic tools (one per role)
│   ├── editor.py          # 15 mechanical gates (CLI)
│   ├── designer.py        # banner gen (Playwright + system Chrome)
│   ├── publisher/         # Buffer / X direct / LinkedIn direct / blog.sh
│   ├── analyst.py         # engagement pull + re-rank
│   ├── capture-session.py # captures the CURRENT session → content/sessions/YYYY-MM-DD-session-current.md
│   ├── researcher.py      # mechanical classify + opencode session-list (debug)
│   └── sync_adapters.py   # generates IDE adapter files
│
├── content/               # generated content
│   ├── sessions/
│   ├── queue/
│   ├── posted/
│   ├── rejected/
│   └── .brief/            # archived briefs (gitignored)
│
├── assets/                # design assets
│   ├── icons/             # 17 SVG icons (sparkles, rocket, etc.)
│   └── banners/           # generated banner PNGs
│
├── bin/spiel              # vault-resolver shim + CLI
│                          # (~/.config/spielos/config is the global vault pointer)
│
├── install/               # single-command install
│   ├── install.sh         # curl | bash entry
│   ├── uninstall.sh
│   ├── wizard/            # the localhost:7331 setup wizard
│   │   ├── serve.py       # stdlib http.server
│   │   ├── index.html     # 10-step form (Alpine + design system)
│   │   ├── design-system.css
│   │   └── steps.js
│   └── brew/spiel.rb      # homebrew formula
│
├── adapters/              # auto-gen per-IDE agent files
│   ├── opencode/agents/   # ~/.config/opencode/agents/
│   ├── opencode/skill/    # ~/.config/opencode/skill/
│   ├── claude/agents/
│   ├── cursor/commands/
│   └── mcp/server.json
│
├── AGENTS.md              # role registry + state machine
├── README.md              # you are here
├── tests/                 # smoke + state machine tests
└── package.json
```

---

## What stays deterministic

These 4 tools the LLM can't replace:

| Tool | Role | What |
|---|---|---|
| `tools/editor.py` | Editor | 15 mechanical gate checks (regex, length, structural) |
| `tools/designer.py` | Designer | Banner PNG render (Playwright + system Chrome) |
| `tools/publisher/*.py` | Publisher | API dispatch + archive (Buffer primary, X/LinkedIn direct fallback, blog.sh) |
| `tools/analyst.py` | Analyst | Buffer engagement pull + perf ledger + re-rank |
| `tools/researcher.py` | Researcher | Mechanical classify + opencode session-list (debug) |
| `tools/capture-session.py` | Researcher | Capture the current session → `content/sessions/YYYY-MM-DD-session-current.md` (overwrites). The canonical "current" log. |

Everything else is LLM-driven (the 8 role `.md` files).

---

## The state machine (10 states)

```
IDLE → SESSION_CAPTURE → COMPILE → SELECT → DRAFTING → BANNER
     → GATE_CHECK → PUBLISHING → ANALYZING_POST → COMPLETE_POST → IDLE
```

The state table is the **single source of truth** at `system/state-machine.md`. No Python enforces it. MD reads the table; nobody else needs to.

Human checkpoints are embedded in the role that owns the work:

| # | State | Actor | Action |
|---|---|---|---|
| 1 | SESSION_CAPTURE | Researcher | Collect source + classify |
| 2 | COMPILE | Strategist | 8-step session compiler / 6-question topic compiler |
| 3 | SELECT | Strategist | Rank templates |
| 4 | DRAFTING | Copywriter | Format wizard + write drafts |
| 5 | BANNER | Designer | Render PNGs |
| 6 | GATE_CHECK | Editor | Run 15 mechanical + 14 soft |
| 7 | PUBLISHING | Publisher | Publish wizard + dispatch |
| 8 | ANALYZING_POST | Analyst | Engagement + re-rank |
| 9 | COMPLETE_POST | MD | Archive brief |

---

## Hard rules

- **NEVER** auto-pick at a human checkpoint. The wizard is a wizard.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight", "the engine", "the pipeline") in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** publish a draft with `gates: fail` or no `banner:`.
- **NEVER** advance the state without the previous role's section populated.

---

## Add a new role

1. Drop `team/<name>.md` with the standard structure (see `team/README.md`).
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, MCP.

## Add a new state

1. Add one row to `system/state-machine.md`.
2. Assign it a role (existing or new).
3. Add the role's prompt to `team/`.

---

## License

MIT.
