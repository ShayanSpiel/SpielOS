# The Spiel Engine 🤖✍️

Turn real build sessions into publishable content automatically.

The Spiel Engine is a Session-as-Content system for technical founders.
It converts what you already build, debug, decide, and ship into platform-native
posts for **X, LinkedIn, and blog** without requiring a separate content workflow.

> You do not create content. You extract it from work.

```
WORK SESSION → [Wiki Loop] → Knowledge Base → [Content Loop] → X / LinkedIn / Blog
```

👉 Want a white-glove install? DM [X @ShayanSpiel](https://x.com/ShayanSpiel) to get a custom setup,
ICP build, and voice model configured for your company.

> ⚠️ WARNING
> This repo is not a ready-made content strategy.
> It is an engine, not a finished brand voice, and it needs your ICP definition,
> positioning, and offer to produce differentiated output.

> 💡 NOTE
> The engine ships with skeleton strategy templates in `concepts/`.
> `SETUP.md` uses a 14-question session to fill those with your real ICP, voice,
> and offer. Your full strategy stays in your local vault, not in this repo.

## What this repo is for

- **Engine only:** session-based content workflow, quality gates, publishing
  automation.
- **Not a SaaS wrapper:** runs locally with Python + bash.
- **Not pre-trained on your voice:** it learns your language from your setup.
- **Not a finished audience:** you must define your ICP and positioning first.

## What this repo does not include

❌ Your ICP definition
❌ Your positioning strategy
❌ Your offer design
❌ Your brand voice
❌ A distribution plan

Without those, output will read as functional but generic.
>>>>>>> 00883f6 (Update README clone URL to github.com/ShayanSpiel/SpielEngine)

## Quick Start

```bash
git clone https://github.com/ShayanSpiel/SpielEngine.git
cd SpielEngine
```

Open `SETUP.md` and paste the prompt into **any** LLM-powered agent:
Cursor, Claude Code, opencode, Continue, ChatGPT, etc.
The agent will:

- detect the repo structure
- configure your ICP and voice
- initialize your content strategy
- generate the templates and commands

**Requirements:** Python 3, bash, git.

---

## Choose your path

- 🛠️ **Self-Serve:** clone the repo, run `SETUP.md`, and launch your engine in minutes.
- 🚀 **Done-For-You:** skip the setup and get a custom install, ICP build, and voice model configured for your company.

DM me on [X @ShayanSpiel](https://x.com/ShayanSpiel) if you want the full white-glove install.

---

## Why this exists

Technical founders do not need to become influencers to get inbound.
They need a system that turns their actual work into distribution without a
content identity switch.

> Your work already contains content.
> This system extracts it, structures it, and turns it into platform-ready posts.

---

## See it in action

| 📄 Your raw input | 🚀 Generated post output |
| :--- | :--- |
| *“Spent 4 hours debugging LangGraph state drift. The issue was hidden state
  transitions and a bad `n_parallel` default.”* | *“Most AI agents don’t fail because of prompts.
  They fail because hidden state transitions create another place for context to drift.
  If you are building local agent workflows, fix your state model first.”* |

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
| **`/post [topic]`** | 🔥 **Start content pipeline - convert a session into drafts** |
| **`/publish [id\|all]`** | 🚀 **Push approved queue to X / LinkedIn** |
| **`/extract [file]`** | Ingest raw notes → wiki pages |
| `/state` | Show current state of wiki and content loops |
| `/health` | Wiki health check (orphans, links, frontmatter) |
| `/queue` | View drafts waiting for review or publish |
| `/optimize` | Suggest tagging, linking, and pruning opportunities |
| `/reconcile` | Reconcile extracted content into wiki pages |
| `/analyze` | Run analysis step on pending items |
| `/compact` | Merge redundant or overlapping pages |
| `/config` | Show current engine configuration |
| `/index` | Display the wiki index |
| `/log` | Recent log entries |
| `/prune` | Identify and remove stale or low-confidence pages |
| `/reject` | Remove a draft from the queue |
| `/relink` | Scan and repair broken wikilinks |
| `/schedule` | Set publish timestamps for queued content |
| `/help` | Show all available commands |

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
