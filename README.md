# The Spiel Engine

A portable content engine that turns work sessions into platform-native content.

## Quick Start

```bash
bash scripts/install.sh
```

Then run `/setup` in opencode (or any agent) to set up your ICP, offer, and voice.

## Commands

| Command | Action |
|---------|--------|
| `/post` | Start content pipeline |
| `/extract` | Ingest raw notes → wiki pages |
| `/publish` | Queue → production |
| `/health` | Wiki health check |
| `/queue` | Show content queue |
| `/setup` | Configure ICP, offer, voice |

See `SETUP.md` for the full manual, `concepts/` for methodology.

## Architecture

```
TheSpielEngine/
├── agents/              # Agent specs (generated)
├── assets/              # Brand, banners, screenshots
├── concepts/            # Strategy + voice configuration
├── content/             # Sessions, queue, posted archive
├── logs/                # JSONL activity logs
├── notes/               # Raw exports / .md journals
├── pages/               # Wiki pages (semantic memory)
├── raw/                 # Ingest source files
├── scripts/             # Engine scripts (Python + Shell)
├── templates/           # Post templates
└── rules.yaml           # Engine config (local, gitignored)
```

## Portability

The engine auto-resolves its root path. Set `VAULT_DIR` in `.env` (gitignored)
or as an environment variable. No hardcoded paths.
