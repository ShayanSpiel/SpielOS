# Design Department

Design owns visual planning and media production. It consumes an evaluated
Content Artifact; it does not rewrite the brief, copy, or strategy.

## Flow

`content_ready → template plan → scene plan → TTS/render → render_report`

- `templates/registry.json` is the template authority.
- `templates/video/narration.json` is the voice, timing, and audio authority.
- `tools/` enforce generation and objective media checks.
- A `render_report` is Design evidence and must match the campaign and batch.

Use one registered template per item/platform. Do not repeat a template within
a batch when enough registered templates exist. The selected template supports
the story; it never changes the story's message.

## Media rules

Use one narrator per video generation, measured speech timing, and a
narration-only mix. Keep the final Short below the configured limit. The
renderer validates provenance, timing, streams, text visibility, and the
thumbnail before it emits a report.

Campaign deliverables live beside their campaign Artifact under
`.spielos/artifacts/`.
