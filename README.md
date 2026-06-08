# SpielEngine

**Agentic wiki — a vault operated by state machines, not prompts.**

SpielEngine is an open-source template for building an LLM-operated second brain. It replaces static rule files ("always check, never overwrite") with two executable state machines:

- **Wiki Loop** — ingest raw sources → analyze → reconcile → index → validate
- **Content Loop** — session capture → strategy load → draft → gate check → publish → analyze

Both loops are defined in a single `AGENTS.md` file that serves as the system's governing constitution. Your LLM reads it once per session and follows a state machine instead of a prompt with 50 rules.

## How It Works

1. Your LLM (opencode, Claude Code, Cline, etc.) loads `AGENTS.md` at session start.
2. `.wiki-state` tracks which state the system is in (IDLE → INGESTING → ANALYZING → ...).
3. You issue slash commands (`/extract`, `/post`, `/health`) to transition between states.
4. Each state has an **entry gate, an action, a validation gate, and an exit transition** — no silent failures, no skipped steps.
5. The content loop feeds back into the wiki: engagement data updates style guides, rejected drafts grow the anti-pattern library.

## Quick Start

```bash
# Clone the template
git clone https://github.com/YOUR_USER/SpielEngine my-wiki
cd my-wiki

# Copy to your LLM's project directory
cp -r . ~/my-project/

# Configure your identity
# Edit these files:
#   AGENTS.md       → set YOUR_NAME, YOUR_DOMAIN
#   .content-config → set posting mode (manual / auto-threshold / auto-always)

# Start a session
# Your LLM will read AGENTS.md and enter IDLE state.
# Try: /extract my-first-source.md
```

## Directory Structure

```
SpielEngine/
├── AGENTS.md                ← The government (state machines + quality gates)
├── .wiki-state              ← State machine persistence (auto-generated)
├── .content-config          ← Posting toggle config (user-editable)
├── SCHEMA.md                ← Frontmatter spec + tag taxonomy
├── index.md                 ← Page catalog (auto-maintained)
├── log.md                   ← Append-only action log
├── raw/                     ← Source materials (articles, notes, captures)
├── concepts/                ← Evergreen wiki pages (concepts, ideas, guides)
├── entities/                ← Entity pages (people, platforms, projects)
├── summaries/               ← Summary/overview pages
├── templates/               ← Page and post templates
│   ├── concept.md
│   ├── entity.md
│   ├── summary.md
│   ├── blog-post.md
│   ├── linkedin-post.md
│   ├── x-post.md
│   └── session-log.md
├── content/
│   ├── queue/               ← Drafts awaiting review/publish
│   ├── posted/              ← Published content
│   ├── rejected/            ← Rejected drafts (anti-pattern library)
│   └── sessions/            ← Session logs
├── assets/
│   └── screenshots/         ← Screenshot captures
├── scripts/
│   ├── wiki-health.py       ← Orphan/broken-link/stale-page checker
│   └── detect-redundancy.py ← Content overlap detection
├── .config/
│   └── opencode/
│       ├── opencode.jsonc   ← Command registrations
│       ├── skill/
│       │   └── shayanspiel-content/
│       │       └── SKILL.md ← Content engine skill
│       └── command/         ← 18 slash commands
│           ├── extract.md
│           ├── post.md
│           ├── publish.md
│           ├── queue.md
│           ├── health.md
│           ├── prune.md
│           ├── state.md
│           ├── reconcile.md
│           ├── relink.md
│           ├── index.md
│           ├── compact.md
│           ├── config.md
│           ├── log.md
│           ├── help.md
│           ├── schedule.md
│           ├── optimize.md
│           ├── analyze.md
│           └── reject.md
└── .gitignore
```

## Commands

| Command | What it does | State Machine |
|---------|-------------|---------------|
| `/extract [source]` | Ingest raw source → wiki page | Wiki |
| `/post [about]` | Session → queue drafts | Content |
| `/publish [id\|all]` | Queue → production | Content |
| `/health` | Full validation check | Wiki |
| `/prune` | Archive stale, merge duplicates | Wiki |
| `/state` | Show current system state | System |
| `/reconcile [page]` | Update page from source | Wiki |
| `/relink [page]` | Rebuild cross-links | Wiki |
| `/index` | Rebuild page catalog | Wiki |
| `/compact [topic]` | Consolidate concepts | Wiki |
| `/config [key] [value]` | View/modify config | System |
| `/log [n]` | Show last N log entries | System |
| `/queue` | Show queue status | Content |
| `/schedule [id] [date]` | Schedule draft | Content |
| `/optimize [id]` | Re-run gates, improve | Content |
| `/analyze [period]` | Analyze posted performance | Content |
| `/reject [id] [reason]` | Reject + learn | Content |
| `/help [command]` | Command synopsis | System |

## Platform Surfaces

SpielEngine supports drafting content for 3 platforms with templates per surface:

- **Blog** — GitHub Pages Jekyll site (deep, permanent, source of truth)
- **LinkedIn** — Casually authoritative posts (1200-3000 chars)
- **X** — Fast, tight posts (280-ish chars, thread support)

## Requirements

- An LLM client that reads markdown system files (opencode, Claude Code, Cline, etc.)
- (Optional) API keys for X and LinkedIn to enable auto-publishing
- (Optional) GitHub Pages repo for blog publishing

## Origin

Built from real production use at [ShayanSpiel](https://shayanspiel.github.io). The system manages 130+ wiki pages and has published 30+ drafts across 3 platforms. The insight: **prompt engineering is the past, agentic loops are the future.**
