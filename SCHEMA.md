# SCHEMA — Frontmatter Spec

## Page Frontmatter

```yaml
---
title: "Page Title"
created: 2026-01-01
updated: 2026-01-01
type: concept            # concept | entity | summary | source
tags:
  - tag1
  - tag2
sources:
  - "raw/source-file.md"
---
```

## Post Frontmatter

```yaml
---
title: "Post Title"
date: 2026-01-01
platform: linkedin       # linkedin | x | blog
archetype: F             # A-F for LinkedIn, 1-8 for X
status: draft            # draft | ready-to-publish | posted | rejected
icp: "target audience"
pattern: "viral pattern"
engagement_ask: "question"
standalone_test: pending  # pending | passed | failed
copywriting_gate: pending # pending | passed | failed
composite_score: null    # 0.0-1.0
posted_at: null
---
```

## Tag Taxonomy

- `identity` — personal brand, positioning, values
- `strategy` — frameworks, methods, playbooks
- `psychology` — human behavior, cognitive bias, motivation
- `systems` — workflows, automation, state machines
- `execution` — shipping, craft, quality
- `business` — offers, pricing, audience
- `tech` — AI, LLM, tooling
- `philosophy` — principles, mental models
- `narrative` — storytelling, voice, copywriting
- `leadership` — management, team, decisions
