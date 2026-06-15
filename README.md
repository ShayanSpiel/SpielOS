# The Spiel Engine

Turn real build sessions into publishable content automatically.

The Spiel Engine is a **Session-as-Content** system for technical founders.
It converts what you already build, debug, decide, and ship into platform-native
posts for **X, LinkedIn, and blog** without requiring a separate content workflow.

You do not create content. You extract it from work.

```
WORK SESSION → [Wiki Loop] → Knowledge Base → [Content Loop] → X / LinkedIn / Blog
```

The engine ships with skeleton strategy templates in `concepts/`. After running
the setup prompt in `SETUP.md`, the 14-question session fills these with your
real content strategy.

> [!NOTE]
> Want a white-glove install? DM [@ShayanSpiel](https://x.com/ShayanSpiel) to get a custom setup,
> ICP build, content strategy, and voice model configured for your company.

## What this repo is for

- **Engine only:** session-based content workflow, quality gates, publishing automation.
- **Not a SaaS wrapper:** runs locally with Python + bash.
- **Not pre-trained on your voice:** it learns your language from your setup.
- **Not a finished audience:** you must define your ICP and positioning first.

## What this repo does NOT include

- Your ICP definition
- Your positioning strategy
- Your offer design
- Your brand voice
- A distribution plan

---

## Quick Start

```bash
git clone https://github.com/ShayanSpiel/SpielEngine.git
cd SpielEngine
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
them -- a compounding knowledge base that grows with every session.

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
| `/post [topic]` | Start content pipeline (session or topic) |
| `/publish [id\|all]` | Queue to production (X / LinkedIn) |
| `/extract [file]` | Ingest raw notes to wiki pages |
| `/state` | Show current state of wiki and content loops |
| `/health` | Wiki health check (orphans, links, frontmatter) |
| `/queue` | Show content queue grouped by platform |
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

## Quality Gates

Every draft passes through a multi-layer gate system before publishing:

### Mechanical (16 checks -- `gates.py`)
- Character count, hook presence, em-dash rules
- No architecture leaks, audience named, lesson surfaced
- No generic statements, reader as subject, closing presence
- Frontmatter complete, ICP present, banner file exists

### Creative (4-check baseline + 10-gate extended -- LLM judges)
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
| `.env` | `VAULT_DIR` -- vault root path |

---

## Directory Structure

```
TheSpielEngine/
├── AGENTS.md                # State machines + governance rules
├── SETUP.md                 # Universal setup prompt (start here)
├── SCHEMA.md                # Page and post frontmatter schemas
├── rules.yaml               # Engine config (local, gitignored)
├── rules.yaml.example       # Example config with defaults
├── .env                     # VAULT_DIR (local, gitignored)
│
├── concepts/                # Strategy + voice configuration
│   ├── icp-offer.md
│   ├── voice-corpus.md
│   ├── voice-and-gates.md
│   ├── funnel-and-matrix.md
│   └── session-as-content.md
│
├── scripts/                 # Engine scripts (Python + Shell)
│   ├── engine.py             # State machine controller
│   ├── pipeline.sh           # CLI wrapper for all states
│   ├── content_compiler.py   # 8-step Content Engine Compiler
│   ├── gates.py              # 16 mechanical gate checks
│   ├── strategy_classifier.py
│   ├── icp_world.py
│   ├── post_x.py / post_linkedin.py / post_topic.py
│   ├── post.sh / publish-blog.sh
│   ├── banner.py
│   ├── wiki-health.py
│   ├── state_machine.py / state.py
│   ├── logger.py
│   ├── capture_session.py / capture-*.sh
│   ├── detect-redundancy.py
│   └── generate-arch-canvas.py
│
├── templates/               # Post frontmatter + structure templates
│   ├── x-post.md
│   ├── linkedin-post.md
│   ├── blog-post.md
│   └── session-log.md
│
├── assets/                  # Brand, banners, screenshots, icons
│   ├── brand-config.json
│   ├── banners/
│   └── icons/
│
├── content/                 # All generated content
│   ├── sessions/
│   ├── queue/
│   ├── posted/
│   └── rejected/
│
├── .opencode/               # Command + skill definitions for agent
├── tests/                   # Test suite
├── comparisons/             # Wiki comparison pages
├── entities/                # Extracted wiki entities
├── summaries/               # Wiki summary pages
├── logs/                    # JSONL activity logs
├── raw/                     # Ingest source files
└── notes/                   # Raw exports / .md journals
```

---

## Portability

- **Auto-resolving root:** scripts detect their own location, no hardcoded
  paths. Set `VAULT_DIR` in `.env` or as an environment variable to override.
- **Agent-agnostic:** the setup prompt works in any LLM agent -- Cursor, Claude
  Code, opencode, Continue, ChatGPT, etc.
- **Gitignored:** `rules.yaml`, `.env`, `content/*`, `logs/*`, `assets/banners/*`,
  `assets/screenshots/*` -- local data stays local.
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
