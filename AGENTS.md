# AGENTS.md — Engine Control System

State machines + governance for both agentic loops.
LLM performs creative steps (analyzing, drafting). Scripts perform mechanical steps.

## Two Loops

```
WIKI LOOP:     IDLE → INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE → COMPLETE → IDLE
CONTENT LOOP:  IDLE → SESSION → STRATEGY → COMPILE → DRAFT → GATE → QUEUE → PUBLISH → ARCHIVE → IDLE
```

## Wiki State Machine

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | start | Read `.wiki-state` | State valid | Command |
| INGESTING | extract | Add frontmatter, validate domain | Frontmatter + content + domain | ANALYZING |
| ANALYZING | ingest ok | Extract entities, apply thresholds | Threshold decision | RECONCILING |
| RECONCILING | analyze ok | Create/update pages; preserve contradictions | Append never overwrite | INDEXING |
| INDEXING | reconcile ok | Update index.md, write log.md | Catalog + log entry | VALIDATING |
| VALIDATING | index ok | Check frontmatter, wikilinks, redundancy | All checks pass | COMPLETE |
| COMPLETE | validate ok | Reset to IDLE | State file updated | IDLE |

## Content State Machine

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | start | Read state | State valid | Command |
| SESSION_CAPTURE | post | Save brief | Brief has strategy pages | STRATEGY_LOAD |
| STRATEGY_LOAD | capture ok | Classify archetype, vertical, funnel stage, ICP layer | Strategy populated | ICP_WORLD_BUILD |
| ICP_WORLD_BUILD | strategy ok | Run 8-step Compiler | core_insight + meaning populated | DRAFTING |
| DRAFTING | compile ok | Write posts to content/queue/ with frontmatter | Frontmatter + char count + quality | GATE_CHECK |
| GATE_CHECK | draft ok | 16 mechanical checks + LLM gates | Composite ≥ 0.85 | QUEUE / REVISING |
| QUEUE | gate pass | Frontmatter complete | Frontmatter complete | PUBLISHING / IDLE |
| PUBLISHING | user confirm | POST to platform | API success | ARCHIVING |
| ARCHIVING | publish ok | Move file, update frontmatter | File moved | COMPLETE_POST |
| COMPLETE_POST | archive ok | Reset to IDLE | State file updated | IDLE |

## Commands

| Command | Action |
|---------|--------|
| `/analyze` | Run analysis step on pending items |
| `/compact` | Merge redundant or overlapping pages |
| `/config` | Show current engine configuration |
| `/extract [file]` | Ingest raw → wiki pages |
| `/health` | Wiki health check (orphans, links, frontmatter) |
| `/help` | Show all available commands |
| `/index` | Display the wiki index |
| `/log` | Recent log entries |
| `/optimize` | Suggest tagging, linking, and pruning opportunities |
| `/post [topic]` | Start content pipeline (session or topic) |
| `/prune` | Identify and remove stale or low-confidence pages |
| `/publish [id|all]` | Queue → production (X / LinkedIn) |
| `/queue` | Show content queue grouped by platform |
| `/reconcile` | Reconcile extracted content into wiki pages |
| `/reject` | Remove a draft from the queue |
| `/relink` | Scan and repair broken wikilinks |
| `/schedule` | Set publish timestamps for queued content |
| `/state` | Show current state of wiki and content loops |

