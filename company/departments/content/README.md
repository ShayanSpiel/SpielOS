# Content Department

Content owns the customer message. It does not choose visual templates, render
media, or publish.

## Flow

`Strategy intake → worldview → Content Brief → copywriter → editorial gate → Design handoff`

1. Validate the requested ICP, reader, intent, topic, platforms, and formats
   against the selected canonical strategy context. Missing or placeholder
   strategy blocks production.
2. The Strategist writes the worldview and locks one Content Brief. The
   Copywriter then writes platform-native copy per item. A Short starts as one
   complete `narration.script`; scene splitting happens only after review.
3. The editorial gate verifies every copy artifact carries the requested ICP
   and reader, and emits the final text artifact plus `content_ready`.
4. Design consumes that evidence, chooses a template,
   creates the scene plan, and returns its own `render_report`.

## Brief

Each request has `icp`, `reader`, `intent`, `topic`, `platforms`, and `formats`.
Each item brief has `reader`, `customer_moment`, `one_idea`, `desired_result`,
`intent`, `spielos_relevance`, and optional `proof`. Renditions may adapt the
expression, never the idea.

## Authorities

- `company/strategy/` owns audience, positioning, and voice.
- `skills/copywriting-en/SKILL.md` owns writer guidance.
- `evals.py` owns editorial acceptance criteria.
- `campaign_contract.py` owns the Artifact shape and platform safety checks.
- Design owns template selection, scene visuals, voice configuration, and
  media validation.

The campaign Artifact moves through
`strategy → designed → rendered → approved → delivered → measured → evaluated`.
Generated Artifacts live under `.spielos/artifacts/`.
