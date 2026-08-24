---
name: copywriting-en
description: Write clear, compact English content for the canonical SpielOS ICP from one customer-relevant idea.
---

# SpielOS English copywriting

Read `../../../company/strategy/icp.md` and `../../../company/strategy/voice.md`.

## Brief

Use only:

- reader
- customer moment
- one idea
- desired result
- intent (`value`, `proof`, or `conversion`)
- spielos relevance (one or two sentences: where the supervised-workflow role lands)
- optional proof

Internal work is evidence, not the topic. Do not write for developers, AI
builders, or people interested in our operating machinery.

## Write

1. Open with one sharp statement the reader understands immediately.
2. Explain it in one short paragraph or a short list.
3. Connect SpielOS only when the connection is natural.
4. Add a CTA only when the post earns one.
5. Remove everything that does not serve the one idea.

Use direct, conversational English. Prefer the buyer's words: staff time,
missed details, slow replies, repeated work, delivery speed, cost, capacity,
and errors. Explain `workflow` through the real work around it.

Avoid internal terms such as batch, campaign, hook, review gate, Department,
Artifact, runtime, harness rule, approval record, creative signature, or
content dispatch. Avoid generic SaaS claims and theatrical contrast formulas.

## Social shape

The useful default is:

- sharp opening
- one explanation
- optional bullets
- optional SpielOS bridge
- optional CTA

Do not force the same structure when fewer lines are stronger.

Threads:

- Use real paragraph breaks.
- Put each bullet on its own line.
- Put a link on its own line after the CTA.

YouTube Shorts:

- Keep the description concise.
- Write `Link in bio.` when a CTA is needed.
- Never include a UTM URL in the description.

Every fifth paired social idea uses the canonical SpielOS reminder from
`voice.md`. It is a short brand reminder, not an internal process report.

## Short-form narration (YouTube Shorts storytelling)

Short-form narration is ONE complete story, never a list of independent
slides:

1. Write the whole narration first — `narration.script` — covering the
   conversion arc in order: Hook → Pain/Context → Why it matters → AI/workflow
   mechanism → SpielOS role → Outcome → CTA. Each scene causes the next.
2. After the whole story passes `content-story-whole`, split it into the
   assigned template's scenes (registry.json `scene_control.scenes` keeps the
   per-archetype order) and lock each scene's delivery `intent`
   (`question/rising`, `statement/falling`, `command/falling`).
3. Keep ONE exact narrator persona for the whole campaign. Never write copy
   that requires a different voice or a silent fallback switch; every scene
   must sound like the same founder.

## Final check

- One reader, one moment, one idea.
- Cold-audience clarity: understandable to someone who has never heard of
  SpielOS.
- Concrete buyer language.
- Natural flow and spacing.
- No unsupported claim.
- No literal `\n` or `\r`.

Before a campaign can advance, the judge-enforced rubrics
(`company/departments/content/evals.py`) apply:

- `content-copy-top10` — the ten ICP-grounded criteria above — `one_reader`,
  `one_moment`, `one_idea`, `cold_audience_clarity`, `buyer_language`,
  `sharp_opening`, `honest_claims`, `platform_native`, `flow_brevity`,
  `fifth_item_reminder` — per item against the brief and both renditions.
- `content-story-whole` — the six whole-story criteria —
  `cold_audience_context`, `causal_flow`, `solution_clarity`,
  `spielos_relevance`, `earned_cta`, `founder_personality` — per item against
  the COMPLETE narration, BEFORE any template is assigned.

Run them with
`company eval run content-copy-top10 --payload <campaign>.json` and
`company eval run content-story-whole --payload <campaign>.json`; a failing
criterion must be fixed in the copy, never waived.

Return only the final copy unless notes are requested.
