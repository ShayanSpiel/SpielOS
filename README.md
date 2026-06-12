# Spiel Engine

An agentic content engine that turns work sessions into platform-native posts.
Portable — runs from anywhere via `VAULT_DIR` or auto-detects its root.

## Quick Start (5 min)

### 1. Edit your rules
**`rules.yaml`** — All mechanical gates, character limits, banned openers, safe openers, audience triggers, lesson triggers, strategy classifier keywords, and posting behavior.

### 2. Edit your voice
- **`concepts/voice-and-gates.md`** — Voice markers + 4-check + 10-gate + 8-step Compiler
- **`concepts/voice-corpus.md`** — Fill in your best posts as canonical examples
- **`concepts/icp-offer.md`** — Who you're writing for, what you're selling
- **`concepts/funnel-and-matrix.md`** — Funnel stages, archetypes, CTA matrix

### 3. Edit your templates
- **`templates/x-post.md`** — X/Twitter post structure
- **`templates/linkedin-post.md`** — LinkedIn post structure
- **`templates/blog-post.md`** — Blog pillar structure
- **`templates/session-log.md`** — Session log format

### 4. Run the pipeline
```bash
./scripts/engine.py status        # See current state
./scripts/post.sh                  # Start a post from your latest session
./scripts/gates.py --all           # Check all queue drafts against your rules
./scripts/pipeline.sh wiki-health  # Run wiki health check
```

## Architecture

```
rules.yaml          ← THE config. Mechanical rules, keywords, limits, toggles.
concepts/*.md       ← LLM guidance. Voice markers, ICP, funnel, corpus.
templates/*.md      ← Post structural templates.
scripts/            ← Framework code. No hardcoded config values.
```

## Portability

Set `VAULT_DIR` to run from any directory. All scripts use it with a dynamic fallback to the vault root.

## What to configure

1. `rules.yaml` — your keywords, limits, openers, posting mode
2. `concepts/icp-offer.md` — your ICP and offer
3. `concepts/funnel-and-matrix.md` — your verticals and funnel
4. `concepts/voice-and-gates.md` — your voice markers
5. `templates/*.md` — your post structures
6. `assets/brand-config.json` — your brand identity
