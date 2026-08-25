# Content Department

Content owns the customer message. It does not choose visual templates, render
media, or publish.

## Flow

`brief → copy and whole narration → editorial evaluation → Design handoff`

1. Read the canonical buyer, positioning, and voice sources in
   `company/strategy/`.
2. Write one brief and platform-native copy per item. A Short starts as one
   complete `narration.script`; scene splitting happens only after review.
3. Record passing `content-copy-top10` and `content-story-whole` reports.
4. Emit `content_ready`. Design consumes that evidence, chooses a template,
   creates the scene plan, and returns its own `render_report`.

## Brief

Each item has `reader`, `customer_moment`, `one_idea`, `desired_result`,
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
