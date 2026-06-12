# AGENTS.md — ShayanWiki Agent Control System

State machines + governance for both agentic loops. The LLM performs the
**creative** steps (analyzing, drafting). Scripts perform the **mechanical**
steps (transitions, gates, posting). The two never overlap.

> **Engine:** `scripts/engine.py` (state machine), `scripts/state.py` (paths),
> `scripts/pipeline.sh` (CLI wrapper). The canonical state table is in
> `scripts/state_machine.py` — edit it to change transitions.
>
> **Single source of truth:**
> - `rules.yaml` — mechanical config (gates, char limits, keywords, posting mode)
> - `concepts/voice-and-gates.md` — LLM voice + 4-check + 10-gate + 8-step compiler
> - `concepts/icp-offer.md` — ICP + offer + funnel stages
> - `concepts/funnel-and-matrix.md` — funnel + archetypes + matrix
> - `concepts/session-as-content.md` — methodology + session schema
> - `concepts/voice-corpus.md` — 8 canonical examples (read before drafting)

---

## Two Loops

```
WIKI LOOP:     IDLE → INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE → COMPLETE → IDLE
CONTENT LOOP:  IDLE → SESSION → STRATEGY → COMPILE → DRAFT → GATE → QUEUE → PUBLISH → ARCHIVE → IDLE
```

Each `→` is a `bash scripts/pipeline.sh <state>` call. LLM does the creative
work at DRAFTING (write posts) and the LLM-judged gates at GATE_CHECK. Everything
else is script.

---

## State Machine: Wiki

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | start | Read `.wiki-state` | State valid | Command |
| INGESTING | `/extract` | Add frontmatter, validate domain | Frontmatter + content + domain | ANALYZING |
| ANALYZING | ingest ok | Extract entities, apply page thresholds | Threshold decision for each item | RECONCILING |
| RECONCILING | analyze ok | Create or update pages; preserve contradictions | Append, never overwrite | INDEXING |
| LINKING | optional | Add 0-3 wikilinks per page | Semantic relevance | INDEXING |
| INDEXING | reconcile ok | Update `index.md`, write `log.md` | Catalog + log entry | VALIDATING |
| VALIDATING | index ok | Check frontmatter, wikilinks, redundancy | All critical checks pass | COMPLETE |
| COMPLETE | validate ok | Reset to IDLE | State file updated | IDLE |

---

## State Machine: Content

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | start | Read state | State valid | Command |
| SESSION_CAPTURE | `/post` | Mode 1: today's session. Mode 2: topic. Save `.content-brief.json` | Brief has strategy pages + source kind | STRATEGY_LOAD |
| STRATEGY_LOAD | capture ok | LLM classifies: archetype (S1-S10), vertical, funnel stage, ICP layer | All strategy pages listed | ICP_WORLD_BUILD |
| ICP_WORLD_BUILD | strategy ok | Run 8-step Compiler; write `core_insight` + 6 meanings + selection to brief | core_insight + selected_meaning populated | DRAFTING |
| DRAFTING | compile ok | Read templates; write posts to `content/queue/` with frontmatter | Frontmatter + char count + quality test | GATE_CHECK |
| BANNER | auto-substep | `banner.py` generates PNGs and writes `banner:` frontmatter | Each draft has banner file | GATE_CHECK |
| GATE_CHECK | draft ok | `gates.py --all` runs 16 mechanical checks; LLM runs 4-check + 10-gate | All pass → composite ≥ 0.85 | QUEUE / REVISING |
| REVISING | gate fail | Fix failing sections, max 2 cycles | Gates re-pass | GATE_CHECK / scrap |
| QUEUE | gate pass | Frontmatter complete; publish-toggle respected | Frontmatter complete | PUBLISHING / IDLE (hold) |
| PUBLISHING | user confirm | `post_x.py` or `post_linkedin.py` POSTs; archive to `posted/` | API call succeeded | ARCHIVING |
| ARCHIVING | publish ok | Move file, update frontmatter (posted_at + tweet_id/linkedin_url) | File moved | ANALYZING_POST |
| ANALYZING_POST | archive ok | Aggregate engagement; flag anti-patterns | Analysis logged | COMPLETE_POST |
| COMPLETE_POST | analyze ok | Reset to IDLE | State file updated | IDLE |

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

### Page Schemas

Wiki pages require frontmatter: `title`, `created`, `updated`, `type` (entity|concept|comparison|query|summary), `tags`, `sources`, `confidence` (high|medium|low), `contested`, `contradictions`.

Tag taxonomy lives in `AGENTS.md` only — `wiki-health.py` parses it from the `## Tag Taxonomy` section. Domains: identity, strategic-thinking, systems-design, psychology, cognitive, autonomy, execution, business, technology, philosophy, narrative, leadership. Qualities: core-strength, core-weakness, operational-pattern, psychological-trap, non-negotiable, healing-path, synthesis. Meta: comparison, timeline, contradiction-flag, foundational.

---

## Logging

JSONL to `logs/YYYY-MM-DD.jsonl`. View with:

```bash
bash scripts/engine.py log --days 7 --tail 20
bash scripts/engine.py log --level ERROR
```

---

## Commands

| Command | What | Call |
|---------|------|------|
| `/health` | Wiki health check (orphans, links, frontmatter, stale, redundancy) | `pipeline.sh wiki-health` |
| `/queue` | Show content queue grouped by platform | `pipeline.sh queue` |
| `/log` | Recent log entries | `engine.py log --tail 20` |
| `/extract [file]` | Ingest raw → wiki pages | `pipeline.sh wiki-extract <file>` + per-state |
| `/post` | Content pipeline (mode 1: session, mode 2: topic) | `pipeline.sh post-start [topic]` |
| `/publish [id\|all]` | Queue → production (checks toggle, posts to API) | `pipeline.sh post-publish` |

`/post` mode 1 (empty): engine checks for today's session log; if missing, auto-creates stub. Mode 2: `post <topic>` runs `post_topic.py`.

After SESSION_CAPTURE, run `pipeline.sh post-compile` (8-step Compiler) and write `core_insight` + 6 meanings + selection to `.content-brief.json` before drafting. After DRAFTING, run `pipeline.sh post-banner` to auto-generate banners.

---

## Portability

Set `VAULT_DIR` to run from any directory. All scripts use it with a dynamic fallback to the vault root (parent of `scripts/`). Configure in `~/.config/opencode/opencode.jsonc` under `env:` for automatic availability.

---

## Extract Dedup

`/extract` uses `.raw-manifest.json` (SHA256) to skip unchanged files. To force re-extract, delete the entry from `.raw-manifest.json` or modify the source.
