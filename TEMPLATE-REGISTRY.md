# Template Registry — Progress & Architecture

Built 2026-06-16. Heuristic scoring engine that recommends viral content templates based on session archetype, meaning axis, funnel stage, and ICP layer.

---

## Architecture Overview

```
templates/registry/viral-templates.yaml    ← structured YAML (platform → categories → templates)
scripts/template_selector.py               ← heuristic scoring engine (Python, no LLM call)
rules.yaml §template_selector              ← weights, top_n, toggle
engine.py cmd_content_select_template      ← pipeline command
pipeline.sh post-select-template           ← CLI entry point
```

### Data Flow

```
post-compile (fills brief with core_insight + meanings + selected_meaning)
     ↓
post-select-template
     ├── reads .content-brief.json (selected_meaning.axis, core_insight)
     ├── runs strategy_classifier.py on session/topic text → archetype, funnel_stage, icp_layer
     ├── loads templates/registry/viral-templates.yaml → 50 templates
     ├── scores each: Σ(weights × match) per template
     └── outputs ranked JSON recommendations
     ↓
LLM shows user recommendations → user picks → LLM writes IDs to .content-brief.json
     ↓
post-draft (drafts using selected template's hook/body/CTA formulas)
```

### Scoring Formula

```
score(t) = w_arch  × arch_match(t)   (0.30)
         + w_axis  × axis_match(t)   (0.25)
         + w_funnel × funnel_match(t) (0.20)
         + w_layer × layer_match(t)  (0.15)
         = 0.90 max
         (0.10 reserved for future psych_trigger NLP scoring against core_insight)
```

Weights in `rules.yaml §template_selector.weights`. Edit to tune.

---

## What's Done (Phase 1)

| Component | Status | Details |
|-----------|--------|---------|
| `templates/registry/viral-templates.yaml` | ✅ Delivered | 50 X templates in 5 categories (listicle, contrarian, story, data, interactive) |
| `scripts/template_selector.py` | ✅ Delivered | Loads YAML, runs classifier, scores templates, outputs JSON |
| `rules.yaml §template_selector` | ✅ Delivered | Weights, top_n per platform, enabled toggle |
| `engine.py` — `cmd_content_select_template` | ✅ Delivered | Non-state-changing utility command |
| `pipeline.sh — post-select-template` | ✅ Delivered | CLI wrapper |
| `.content-brief.json` — `template_selection` field | ✅ Delivered | Schema extended |
| `commands/post.md` — selection step | ✅ Delivered | Replaces old "which format" interaction |
| `SKILL.md` — template selection guidance | ✅ Delivered | In spiel-content skill |

---

## What's Next (Future Phases)

### Phase 2: LinkedIn + Blog Templates (remaining 100)

**File:** `templates/registry/viral-templates.yaml`

Add two new platform sections with categories:

**LinkedIn** (5 categories × 10 = 50 templates):
- `authority` — Case studies & results (STAR/PAS frameworks)
- `vulnerability` — Lessons learned
- `de-risking` — Cautionary & preventive
- `paradigm` — Professional theories
- `scale` — Metrics & tenure

**Blog** (5 categories × 10 = 50 templates):
- `howto` — Step-by-step guides
- `numbered` — Structural categorization
- `question` — Direct answer
- `curiosity` — The "one thing"
- `contrarian` — Myth busting

Each entry needs `best_for` mappings (archetypes, meaning_axes, funnel_stages, icp_layers) and psych_triggers. Follow the existing X template pattern.

### Phase 3: Slot-Filling Engine (Optional)

Currently, slot variables like `{persona}`, `{result}`, `{timeframe}` in hook/body/CTA formulas are filled by the LLM during drafting. An automated slot-filler could:

1. Parse `{slot_name}` patterns from selected template
2. Extract slot values from `.content-brief.json` core_insight + meanings
3. Pre-fill slots before the LLM drafts (reduces token usage, improves consistency)

This requires defining a `slot_map` in each template entry or a shared slot extraction function.

### Phase 4: Psych Trigger NLP Scoring

The reserved 0.10 weight for `psych_trigger` scoring. Match psych_triggers of each template against core_insight + meanings using keyword overlap or embeddings. Add to `template_selector.py`:

```python
# Match psych_triggers against core_insight text
for trigger in tmpl["psych_triggers"]:
    if trigger_keywords[trigger].intersection(core_insight_words):
        score += weights.get("psych_trigger", 0.10) / len(tmpl["psych_triggers"])
```

### Phase 5: Engagement Data Feedback Loop

After posts are published and engagement data collected (`engagement:` frontmatter), feed back into template scoring:

- Track which templates over/under-perform by platform
- Decay scores for underperforming templates
- Boost scores for proven patterns
- Store performance data in a `templates/registry/performance.json` or in `rules.yaml`

---

## Design Decisions

### Why YAML, not JSON or Markdown?
- YAML is the most token-efficient structured format for LLM context
- Supports comments, anchors, and inheritance (category → template defaults)
- Already used by `rules.yaml` — consistent toolchain
- ~2× denser than equivalent JSON; ~5× denser than equivalent markdown

### Why no new state machine state?
Selector is a read-only utility (like BANNER), not a stateful pipeline stage. It reads the brief and outputs recommendations. The state machine stays at 12 content states. If you want a formal stop-gate, add `TEMPLATE_SELECT` between `ICP_WORLD_BUILD` and `DRAFTING` in `state_machine.py`.

### Why run strategy_classifier again instead of caching results?
The classifier is cheap (keyword matching, <100ms). Running it fresh eliminates stale data and avoids storing classifier output in `.content-brief.json`. If latency becomes an issue, cache results in the brief.

### Why `0.90` max score instead of `1.00`?
The remaining 0.10 is reserved for psych_trigger NLP scoring against core_insight (Phase 4). Adding it later won't change existing scores (just adds a bonus term). If you never add it, normalize scores to 1.0 by dividing by 0.90.

### Template ID naming convention
```
{platform}-{category}-{NN}
```
Examples: `x-listicle-01`, `x-contrarian-03`, `li-authority-07`, `blog-howto-05`

---

## Editing the Registry

**Adding a new template:** Add a new entry under the appropriate category's `templates:` list. If it differs from category defaults, add override fields (e.g., `best_for:`, `psych_triggers:`).

**Adding a new category:** Add a new entry under `categories:` with `defaults` and `templates`.

**Adding a new platform:** Add a new platform block at the top level (e.g., `platform: linkedin` → but the file currently has `platform: x` as a flat key). Future platforms should use a nested structure. When Phase 2 is ready, restructure the file header to:

```yaml
version: 1
platforms:
  x:
    categories:
      - id: listicle
        ...
  linkedin:
    categories:
      - id: authority
        ...
  blog:
    categories:
      - id: howto
        ...
```

And update `template_selector.py` `flatten_templates()` to iterate `registry['platforms']` instead of reading `registry['platform']`.

---

## Key Files

| Path | Purpose |
|------|---------|
| `templates/registry/viral-templates.yaml` | All template data |
| `scripts/template_selector.py` | Selection engine |
| `rules.yaml` §`template_selector` | Config |
| `scripts/engine.py` — `cmd_content_select_template` | Pipeline command |
| `scripts/pipeline.sh` — `post-select-template` | CLI wrapper (back-compat) |
| `scripts/bin/spiel` — `spiel content select` | Path-independent CLI wrapper (preferred) |
| `.content-brief.json` — `template_selection` | Brief schema |
| `commands/post.md` | Pipeline protocol |
| `.config/opencode/skill/spiel-content/SKILL.md` | Skill definition |

---

## Commands

```bash
# Run template selector (after post-compile, before post-draft)
spiel content select                 # preferred: works from any cwd
bash scripts/pipeline.sh post-select-template   # back-compat: needs cwd = vault

# Filter to specific platform
python3 scripts/template_selector.py --platform x --top-n 5

# Direct Python import
python3 -c "
import json, sys; sys.path.insert(0, 'scripts')
from template_selector import load_registry, flatten_templates, score_template
reg = load_registry()
tmpls = flatten_templates(reg)
print(f'{len(tmpls)} templates loaded')
"
```

---

## Tests

```bash
# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('templates/registry/viral-templates.yaml'))"

# Count templates
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from template_selector import load_registry, flatten_templates
print(len(flatten_templates(load_registry())))
"

# Test scoring
python3 scripts/template_selector.py --platform x --top-n 5
```
