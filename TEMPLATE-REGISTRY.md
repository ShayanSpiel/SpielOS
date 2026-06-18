# Template Registry — Progress & Architecture

Built 2026-06-16. Heuristic scoring engine that recommends viral content templates based on session archetype, meaning axis, funnel stage, and ICP layer.

## Location

`templates/registry/viral-templates.yaml` — structured YAML with 30 universal templates (10 per platform: X, LinkedIn, blog).

## Ranking

The `template_ranker.py` script scores each template on:
- **substance** — how much non-slot content in hook/CTA
- **archetype** — breadth of archetype coverage
- **psych_match** — alignment of psych_triggers with funnel_stages
- **anti_density** — how many anti_patterns declared
- **engagement** — historical engagement rate (when N>=5 posts)

## Registry Structure

```
templates/registry/
├── viral-templates.yaml         (canonical template set)
├── _archive/                    (snapshots from each rank run)
├── curated/                     (per-category slim files)
├── performance.json             (engagement data)
└── rank-history.jsonl           (per-run audit log)
```

## Usage

```bash
# Re-rank templates based on current performance data
spiel content rank-templates

# View current rankings
python3 scripts/template_ranker.py --show
```

## Templates by Platform

| Platform | Templates | Categories | Primary Funnel |
|----------|-----------|------------|----------------|
| X | 10 | listicle, contrarian, story, numbered_lessons, howto | TOFU/MOFU |
| LinkedIn | 10 | story_arc, listicle, contrarian, observation, framework | TOFU/BOFU |
| Blog | 10 | pillar_system, pillar_story, pillar_teardown, pillar_compare, pillar_frame | MOFU/BOFU |

Each template includes: `id`, `name`, `hook` (with `{slot}` variables), `cta`, `psych_triggers`, `anti_patterns`, and `best_for` archetype/axis/stage/layer metadata.
