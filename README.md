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
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
```

The installer:
1. Detects arch, python, git, curl/wget
2. Downloads the vault (git clone preferred, tarball fallback)
3. Starts the setup wizard at `http://localhost:7331` (auto-opens in your browser)
4. Waits for you to click **Finish** in the wizard
5. Installs the `spiel` shim to `~/.local/bin/spiel`
6. Syncs the 8 role agents + 8 skill stubs to `~/.config/opencode/`
7. Prints `DONE. Run 'spiel /post empty' from any IDE.`

Override the install path: `SPIELOS_INSTALL_DIR=/path/to/.spiel bash <(curl ...)`. Override the wizard port: `SPIELOS_WIZARD_PORT=8080`. Override the timeout (default 30 min): `SPIELOS_WIZARD_TIMEOUT=300`.

Brew (when published):

```bash
brew install spielos/tap/spiel
```

---

## After install

From any IDE (opencode, Claude Code, Cursor, MCP), type:

```bash
/post empty                 # use today's session log
/post "Just shipped v2"     # topic mode — ship an announcement
/post @file:./notes.md      # topic mode from a file
```

The MD subagent picks the right next role, hands off via `.brief.md`, and chains the full pipeline: **Researcher → Strategist → Copywriter → Designer → Editor → Publisher → Analyst**. You get two human pauses — pick platforms, pick publish/hold/reject per draft.

CLI shortcuts (work from any terminal):

```bash
spiel --version             # show version + vault path
spiel config                # show vault + tool paths
spiel status                # show current pipeline state
spiel check <draft.md>      # run the 15 mechanical gates
spiel analyze               # pull engagement, re-rank templates
spiel init                  # re-open the setup wizard
```

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
3. **Identity** — role, story, content sources
4. **ICP** — who you serve, goals, fears, internal monologue
5. **Positioning** — your one-liner, category, core insight
6. **Offer** — what you sell, stack, price, guarantee
7. **Funnel** — distribution + archetypes (with custom archetype input)
8. **Voice** — register, style rules, banned openers
9. **Methodology** — name, description, platforms
10. **Connect** — Buffer / X / LinkedIn / blog tokens (all skippable)

The wizard mirrors the shayanspiel.github.io design system — same tokens, same components, same gradient. Every input shows a `→ file/path` chip so you know where each value lands. The 10-step stepper at the top is clickable. The bottom nav is sticky.

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
│   ├── identity.md        # LLM-facing runtime identity
│   ├── gates.md           # 15 mechanical + 14 soft gates
│   ├── rules.yaml         # mechanical config values
│   └── prompts/           # LLM-facing text per role
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
│   ├── researcher.py      # session synthesis from opencode DB
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
├── bin/spiel              # vault-resolver shim
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
| `tools/researcher.py` | Researcher | Session log synthesis from opencode DB + classify |

Everything else is LLM-driven (the 8 role `.md` files).

---

## The state machine (12 states)

```
IDLE → SESSION_CAPTURE → COMPILE → SELECT → FORMAT_WIZARD → DRAFTING → BANNER
     → GATE_CHECK → PUBLISH_REVIEW → PUBLISHING → ANALYZING_POST → COMPLETE_POST → IDLE
```

The state table is the **single source of truth** at `system/state-machine.md`. No Python enforces it. MD reads the table; nobody else needs to.

Two LLM handoffs and two human pauses are the only non-mechanical steps:

| # | State | Actor | Action |
|---|---|---|---|
| 1 | SESSION_CAPTURE | Researcher | Collect source + classify |
| 2 | COMPILE | Strategist | 8-step session compiler / 6-question topic compiler |
| 3 | SELECT | Strategist | Rank templates |
| 4 | FORMAT_WIZARD | **human** | Pick platforms |
| 5 | DRAFTING | Copywriter | Write drafts |
| 6 | BANNER | Designer | Render PNGs |
| 7 | GATE_CHECK | Editor | Run 15 mechanical + 14 soft |
| 8 | PUBLISH_REVIEW | **human** | Per-draft p/h/r/s |
| 9 | PUBLISHING | Publisher | Dispatch via Buffer |
| 10 | ANALYZING_POST | Analyst | Engagement + re-rank |
| 11 | COMPLETE_POST | MD | Archive brief |

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
