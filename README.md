# SpielOS

**A lean markdown-driven marketing team that lives in your IDE.**

SpielOS turns one `/post` command into platform-native content for X, LinkedIn, and your blog. The team — Director, Strategist, Writer, Editor, Publisher — is just `.md` files. The deterministic parts (quality gates, publishing) are tiny Python tools. Everything else is LLM-orchestrated markdown.

```
IDLE → [Director] → [Strategist] → [Writer] → [Editor] → [Publisher] → IDLE
                  ↕ user             ↕ user
              source reject      format wizard
                                publish/hold/reject
```

---

## Install

One command. Any Mac/Linux. Any IDE.

```bash
curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
```

The installer:
1. Detects arch, python, git, curl/wget
2. Downloads the vault to the **current directory** (your project root becomes the vault)
3. Starts the setup wizard at `http://localhost:7331` (auto-opens in your browser)
4. Waits for you to click **Finish** in the wizard
5. Installs the `spiel` shim to `~/.local/bin/spiel`
6. Writes `~/.config/spielos/config` — a **global config** that makes the vault resolvable from ANY working directory, not just inside the vault
7. Syncs the 5 role agents + 3 skills to `~/.config/opencode/`, `~/.claude/`, `~/.cursor/`, `~/.codex/`
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
/post                       # topic mode — supply source after /post
/post "Just shipped v2"     # topic mode — ship an announcement
/post @file:./notes.md      # topic mode from a file
```

The Director subagent picks the right next role, hands off via `content/current.md`, and chains the full pipeline: **Director → Strategist → Writer → Editor → Publisher**. You get two human pauses — pick platforms, pick publish/hold/reject per draft.

CLI shortcuts (work from any terminal — **not cwd-dependent**):

```bash
spiel --version             # show version + vault path
spiel --where               # print resolved vault path
spiel set-vault <path>      # change which vault spiel resolves to
spiel config                # show vault + tool paths
spiel status                # show current pipeline state
spiel check <draft.md>      # run the 4 mechanical gates
spiel sync                  # regenerate IDE adapter files (no pull)
spiel init                  # re-open the setup wizard
spiel update                # pull latest + sync to IDEs (preserves your data)
```

All CLI commands resolve the vault from `~/.config/spielos/config` (set once at install time). You can run `spiel --where` from `/tmp`, `/home/project-x`, or any IDE project directory — it always returns the same vault path.

---

## The team

| Role | Type | Owns |
|---|---|---|
| **Director** | LLM agent | Source intake, handoffs, human checkpoints |
| **Strategist** | LLM agent | Compiles reader, pain, point, proof, angle, formats |
| **Writer** | LLM agent | Writes platform-native drafts |
| **Editor** | LLM + tool | 4 mechanical gates + taste review |
| **Publisher** | LLM + tool | Publish / hold / reject per draft, then dispatch |

Each role is a single `.md` file in `team/`. The IDE invokes the Director subagent when you type `/post`. Director chains the other 4.

---

## The setup wizard

The 6-step wizard at `http://localhost:7331`:

1. **Welcome** — overview, target, time
2. **Brand** — name, handle, tagline, colors + live banner preview
3. **Audience** — who you write for (markdown editor with skeleton)
4. **Offer** — what you sell (markdown editor with skeleton)
5. **Voice** — how posts read (markdown editor with skeleton)
6. **Examples** — your best posts (markdown editor with skeleton)
7. **Connect** — Buffer / X / LinkedIn / blog tokens (all skippable)

The wizard uses a minimal design system with a live banner preview and color pickers. Every input shows a `→ file/path` chip so you know where each value lands. The 6-step stepper at the top is clickable. The bottom nav is sticky.

On Finish, the wizard writes 4 strategy files (textarea-based editors) + brand + .env, then auto-shuts down. The installer then installs the `spiel` shim to `~/.local/bin/spiel`, syncs the IDE adapter files, and installs the 5 agent + 3 skill stubs to `~/.config/opencode/`. From then on, `/post` works from any IDE.

---

## Project structure

```
spielos/
├── team/                  # 5 role .md files (the marketing team)
│   ├── director.md        # orchestrator
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
│   ├── editor.py          # 4 mechanical gates (CLI)
│   ├── publisher/         # Buffer / X direct / LinkedIn direct / blog.sh
│   ├── designer.py        # banner PNG render (dormant — Designer archived)
│   ├── sync_adapters.py   # generates IDE adapter files
│   └── _vault.py          # shared vault resolver
│
├── content/               # generated content
│   ├── inbox/             # source notes
│   ├── drafts/            # writer output
│   ├── ready/             # editor-approved
│   ├── posted/            # published archive
│   └── rejected/          # rejected archive
│
├── assets/                # design assets (dormant)
│   ├── icons/             # 17 SVG icons
│   └── banners/           # generated banner PNGs
│
├── skills/                # 3 active human-checkpoint skills
│   ├── format_wizard/     # ask user for platforms
│   ├── publish_wizard/    # ask user for p/h/r
│   └── voice_match/       # match user voice register
│
├── bin/spiel              # vault-resolver shim + CLI
│                          # (~/.config/spielos/config is the global vault pointer)
│
├── install/               # single-command install
│   ├── install.sh         # curl | bash entry
│   ├── uninstall.sh
│   ├── wizard/            # the localhost:7331 setup wizard
│   │   ├── serve.py       # stdlib http.server
│   │   ├── index.html     # 6-step form
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
| `tools/editor.py` | Editor | 4 mechanical gates (em-dash, banned phrases, required frontmatter, char count) |
| `tools/publisher/*.py` | Publisher | API dispatch + archive (Buffer primary, X/LinkedIn direct fallback, blog.sh) |
| `tools/designer.py` | (dormant) | Banner PNG render — Designer role is archived, kept for restore |
| `tools/sync_adapters.py` | build | Generates IDE adapter files from `team/*.md` + `skills/*/SKILL.md` |

Everything else is LLM-driven (the 5 role `.md` files).

---

## The pipeline (5 steps)

```
IDLE → Director → Strategist → Writer → Editor → Publisher → IDLE
```

The pipeline table is the **single source of truth** at `system/pipeline.md`. No Python enforces it. Director reads the table; nobody else needs to.

Human checkpoints are embedded in the role that owns the work:

| # | Step | Role | Action |
|---|---|---|---|
| 1 | Director | Director | Accept source, write `content/current.md`, delegate |
| 2 | Strategist | Strategist | Compile reader, pain, point, proof, angle, formats |
| 3 | Writer | Writer | Format wizard (HUMAN) + write drafts |
| 4 | Editor | Editor | Run 4 mechanical + taste review |
| 5 | Publisher | Publisher | Publish wizard (HUMAN) + dispatch |

---

## Hard rules

- **NEVER** auto-pick at a human checkpoint. The wizard is a wizard.
- **NEVER** use em-dashes. Use →, colons, or commas. The Editor will fail the draft.
- **NEVER** leak internal labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, "core_insight", "the engine", "the pipeline") in public posts.
- **NEVER** pitch the offer outside the 1-in-5 rule.
- **NEVER** write a draft without the full 8-field frontmatter.
- **NEVER** publish a draft that failed `tools/editor.py`.
- **NEVER** advance the step without the previous role's section populated.

---

## Add a new role

1. Drop `team/<name>.md` with the standard structure (see `team/README.md`).
2. Run `python3 tools/sync_adapters.py --install`.
3. The new role is now available in opencode, Claude Code, Cursor, Codex, MCP.

---

## License

MIT.
