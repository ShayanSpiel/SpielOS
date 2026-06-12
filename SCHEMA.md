# Wiki Schema — ShayanWiki (Strategic Builder Second Brain)

> **Schema reference only.** For state machines, execution pipeline, and governance rules, see `AGENTS.md`.

## Domain

**Personal identity, strategic thinking systems, and operational execution.**

This wiki serves as an externalized cognitive extension for a **strategic builder**: someone who integrates psychology, business, technology, systems, philosophy, and strategy into unified models. The wiki compounds knowledge about personal growth, system design, autonomy architecture, and reality-based execution.

**Core purpose:** Track identity evolution, operational patterns, psychological dynamics, and strategic frameworks while maintaining cross-references so the agent can synthesize across all ingested material.

## Conventions

- **File naming:** lowercase with hyphens (e.g., `strategic-builder.md`, not `Strategic Builder.md`)
- **Frontmatter required** on all wiki pages (see Frontmatter section)
- **Cross-links recommended:** Link naturally to relevant pages via `[[wikilinks]]`. Prefer semantic relevance over quantity.
- **Update policy:** Bump `updated` date on every edit; never modify files in `raw/`
- **Index maintenance:** Add every new page to `index.md`; archive superseded content to `_archive/`
- **Provenance markers:** On pages synthesizing 3+ sources, append `^[raw/somefile.md]` citations to specific paragraphs
- **Page thresholds:** Create a page only if the concept appears in 2+ sources OR is central to one source

## Frontmatter (Required on All Pages)

```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from-taxonomy-below]
sources: [raw/article-name.md, raw/another-source.md]
confidence: high | medium | low           # Optional but recommended for opinion-heavy topics
contested: false                         # Optional: set true when claims contradict other pages
contradictions: [other-page-slug]        # Optional: list page slugs with conflicting claims
---
```

**Fields explained:**
- `confidence`: How well-supported are the claims? Use `high` only for well-corroborated facts. For single-source or opinion-heavy topics, use `medium` or `low`.
- `contested`: Set to `true` when new info contradicts existing content (see Update Policy).
- `contradictions`: List page slugs that conflict with this one; enables user to review contradictions explicitly.

## Raw Sources Frontmatter

For files you add to `raw/`, include:

```yaml
---
source_url: https://example.com  # or omit for local notes
ingested: YYYY-MM-DD
sha256: <hex-digest-of-content-after-frontmatter>
---
```

The `sha256` enables drift detection—if the same URL is re-ingested with a different hash, it flags source changes.

## Tag Taxonomy

Use only these tags (add new ones to SCHEMA.md first):

**Domains:**
- identity
- strategic-thinking
- systems-design
- psychology
- cognitive
- autonomy
- execution
- business
- technology
- philosophy
- narrative
- leadership

**Qualities:**
- core-strength
- core-weakness
- operational-pattern
- psychological-trap
- non-negotiable
- healing-path
- synthesis

**Meta:**
- comparison
- timeline
- contradiction-flag
- foundational

## Page Thresholds (Strictly Follow)

1. **Create a page** when an entity/concept appears in 2+ sources OR is central to one source
2. **Add to existing page** when a source mentions something already covered
3. **DON'T create a page** for passing mentions, minor details, or things outside the domain
4. **Split a page** when it exceeds ~200 lines — break into sub-topics with cross-links
5. **Archive a page** when its content is fully superseded; move to `_archive/`

## Entity Pages

One page per notable person, company, project, or tool. Include:
- Brief overview
- Key facts/dates/relationships
- Cross-references to related entities
- Source attribution in frontmatter

Example structure (YAML frontmatter + body only):
```yaml
---
title: strategic-builder
created: 2024-01-15
updated: 2026-06-02
type: entity
tags: [identity, core-strength]
sources: [raw/my-identity.md]
confidence: high
---

## Summary

Brief one-sentence overview (e.g., "Core identity as strategic builder who adapts to reality")

## Key Attributes

List 3-5 defining attributes with brief explanations.

## Cross-References

- [[psychology]]: connects psychological dynamics to execution
- [[operational-pattern]]: links to patterns you practice
```

## Concept Pages

One page per idea, pattern, framework, or theme. Include:
- Definition/explanation
- How it applies to your work
- Related concepts (cross-links)
- Sources (if applicable)

Example:
```yaml
---
title: disembodied-cognition
created: 2024-01-15
updated: 2026-06-02
type: concept
tags: [psychology, core-weakness]
sources: [raw/my-identity.md]
confidence: high
---

## Summary

Definition of the concept (1-2 sentences).

## Details

Core explanation with sub-points as needed.

## Cross-References

- [[integrative-intelligence]]: your counterbalance to over-abstraction
- [[grounding-action]]: practical antidotes to disembodied thinking
```

## Comparison Pages

Side-by-side analyses (use tables when comparing dimensions):

```yaml
---
title: autonomy-without-structure-vs-structure-without-autonomy
created: 2024-01-15
updated: 2026-06-02
type: comparison
tags: [psychological-trap]
sources: [raw/my-identity.md]
confidence: medium
---

## What's Being Compared

Explain why this comparison matters.

| Dimension | Autonomy w/o Structure | Structure w/o Autonomy |
|-----------|------------------------|------------------------|
| Stability | Chaotic               | Rigid                 |
| Growth    | Explosive but unguided| Limited                |

## Verdict

Synthesis of which works best and when.
```

## Update Policy (When New Info Conflicts)

1. **Check dates** — newer sources generally supersede older ones
2. **If genuinely contradictory**, note both positions with dates and sources
3. **Mark in frontmatter:** `contradictions: [other-page-slug]`
4. **Flag for user review** via lint report
5. **Append to existing page** if it's a minor update, not overwrite entire content

## Navigation Files

### index.md

Catalog all wiki pages with one-line summaries under section headers:

```markdown
# Wiki Index — ShayanWiki

> Content catalog. Every wiki page listed under its type with a one-line summary.
> Read this first to find relevant pages for any query.
> Last updated: 2026-06-02 | Total pages: 12

## Entities
<!-- Alphabetical within section -->
- [[strategic-builder]]: Core identity as strategic builder who adapts to reality
- [[integrative-intelligence]]: Ability to integrate multiple layers into unified models

## Concepts
- [[disembodied-cognition]]: Mind becoming too detached from grounded reality
- [[grounding-action]]: Grounding cognition into repeated action as antidote

## Comparisons
- [[autonomy-without-structure-vs-structure-without-autonomy]]: Psychological trap analysis

## Queries
<!-- Query results worth keeping -->
```

### log.md

Chronological record (append-only, rotate annually):

```markdown
# Wiki Log — ShayanWiki

> Chronological record of all wiki actions. Append-only.
> Format: `## [YYYY-MM-DD] action | subject`

## [2024-01-15] create | Initialized wiki from My Identity.md
- Created SCHEMA.md, index.md, log.md
- Ingested raw/my-identity.md (Strategic Builder core document)

## [2024-01-16] ingest | Additional notes added to raw/
- Added [[notes-from-article]] to raw/articles/
- Updated [[strategic-builder]] and [[integrative-intelligence]] with new insights
```

## Core Operations (How the Agent Works)

### 1. Ingest

When user adds a source:
- Capture raw source → save to `raw/{subdir}/`
- Discuss takeaways with user
- Check existing pages for mentioned entities/concepts
- Create/update wiki pages per Page Thresholds
- Add cross-references (2+ outbound links minimum)
- Update index.md and log.md

### 2. Query

When user asks a question:
- Read index.md to identify relevant pages
- Search files if >100 pages exist
- Read relevant pages with read_file
- Synthesize answer from compiled knowledge
- Cite wiki pages used in response
- File valuable answers back as query/comparison pages

### 3. Lint (Health-check)

Check:
- Orphan pages (no inbound wikilinks)
- Broken wikilinks (links to non-existent pages)
- Index completeness (all pages listed)
- Frontmatter validation (required fields present)
- Stale content (>90 days old since last source update)
- Contradictions between pages
- Confidence signals on single-source claims
- Tag taxonomy compliance

## Working With The Wiki

### Searching

```bash
# Find by content
search_files "autonomy" path="/Users/shayan/ShayanWiki" file_glob="*.md"

# Find by filename pattern
search_files "*.md" target="files" path="/Users/shayan/ShayanWiki"

# Recent activity
read_file "/Users/shayan/ShayanWiki/log.md" offset=<last 30 lines>
```

### Bulk Ingest

1. Read all sources first
2. Identify entities/concepts across all sources
3. Check existing pages once (not N times)
4. Create/update in one pass
5. Update index.md at end
6. Write single log entry covering batch

### Archiving

When content is superseded:
1. Create `_archive/` directory
2. Move page to `_archive/` with original path
3. Remove from index.md
4. Update wikilinks (replace with plain text + "(archived)")
5. Log the action

### Obsidian Integration

- Opens natively as Obsidian vault
- Wikilinks work out of box
- Graph View visualizes knowledge network
- YAML frontmatter powers Dataview queries

Install Dataview for queries like:
```dataview
TABLE updated FROM "entities" WHERE type == "entity" SORT created DESC
```

## Pitfalls (Never Do These)

- **Never modify files in `raw/`** — sources are immutable
- **Don't create pages for passing mentions** — follow Page Thresholds strictly
- **Don't create pages without cross-references** — isolated pages are invisible
- **Don't omit frontmatter** — it enables search/filtering/staleness detection
- **Don't use tags outside taxonomy** — add new ones to SCHEMA.md first
- **Ask before mass-updating** — if an ingest touches 10+ existing pages, confirm scope
- **Rotate the log** — when log.md exceeds 500 entries, rotate to `log-YYYY.md`
