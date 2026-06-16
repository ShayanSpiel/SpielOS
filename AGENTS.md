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

---

## Human-Review Toggle

`rules.yaml §posting`:

```yaml
posting:
  mode: manual              # manual | auto-threshold | auto-always
  quality_threshold: 0.85
  require_confirm: [blog, linkedin]
  max_auto_day: 3
```

- **manual**: `/publish` shows draft, waits for "yes" before API call.
- **auto-threshold**: if composite score ≥ 0.85, auto-publish; else pause.
- **auto-always**: zero human review (opt-in only).

Composite score = (passes / total gates). With current `gates.py` (16 mechanical)
+ LLM gates (4-check standalone + 10-gate extended = 14), total ≈ 30.

---

## Quality Gates

### Pre-Creation (ANALYZING)
- **Threshold**: 2+ sources or core to one source → create. Passing mention → skip.
- **Redundancy**: >60% overlap → update, don't create.
- **Domain**: must be within identity, strategy, psychology, systems, execution, business, tech, philosophy, narrative, leadership.

### Pre-Write (RECONCILING)
- **Frontmatter**: title, created, updated, type, tags, sources.
- **Provenance**: claims link back to `raw/`.
- **Contradiction**: preserve both with date stamps.

### Post-Write (VALIDATING)
- **Link health**: all `[[wikilinks]]` resolve.
- **Index**: new page listed in `index.md`.
- **Log**: action recorded in `log.md`.

### Content (GATE_CHECK)
- **Banner**: `banner:` frontmatter field pointing to existing file in `assets/banners/`.
- **Mechanical**: 16 checks in `gates.py` (char count, hook, em-dash, word repeat, architecture leak, audience named, lesson surfaced, generic statement, project as subject, closing, frontmatter, dollar in note, strategy void, icp present, banner, grounded reference). All parameters from `rules.yaml`.
- **Creative**: 4-check standalone test + 10-gate extended. See `concepts/voice-and-gates.md`.

---

## Logging

JSONL to `logs/YYYY-MM-DD.jsonl`. View with:

```bash
bash scripts/engine.py log --days 7 --tail 20
bash scripts/engine.py log --level ERROR
```

---

## Portability

Set `VAULT_DIR` to run from any directory. All scripts use it with a dynamic fallback to the vault root (parent of `scripts/`). Configure in `~/.config/opencode/opencode.jsonc` under `env:` for automatic availability.

---

## Pipeline Determinism Contract

The LLM may request execution, draft text, and run bash invocations. The LLM may
NOT call `Write` for `content/queue/` or `pages/` files. Only `pipeline.sh` (via
`post-draft`) may write to those paths. `post-verify` is the receipt — its output
is the only valid assertion of pipeline state.

---

## Extract Dedup

`/extract` uses `.raw-manifest.json` (SHA256) to skip unchanged files. To force re-extract, delete the entry from `.raw-manifest.json` or modify the source.

