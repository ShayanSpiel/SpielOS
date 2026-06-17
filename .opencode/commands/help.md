---
description: Show all available commands
---

# /help — Show Available Commands

Lists all available commands.

Usage: `/help`

## Engine commands

| Command | What |
|---------|------|
| `/post [topic]` | Start content pipeline (delegates to @post subagent) |
| `/publish [id\|all]` | Queue to production (X / LinkedIn / Buffer) |
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

## Behind the scenes

Every command ultimately invokes `spiel <engine-subcommand>`. The shim is at `~/.local/bin/spiel` and resolves the vault from `~/.config/opencode/.env`, so commands work from any project or IDE on the local machine.
