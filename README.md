# The Spiel Engine

> [!NOTE]
> If you are a technical founder who wants inbound without becoming a creator, this is the setup. Read the full methodology on the [homepage](/), or DM me on [X @ShayanSpiel](https://x.com/ShayanSpiel) for a done-for-you install.

A portable content engine that turns work sessions into platform-native posts.
Two agentic loops — one for compounding knowledge (wiki), one for publishing
content — governed by state machines, quality gates, and your ICP strategy.

```
WORK SESSION → [Wiki Loop] → Knowledge Base → [Content Loop] → X / LinkedIn / Blog
```

## Quick Start

```bash
git clone https://github.com/<owner>/TheSpielEngine.git
cd TheSpielEngine
```

Open `SETUP.md` and paste the prompt into **any** LLM-powered agent
(Cursor, Claude Code, opencode, Continue, ChatGPT, etc.).
The agent will self-detect, install commands, and walk through the
14-question ICP/voice/brand setup automatically.

**Requirements:** Python 3, bash, git.

---

## How It Works

Two state machines run independently. Each step is a `pipeline.sh` call.

### Wiki Loop

Ingests raw notes, extracts entities, reconciles into wiki pages, and links
them — a compounding knowledge base that grows with every session.

```
IDLE → INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE → COMPLETE → IDLE
```

### Content Loop

Turns a session (or topic) into platform-native drafts through strategy
classification, the 8-step Content Engine Compiler, drafting, gating,
queuing, and publishing.

```
IDLE → SESSION → STRATEGY → COMPILE → DRAFT → GATE → QUEUE → PUBLISH → ARCHIVE → IDLE
```

Both loops are driven by the LLM for creative work (analyzing, drafting,
gate-judging) and by scripts for mechanical work (transitions, file ops,
API calls). See `AGENTS.md` for the full state machine.

---

## Commands

After setup, your agent will have these commands available. Run them by
typing `/command` in the chat.

| Command | Action |
|---------|--------|
| `/analyze` | Run analysis step on pending items |
| `/compact` | Merge redundant or overlapping pages |
| `/config` | Show current engine configuration |
| `/extract [file]` | Ingest raw notes → wiki pages |
| `/health` | Wiki health check (orphans, links, frontmatter) |
| `/help` | Show all available commands |
| `/index` | Display the wiki index |
| `/log` | Recent log entries |
| `/optimize` | Suggest tagging, linking, and pruning opportunities |
| `/post [topic]` | Start content pipeline (session or topic) |
| `/prune` | Identify and remove stale or low-confidence pages |
| `/publish [id\|all]` | Queue → production (X / LinkedIn) |
| `/queue` | Show content queue grouped by platform |
| `/reconcile` | Reconcile extracted content into wiki pages |
| `/reject` | Remove a draft from the queue |
| `/relink` | Scan and repair broken wikilinks |
| `/schedule` | Set publish timestamps for queued content |
| `/state` | Show current state of wiki and content loops |

### Pipeline Subcommands

The `pipeline.sh` script drives every state transition. Run individual steps
to inspect, debug, or resume:

```bash
# Wiki pipeline
bash scripts/pipeline.sh wiki-extract notes/my-session.md
bash scripts/pipeline.sh wiki-analyze
bash scripts/pipeline.sh wiki-reconcile
bash scripts/pipeline.sh wiki-index
bash scripts/pipeline.sh wiki-validate
bash scripts/pipeline.sh wiki-complete

# Content pipeline
bash scripts/pipeline.sh post-start "topic"
bash scripts/pipeline.sh post-strategy
bash scripts/pipeline.sh post-compile
bash scripts/pipeline.sh post-draft
bash scripts/pipeline.sh post-banner
bash scripts/pipeline.sh post-gate
bash scripts/pipeline.sh post-publish

# Utilities
bash scripts/pipeline.sh status
bash scripts/pipeline.sh queue
bash scripts/pipeline.sh recover
```

---

## Directory Structure

```
TheSpielEngine/
├── AGENTS.md              # State machines + governance rules
├── SETUP.md               # Universal setup prompt (start here)
├── rules.yaml             # Engine config (local, gitignored)
├── .env                   # VAULT_DIR (local, gitignored)
│
├── concepts/              # Strategy + voice configuration
│   ├── icp-offer.md       # ICP profile, offer, funnel stages
│   ├── voice-corpus.md    # Canonical post examples
│   ├── voice-and-gates.md # Voice markers + 4-check + 10-gate system
│   ├── funnel-and-matrix.md # Archetypes, verticals, CTA matrix
│   └── session-as-content.md # Methodology: session → post
│
├── templates/             # Post frontmatter + structure templates
│   ├── x-post.md
│   ├── linkedin-post.md
│   ├── blog-post.md
│   └── session-log.md
│
├── scripts/               # Engine scripts (Python + Shell)
│   ├── engine.py           # State machine controller
│   ├── pipeline.sh         # CLI wrapper for all states
│   ├── content_compiler.py # 8-step Content Engine Compiler
│   ├── gates.py            # 16 mechanical gate checks
│   ├── strategy_classifier.py # Archetype + funnel classification
│   ├── icp_world.py        # ICP world-building
│   ├── post_x.py / post_linkedin.py # Platform API clients
│   ├── banner.py           # Auto-generate post banners
│   ├── wiki-health.py      # Wiki health checks
│   └── state_machine.py    # Canonical state table
│
├── assets/                # Brand, banners, screenshots, icons
│   ├── brand-config.json   # Brand name, colors, voice keywords
│   ├── banners/            # Auto-generated post banners
│   └── icons/              # SVG icons for the engine UI
│
├── content/               # All generated content
│   ├── sessions/           # Raw session logs
│   ├── queue/              # Drafts awaiting gates + publish
│   ├── posted/             # Published archive
│   └── rejected/           # Failed gates
│
├── .opencode/             # Command + skill definitions
│   ├── commands/           # Slash command files (agent reads + installs)
│   └── skill/              # Content pipeline skill definition
│
├── logs/                   # JSONL activity logs
├── raw/                    # Ingest source files
└── notes/                  # Raw exports / .md journals
```

---

## Quality Gates

Every draft passes through a multi-layer gate system before publishing:

### Mechanical (16 checks — `gates.py`)
- Character count, hook presence, em-dash rules
- No architecture leaks, audience named, lesson surfaced
- No generic statements, reader as subject, closing presence
- Frontmatter complete, ICP present, banner file exists

### Creative (4-check baseline + 10-gate extended — LLM judges)
- Reader's world is the subject, not the writer's project
- Tension in first 2 lines
- Named reader present (founders, builders, operators)
- One ICP per post, problem before solution, specificity
- No platitudes, grounded references, engagement ask

### Composite score
`(passes / total gates)`. Minimum threshold: 0.85. Configured in `rules.yaml`.

---

## Configuration

| File | Purpose |
|------|---------|
| `rules.yaml` | Posting mode, platform limits, gate thresholds, strategy |
| `assets/brand-config.json` | Brand name, colors, voice keywords, platforms |
| `concepts/icp-offer.md` | ICP demographics, psychographics, problem hierarchy |
| `concepts/voice-corpus.md` | Canonical examples for voice matching |
| `concepts/funnel-and-matrix.md` | Archetypes, verticals, CTA matrix |
| `.env` | `VAULT_DIR` — vault root path |

---

## Portability

- **Auto-resolving root:** scripts detect their own location, no hardcoded
  paths. Set `VAULT_DIR` in `.env` or as an environment variable to override.
- **Agent-agnostic:** the setup prompt works in any LLM agent — Cursor, Claude
  Code, opencode, Continue, ChatGPT, etc.
- **Gitignored:** `rules.yaml`, `.env`, `content/*`, `logs/*`, `assets/banners/*`,
  `assets/screenshots/*` — local data stays local.
- **Standalone:** Python 3 + bash is all you need. No npm, no Docker.

---

## Logging

All state transitions are logged to `logs/YYYY-MM-DD.jsonl` (JSONL format).
View with:

```bash
python3 scripts/engine.py log --days 7 --tail 20
python3 scripts/engine.py log --level ERROR
```

---

## License

ISC
