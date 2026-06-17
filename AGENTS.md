# AGENTS.md — Spiel Engine Agent Control System

State machines + governance for both agentic loops. The LLM performs the
**creative** steps (analyzing, drafting). Scripts perform the **mechanical**
steps (transitions, gates, posting). The two never overlap.

> **Engine:** `scripts/engine.py` (orchestrator + CLI), `scripts/engine_state.py`
> (state machine + paths + brief validation + handoff TTL), `scripts/engine_config.py` (rules.yaml reader), `scripts/wizard.py` (format + publish wizards), `scripts/compiler.py` (compiler write), `scripts/banner_tool.py` (banner generator). The canonical state table is in `scripts/engine_state.py:58` — edit it to change transitions.
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
WIKI LOOP:     IDLE → INGESTING → ANALYZING → RECONCILING → [LINKING] → INDEXING → VALIDATING → COMPLETE → IDLE
CONTENT LOOP:  IDLE → SESSION_CAPTURE → COMPILE → SELECT → FORMAT_WIZARD → DRAFTING → BANNER → GATE_CHECK → QUEUE → PUBLISHING → ARCHIVING → ANALYZING_POST → COMPLETE_POST → IDLE
```

Each `→` is a `spiel <command>` call. The **orchestrator**
(`spiel content run`) chains the loop automatically,
pausing at exactly two LLM handoffs and two human checkpoints:

- **LLM handoff 1 (COMPILE):** LLM runs 8-step Compiler, writes via `content compile-write`
- **Human checkpoint 1 (FORMAT_WIZARD):** User picks formats (x/linkedin/blog)
- **LLM handoff 2 (DRAFTING):** LLM writes draft files, registers via `draft-write` + `draft-done`
- **Human checkpoint 2 (QUEUE/publish-wizard):** User picks publish/hold per draft

---

## State Machine: Wiki

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | start | Read `.wiki-state` | State valid | Command |
| INGESTING | `wiki extract` | Add frontmatter, validate domain | Frontmatter + content + domain | ANALYZING |
| ANALYZING | ingest ok | Extract entities, apply page thresholds | Threshold decision for each item | RECONCILING |
| RECONCILING | analyze ok | Create or update pages; preserve contradictions | Append, never overwrite | [LINKING /] INDEXING |
| LINKING | optional | Add 0-3 wikilinks per page | Semantic relevance | INDEXING |
| INDEXING | reconcile ok | Update `index.md`, write `log.md` | Catalog + log entry | VALIDATING |
| VALIDATING | index ok | Check frontmatter, wikilinks, redundancy | All critical checks pass | COMPLETE |
| COMPLETE | validate ok | Reset to IDLE | State file updated | IDLE |

---

## State Machine: Content

| State | Entry | Action | Gate | Exit |
|-------|-------|--------|------|------|
| IDLE | `content run` | Read `.wiki-state`, load brief | State valid | SESSION_CAPTURE |
| SESSION_CAPTURE | auto | Load strategy pages, find/create session, auto-classify, save brief | Brief has strategy + source | COMPILE |
| COMPILE | auto | Print 8-step Compiler. **LLM handoff**: LLM runs 8 steps, calls `content compile-write` (5-min TTL) | `core_insight` + 6 meanings + `selected_meaning` populated | SELECT |
| SELECT | auto | Rank templates by archetype/axis/funnel/ICP | At least 1 template ranked | FORMAT_WIZARD |
| FORMAT_WIZARD | auto | **Human checkpoint**: format wizard asks x/linkedin/blog | `wizard.formats` populated | DRAFTING / IDLE (hold) |
| DRAFTING | auto | **LLM handoff**: LLM writes drafts to `content/queue/`, registers via `draft-write`, signals via `draft-done` (5-min TTL) | `drafting.done` + queue files | BANNER |
| BANNER | auto | `banner_tool.py` generates PNGs, writes `banner:` frontmatter | Each draft has banner file | GATE_CHECK |
| GATE_CHECK | auto | Run 16 mechanical + 4-check + 10-gate; fail → DRAFTING (revision) | All pass | QUEUE / DRAFTING |
| QUEUE | auto | **Human checkpoint**: publish wizard per draft | `wizard.publish_decisions` confirmed | PUBLISHING / IDLE (hold) |
| PUBLISHING | user confirm | Dispatch via Buffer/direct API; archive to `posted/` | API call succeeded | ARCHIVING |
| ARCHIVING | publish ok | Move file, update frontmatter (posted_at + IDs) | File moved | ANALYZING_POST |
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

- **manual**: `content publish` shows draft, waits for "yes" before API call.
- **auto-threshold**: if composite score >= 0.85, auto-publish; else pause.
- **auto-always**: zero human review (opt-in only).

Composite score = (passes / total gates). With current `gates.py` (16 mechanical)
+ LLM gates (4-check standalone + 10-gate extended = 14), total ~= 30.

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
- **Mechanical**: 16 checks in `scripts/gates.py` (char count, hook, em-dash, word repeat, architecture leak, audience named, lesson surfaced, generic statement, project as subject, closing, frontmatter, dollar in note, strategy void, icp present, banner, grounded reference). All parameters from `rules.yaml`.
- **Creative**: 4-check standalone test + 10-gate extended. See `concepts/voice-and-gates.md`.

### Banner Tool (`scripts/banner_tool.py`)

Self-contained Python module + CLI for generating banner images. One entry point for the engine, the post subagent, the human, and tests.

- **Template contract:** `scripts/banner-templates/*.html` — every configurable value lives in a `:root` CSS block. The template is a valid, self-contained HTML file you can open in a browser.
- **Config source:** `assets/brand-config.json → banner.tokens` — the tool injects these into the template's `:root` block at render time. Single source of truth for all visual knobs.
- **Render engine:** Playwright + system Chrome (`/Applications/Google Chrome.app/...` on macOS). No Node, no Puppeteer, no shell-out dance.
- **Live preview:** `python3 -m banner_tool preview --template default --open` writes a real HTML file to `assets/banners/.preview/` and opens it in your browser. Edit the template, hit refresh, see the new look.
- **CLI:**
  - `python3 -m banner_tool render --template default --title "..." --subtitle "..." --out x.png`
  - `python3 -m banner_tool preview --template default [--open]`
  - `python3 -m banner_tool generate-queue` (called by the engine)
  - `python3 -m banner_tool generate-draft --file content/queue/x.md`
  - `python3 -m banner_tool test` (snapshot regression)
- **Tests:** `pytest tests/test_banner_tool.py` — 14 unit tests + 1 snapshot regression. First run creates `tests/snapshots/default.png`; subsequent runs fail on >2% pixel drift.
- **Customizing the look:** edit the `:root` block in `default.html` OR edit the tokens in `assets/brand-config.json`. Both produce the same result. The template is for layout, the tokens are for brand values.

### Page Schemas

Wiki pages require frontmatter: `title`, `created`, `updated`, `type` (entity|concept|comparison|query|summary), `tags`, `sources`, `confidence` (high|medium|low), `contested`, `contradictions`.

Tag taxonomy lives in `AGENTS.md` only — `engine_health.py` reads it from the `## Tag Taxonomy` section. Domains: identity, strategic-thinking, systems-design, psychology, cognitive, autonomy, execution, business, technology, philosophy, narrative, leadership. Qualities: core-strength, core-weakness, operational-pattern, psychological-trap, non-negotiable, healing-path, synthesis. Meta: comparison, timeline, contradiction-flag, foundational.

---

## Publishing Platforms

Three publishers are wired in, in priority order:

| Publisher | Script | Use case | Env vars |
|---|---|---|---|
| **Buffer** (primary) | `publishers/buffer.py` | Multi-platform fan-out (X + LinkedIn + Threads) in one call | `BUFFER_ACCESS_TOKEN`, `BUFFER_CHANNEL_IDS` |
| X direct (fallback) | `publishers/twitter.py` | Direct X API when Buffer is down or out of quota | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` |
| LinkedIn direct (fallback) | `publishers/linkedin.py` | Direct LinkedIn UGC API as above | `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN` |

**Buffer free tier caps:** 3 channels, 10 posts/channel in queue, 3,000 API requests/month. This is sufficient for `max_auto_day: 3` from `posting` config.

**Draft frontmatter contract:**
- `platform: buffer` -> routed to `publishers/buffer.py` (multi-platform)
- `platform: x` -> routed to `publishers/twitter.py` (direct)
- `platform: linkedin` -> routed to `publishers/linkedin.py` (direct)
- `platform: blog` -> routed to `scripts/publish-blog.sh` (GH Pages)

**Archive frontmatter (Buffer):**
- `buffer_post_ids: {x: "...", linkedin: "...", threads: "..."}` -- per-service post IDs
- `buffer_channel_ids: [...]` -- which Buffer channels received the post
- `tweet_id`, `linkedin_share_urn`, `threads_post_id` -- surfaced from Buffer response so downstream code finds them
- `tweet_url`, `linkedin_url`, `threads_url` -- public URLs when available

---

## Logging

JSONL to `logs/YYYY-MM-DD.jsonl`. View with:

```bash
spiel log --days 7 --tail 20
spiel log --level ERROR
```

---

## Commands

The `spiel` shim is the single entrypoint. It resolves the vault from
`~/.config/opencode/.env` and execs `scripts/engine.py` inside it — from
any project cwd, in any IDE. Use `spiel` everywhere.

| Command | What | Call |
|---------|------|------|
| `/health` | Wiki health check (orphans, links, frontmatter, stale, redundancy) | `spiel wiki health` |
| `/queue` | Show content queue grouped by platform | `spiel queue` |
| `/log` | Recent log entries | `spiel log --tail 20` |
| `/extract [file]` | Ingest raw -> wiki pages | `spiel wiki extract <file>` |
| `/post [topic]` | Content pipeline (mode 1: session, mode 2: topic) | `spiel content run [topic]` |
| `/compile` | Run 8-step Compiler display | `spiel content compile` |
| `/select` | Run template selector | `spiel content select` |
| `/draft` | Mark drafting state (LLM writes queue/ files) | `spiel content draft` |
| `/banner` | Auto-generate banners for all drafts | `spiel content banner` |
| `/banner-preview [template]` | Open live HTML preview of template in browser | `python3 -m banner_tool preview --template default --open` |
| `/banner-regen [id]` | Re-render one banner (or all) | `python3 -m banner_tool generate-draft --file <path>` |
| `/banner-test` | Run snapshot regression test | `python3 -m pytest tests/test_banner_tool.py` |
| `/gate` | Run mechanical + LLM gates | `spiel content gate` |
| `/publish` | Bulk publish all queued drafts | `spiel content publish` |
| `/publish [id]` | Publish specific draft (filename, stem, or short ref) | `spiel content publish 2026-06-17-x-draft.md` |
| `/hold` | Return QUEUE -> IDLE without publishing | `spiel content hold` |
| `/analyze` | Pull Buffer engagement, update perf.json, re-rank templates | `spiel content analyze` |
| `/rank` | Re-run the template ranker | `spiel content rank-templates` |
| `/buffer-setup` | List Buffer channels and write IDs to `.env` | `python3 scripts/setup_buffer_channels.py --pick 3` |
| `--version` | Print shim version + resolved vault path | `spiel --version` |
| `--where` | Print the resolved vault path (no python call) | `spiel --where` |

`/post` mode 1 (empty): engine checks for today's session log; if missing, auto-creates stub. Mode 2: `post <topic>` runs auto-classify and saves brief.

**New orchestrator workflow:**
1. `spiel content run` — runs full chain, pauses at handoffs/checkpoints
2. At COMPILE handoff: LLM runs 8 steps, calls `spiel content compile-write`
3. At FORMAT_WIZARD: user picks formats via `spiel content wizard`
4. At DRAFTING handoff: LLM writes drafts, calls `spiel content draft-write` + `draft-done`
5. At QUEUE: user picks publish/hold via `spiel content publish-wizard`

After DRAFTING, run `spiel content banner` to auto-generate banners.

---

## Portability

The `spiel` shim (`scripts/bin/spiel`, also installed at `~/.local/bin/spiel`)
resolves the vault from these sources (first match wins):

1. `$VAULT_DIR` env var (inline override)
2. `<cwd>/.spiel-vault` (project-local override file)
3. `~/.config/opencode/.env` (the global source of truth)
4. The shim's own location, if it lives at `<vault>/scripts/bin/spiel`

This means commands work from **any project, any IDE, any shell** on the local
machine — not just the vault root. All scripts inside the engine also
`os.chdir(VAULT)` at startup so any internal subprocess uses absolute paths.

---

## Pipeline Determinism Contract

The LLM may request execution, draft text, and run bash invocations. The LLM may
NOT call `Write` for `content/queue/` or `pages/` files. Only `engine.py` (via
`engine.py content draft`) may write to those paths. `content complete` is the
receipt -- its output is the only valid assertion of pipeline state.

---

## Extract Dedup

`/extract` uses `.raw-manifest.json` (SHA256) to skip unchanged files. To force re-extract, delete the entry from `.raw-manifest.json` or modify the source.
