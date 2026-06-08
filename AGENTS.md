# AGENTS.md — SpielEngine Agent Control System

This is the **government** that enforces both agentic loops. Read this before any other file. The state machines below define every action, gate, and transition. If a behavior is not in a state definition, it does not execute.

**Replace `YOUR_NAME` and `YOUR_DOMAIN`** with your identity before first use.

---

## Overview: Two Agentic Loops

### Loop 1: Wiki Management (knowledge → structure)

```
/extract → INGEST → ANALYZE → RECONCILE → INDEX → VALIDATE → IDLE
            └────── Act ──────┘  └─ Observe/Evaluate ┘  └─ Update ┘
```

Feed raw sources through the pipeline. Each state has one entry gate, one action, one validation gate, and one exit transition. No overlapping states.

### Loop 2: Content Posting (session → publish)

```
/post → SESSION → STRATEGY → DRAFT → GATES → QUEUE → REVIEW? → PUBLISH → ARCHIVE → ANALYZE → IDLE
        └── Act ──┘  └── Observe/Evaluate ──┘              └── Update ┘
```

Convert session work into platform posts. The REVIEW? step checks the human-review toggle before deciding to publish or wait.

### Cross-Loop Flow

```
WIKI LOOP                           CONTENT LOOP
raw/ source                         
  /extract                          
  ▼                                 
concept pages ──── feed ───────▶   /post reads strategy pages
  ▲                                │
  │ ◌◀── learn from ────────────  /analyze returns engagement data
  │                                │
  │ ◌◀── update AP lib ─────────  /reject appends anti-pattern
  │                                │
  │ ◌◀── evolve style ──────────  style-guide.md updated
```

Feed-forward: wiki concepts are the knowledge base /post reads. Feed-back: content outcomes update the wiki — anti-pattern library grows, style guide evolves, stale concepts get pruned.

---

## State Machine: Wiki Management

```
IDLE ──> INGESTING ──> ANALYZING ──> RECONCILING ──> INDEXING ──> VALIDATING ──> COMPLETE ──> IDLE
                LINKING ──> (optional sub-step, only on /relink or /extract --link)
```

### STATE: IDLE
**Entry:** System start, or previous COMPLETE
**Action:** Read .wiki-state. Check for pending actions. Report status if asked.
**Gate:** .wiki-state is valid
**Exit:** Command received → transition to matching state

### STATE: INGESTING
**Entry:** `/extract [source]` or new file in raw/
**Action:**
  1. Read raw source file
  2. Add frontmatter (source_url if web, ingested date, sha256 hash)
  3. Validate file has readable content within domain
**Gate:** Frontmatter valid + content non-empty + within domain
**Exit:** File saved → ANALYZING
**On failure:** Log error, stay INGESTING, report to user

### STATE: ANALYZING
**Entry:** INGESTING completed
**Action:**
  1. Extract entities, concepts, and patterns from source
  2. Check existing pages against extracted items
  3. Apply page thresholds:
     - Concept in 2+ sources → needs page
     - Central to one source → needs page
     - Passing mention → skip, log note
     - Covered by existing → update existing
**Gate:** Threshold decision made for each extracted item
**Exit:** Entities identified → RECONCILING
**On nothing to create/update:** Skip to INDEXING for log entry

### STATE: RECONCILING
**Entry:** ANALYZING completed
**Action:**
  1. For each item needing a page: check if page exists
  2. If exists: read it, diff with new info, append updates
  3. If new: create page using matching template
  4. Preserve contradictions with date-stamped notes
  5. Add provenance markers (backlinks to raw/ source)
**Gate:** Every update appends, never overwrites. Frontmatter dates bumped.
**Exit:** Pages created/updated → INDEXING

### STATE: LINKING (optional)
**Entry:** `/relink [page]` or `/extract --link`
**Action:**
  1. Scan page body for existing [[wikilinks]]
  2. Search other pages for natural link targets
  3. Add 0-3 relevant wikilinks
  4. NEVER force a link that doesn't add meaning
**Gate:** Every link has semantic relevance. Target pages exist.
**Exit:** Links added → INDEXING

### STATE: INDEXING
**Entry:** RECONCILING (or LINKING) completed
**Action:**
  1. Add/update page entry in index.md under correct section
  2. Write log entry to log.md (format: `## [YYYY-MM-DD] action | subject`)
  3. If page was archived: update wikilinks to "(archived)"
**Gate:** index.md lists all pages. log.md entry written.
**Exit:** Index updated → VALIDATING

### STATE: VALIDATING
**Entry:** INDEXING completed
**Action:**
  1. Check frontmatter completeness (title, created/updated, type, tags, sources)
  2. Check all [[wikilinks]] in new/updated pages point to existing pages
  3. Run redundancy check: does new page overlap >60% with any existing?
  4. Update .wiki-state with validation results
**Gate:** All critical checks pass. Warnings logged but non-blocking.
**Exit:** Pass → COMPLETE. Fail → INGESTING or IDLE with report.

### STATE: COMPLETE
**Entry:** VALIDATING passed
**Action:**
  1. Write final .wiki-state (state: IDLE, last_completed: now)
  2. Report summary to user (files created/updated, gates passed, warnings)
**Exit:** System returns to IDLE

---

## State Machine: Content Posting

```
IDLE ──> SESSION_CAPTURE ──> STRATEGY_LOAD ──> DRAFTING ──> GATE_CHECK ──> QUEUE ──> REVIEW? ──> PUBLISHING ──> ARCHIVING ──> ANALYZING ──> COMPLETE ──> IDLE
                │                                                                           │
                └── REVISING <── (gate fail > 2) ────────────────────────────────────────────┘
                                                                                             │
                                                                             toggle OFF ──────┘
```

### STATE: SESSION_CAPTURE
**Entry:** `/post` or `/post [about topic]`
**Action:**
  1. If topic provided: build a mini-session context around that topic
  2. If no topic: read most recent session log from content/sessions/
  3. If no session log: ask user what they worked on
  4. Determine pillar decision
**Gate:** Session context captured. Pillar decision made.
**Exit:** Context ready → STRATEGY_LOAD

### STATE: STRATEGY_LOAD
**Entry:** SESSION_CAPTURE completed
**Action:** Load strategy pages:
  1. `concepts/tone-of-voice.md` (voice spec)
  2. `concepts/content-strategy.md` (goals, audience, cadence)
  3. `concepts/content-types.md` (archetypes + decision tree)
  4. `concepts/standalone-quality-test.md` (4-check baseline)
  5. `concepts/platform-format-specs.md` (per-surface format)
**Gate:** All strategy pages read. Key rules extracted.
**Exit:** Strategy loaded → DRAFTING

### STATE: DRAFTING
**Entry:** STRATEGY_LOAD completed
**Action:**
  1. If pillar: write pillar blog + 3 LinkedIn + 5-10 X
  2. If not pillar: write casual update + 1-3 X posts
  3. Each draft follows platform template (templates/*.md)
  4. Apply voice from style guide
**Gate:** Drafts written. Templates followed. Voice matches.
**Exit:** Drafts ready → GATE_CHECK

### STATE: GATE_CHECK
**Entry:** DRAFTING completed
**Action:** For every draft:
  1. Run standalone-quality-test
  2. Run copywriting gate checks
  3. Compute composite score
**Gate:** Score recorded per draft
**Exit:** Pass → QUEUE. Almost → REVISING. Fail → scrap.

### STATE: REVISING
**Entry:** GATE_CHECK returned "almost"
**Action:**
  1. Identify which gates failed
  2. Regenerate failing sections
  3. Re-run GATE_CHECK
**Gate:** Max 2 revision cycles. After 2, kill the draft.
**Exit:** Pass on retry → QUEUE. Fail after 2 → scrap.

### STATE: QUEUE
**Entry:** GATE_CHECK passed (or REVISING passed)
**Action:**
  1. Save draft to content/queue/
  2. Include full frontmatter with scores
  3. Check posting toggle in .content-config
**Gate:** File saved with complete frontmatter
**Exit:** Manual → wait. Auto → PUBLISHING.

### STATE: PUBLISHING
**Entry:** QUEUE completed AND toggled to publish
**Action:**
  1. Read draft from queue file
  2. Check platform API keys
  3. POST to platform API
  4. On failure: keep in queue with status: api-failed
**Gate:** API call made. Response captured.
**Exit:** Success → ARCHIVING. Fail → queue.

### STATE: ARCHIVING
**Entry:** PUBLISHING succeeded, or user rejects a draft
**Action:**
  1. Move to content/posted/ or content/rejected/
  2. Update frontmatter with posted_at / rejected_at
  3. If rejected: append anti-pattern to content/rejected/README.md
**Gate:** File moved. Frontmatter updated.
**Exit:** Archived → ANALYZING

### STATE: ANALYZING (content performance loop)
**Entry:** ARCHIVING completed
**Action:**
  1. Aggregate posted drafts by platform, pattern, engagement_ask
  2. Compare rejected patterns against posted patterns
  3. If failure pattern emerges: update style guide
**Gate:** Analysis logged
**Exit:** Analysis done → COMPLETE

### STATE: COMPLETE (posting)
**Entry:** ANALYZING completed
**Action:**
  1. Update .content-config with latest analysis
  2. Report to user: what was posted, what was learned
  3. Suggest next steps
**Exit:** IDLE

---

## Command Reference

| Command | What it does | State machine |
|---------|-------------|---------------|
| `/extract [source]` | Ingest raw source → wiki pages | Wiki |
| `/extract --link` | Same + run LINKING sub-step | Wiki |
| `/reconcile [page]` | Re-read source → update page | Wiki |
| `/relink [page]` | Rebuild cross-links | Wiki |
| `/index` | Rebuild index.md | Wiki |
| `/health` | Full validation check | Wiki |
| `/prune` | Archive stale, merge duplicates | Wiki |
| `/state` | Show system state | System |
| `/compact [topic]` | Consolidate concepts | Wiki |
| `/post [about]` | Session → queue drafts | Content |
| `/queue` | Show queue status | Content |
| `/publish [id\|all]` | Queue → production | Content |
| `/schedule [id] [date]` | Schedule draft | Content |
| `/optimize [id]` | Re-run gates, improve | Content |
| `/analyze [period]` | Analyze posted performance | Content |
| `/reject [id] [reason]` | Reject + learn | Content |
| `/config [key] [value]` | View/modify config | System |
| `/log [n]` | Show last N entries | System |
| `/help [command]` | Command synopsis | System |
