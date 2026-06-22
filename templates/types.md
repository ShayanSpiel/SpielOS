---
title: Content Types
type: spec
tags: [content-strategy, types, reference]
created: 2026-06-21
updated: 2026-06-21
sources: [strategy/voice.md, strategy/funnel.md, templates/registry/viral-templates.yaml]
confidence: high
status: living — engine-canonical
---

# Content Types

A *content type* is a structural pattern for a post. Different platforms favor different types. The type is chosen by the *decision tree* below — run when `/post` reads a session log.

**This is the structural-shape layer.** Voice (tone, register, style markers) lives in `strategy/voice.md`. Quality gates live in `system/gates.md`. The mechanical templates (with hooks, CTAs, body patterns) live in `templates/registry/viral-templates.yaml`.

---

## Cross-Platform Types (3)

- **Story:** A specific moment with dialogue, stakes, and a lesson. Lesson is the last line, not the first.
- **Take:** A contrarian opinion, argued. Reader should feel friction before they agree.
- **Question:** A genuine question framed with enough context to be answerable. Goal is comments, not impressions.

## X-Only Types (14)

| Type | Structure | When |
|------|-----------|------|
| Ship | Verb + what shipped | Feature launch |
| Stack-brag | Tools + price (sparingly) | Capability flex |
| Dev-log | Fact from the build | Concrete insight |
| Decision | Chose X over Y + tradeoff | Trade-off reveal |
| Lesson | Thing learned, abstracted | Teaching |
| Vision | Future-tense direction | Direction setting |
| Numbers | Specific anchored number | Hard data |
| Hook | Single line opening a thread | Thread starter |
| **Ship-log** | Day N + what shipped | BiP build log, daily/weekly |
| **Product** | "We just shipped X" + why it took N months | Launch / changelog |
| **Milestone** | Specific number + what it means | 1k users, $X MRR, N customers |
| **Feature** | "Added Y" + the one metric that moved | Small change with big impact |
| **Behind** | "What's in my stack" | Tool/process reveal |
| **Case-study** | "Client X went from Y to Z" | Before/after proof |

## LinkedIn-Only Types (6 active)

| Type | Length | When |
|------|--------|------|
| Story | 1300-2500 chars | Confessional opener, specific moment, lesson |
| Perception-shift | 1300-2500 chars | Break an old belief, install new one |
| Single-metaphor | 1500-2500 chars | One load-bearing image carries the post |
| Opening-statement / system | 1500-3000 chars | Show the car (problem + whole system) before the motor |
| Casual-update / day-in-the-life | 600-1200 chars | What + why, soft engagement |
| **Case-study** | 1500-3000 chars | Client result with permission, before/after |

**LinkedIn format priority:**
1. Story — confessional opener, specific moment, lesson
2. Perception-shift — break an old belief, install new one
3. Single-metaphor — one load-bearing image
4. Case-study — client result with permission
5. Opening-statement — framework explained end-to-end
6. Casual update — default fallback

## Blog-Only Types (5)

| Type | Word Count | When |
|------|-----------|------|
| Pillar (system) | 1500-2500 | System explained end-to-end |
| Pillar (story) | 1500-2500 | Turning point, correction, meaningful failure |
| Pillar (teardown) | 1500-2500 | Real artifact analyzed |
| **Product launch** | 1500-2500 | Changelog as content, v2 / beta |
| **Behind-the-build** | 1500-2500 | Stack, system, process deep-dive |

---

## The Type Decision Tree

When `/post` is invoked, the tree runs in this order:

1. **System, turning point, story, correction, or teaching?** → pillar blog + 3 LinkedIn + 5-10 X
2. **Specific moment worth telling as story?** → story-mode LI + story X thread/single
3. **Contrarian or non-obvious take?** → argument-mode LI + take X post
4. **Genuine question for audience?** → ask-mode LI + question X post
5. **Something shipped?** → ship X post + (optional) dev-log X post
6. **Specific lesson?** → lesson X post
7. **Number worth highlighting?** → numbers X post
8. **None of the above?** → hook X post or skip

The tree always ends with at least one X post (or a skip). Pillar/LinkedIn only fire when the work earns them.

> **Execution order:** This tree runs AFTER Q1-Q4 in `strategy/funnel.md §The 4 Strategic Questions`. The routing result from `strategy/funnel.md` is an input to the tree.

---

## Templates vs Types

| Concept | What it is | Where it lives |
|---|---|---|
| **Type** | The structural shape (story, take, listicle) | This file (`templates/types.md`) |
| **Template** | A specific hook + body + CTA pattern | `templates/registry/viral-templates.yaml` |
| **Voice marker** | Tone, register, punctuation style | `strategy/voice.md` |

The type is chosen by the decision tree above. The template is recommended by `engine/selector_keyword.py` (top 5 X, 3 LinkedIn, 2 blog). The voice is applied by the LLM from `strategy/voice.md` + `strategy/corpus.md` examples.

---

## See Also

- `strategy/voice.md` — voice markers (how the post reads)
- `strategy/corpus.md` — 8 canonical voice examples
- `strategy/funnel.md` — funnel routing (which stage, which CTA)
- `strategy/archetypes.md` — session archetype classification
- `templates/registry/viral-templates.yaml` — structural templates with hooks + CTAs
- `templates/x-post.md`, `templates/linkedin-post.md`, `templates/blog-post.md` — output shapes
