# Content Department

Content carries one customer-relevant idea from strategy to publication in one
versioned campaign Artifact. The Artifact remains cohesive; the writer sees
only the short creative brief, while production metadata is added afterward.

## Creative brief

Each piece locks seven short fields:

- `reader`
- `customer_moment`
- `one_idea`
- `desired_result`
- `intent` — the buyer intent this piece serves: `value`, `proof`, or
  `conversion` (schema 1.2)
- `spielos_relevance` — in one or two sentences, why this idea matters to
  SpielOS and where the supervised-workflow role lands (schema 1.2)
- optional `proof`

The piece is written from this brief. Platform renditions may add or subtract a
line, but cannot change the idea. SpielOS and the CTA are optional unless the
piece is the fifth-item reminder.

Every fifth paired idea is `spielos-reminder` and uses the company reminder in
`strategy/voice.md`. It may cite one public proof point. It must not become an
internal run log.

## Storytelling architecture (YouTube Shorts)

Short-form narration is ONE complete story, never a list of independent slides:

1. Write the whole narration first (`narration.script`) covering the conversion
   arc in order: Hook → Pain/Context → Why it matters → AI/workflow mechanism →
   SpielOS role → Outcome → CTA.
2. Only after the whole story passes `content-story-whole` does the strategist
   assign a template and split the script into that template's scenes.
3. Every scene carries the archetype's scene id (registry.json
   `scene_control.scenes` — e.g. scenario-b uses
   `hook/pain/promise/pillars/director/cta`) and a delivery `intent`
   (`question/rising`, `statement/falling`, `command/falling`) so the narrator
   never improvises a tone.
4. ONE exact narrator voice for the whole campaign: `voice_selection` is pinned
   per generation (`tts-gemini.js`), fallback providers restart the whole
   scenario, and the renderer refuses to mix clips that do not match the pinned
   persona. There are no silent fallback voice switches.
5. Thumbnails are PLAIN FRAME grabs of the hook window — no glass-card overlay,
   no still-title overlay API.

## Platform-native copy

- Threads uses real paragraphs and bullets. A caption link appears on its own
  line after the CTA.
- YouTube Shorts never contains a UTM URL. When relevant, it says `Link in bio.`
- Literal `\n` and `\r` markers are rejected before approval and dispatch.
- A product bridge or CTA is not required on every post.

## LLM-as-judge quality gate

Mechanical validation never reads copy for clarity, so campaign copy is judged
against grounded quality standards before it can advance:

- `departments/content/evals.py` defines `content-copy-top10` (suite id
  `content-copy-top10`): ten criteria — `one_reader`, `one_moment`,
  `one_idea`, `cold_audience_clarity`, `buyer_language`,
  `sharp_opening`, `honest_claims`, `platform_native`, `flow_brevity`,
  `fifth_item_reminder` — each grounded in a canonical strategy/skill source.
  Every criterion must pass (`all_pass`, `min_score` 1.0) per item AND per
  batch, judged PER ITEM against the item brief and both platform renditions.
- `content-story-whole` (suite id `content-story-whole`): six whole-story
  criteria — `cold_audience_context`, `causal_flow`, `solution_clarity`,
  `spielos_relevance`, `earned_cta`, `founder_personality` — judged PER ITEM
  against the item's COMPLETE YouTube narration (script + ordered scenes), not
  against isolated clips. The quality gate requires a passing eval_report for
  BOTH suites; a failing story criterion blocks the batch before any template
  reaches rendering.
- The `quality_gate` machine step requires an `eval_report` evidence record
  (`kind` eval_report, `payload_id` equal to the batch_id, `overall` pass) for
  every declared suite before it can produce `campaign_ready`; otherwise it
  blocks with attention errors naming the failed criteria.
- The same gate enforces the Design registry rotation rule (registry.json): a
  batch of five items must use five distinct registered Shorts archetypes — the
  content flow no longer bypasses Design's rotation gate (`_rotation_errors`).
- Evidence validity for both suites is `business`: they gate buyer-facing copy
  and narration against the company's ICP/voice standards before publication.

### Adding an eval suite to ANY department (Lego contract)

1. Create `departments/<name>/evals.py` exporting `EVAL_SUITES` — each suite
   declares ordered `EvalCriterion`s with source-file grounding
   (strategy/skill paths), a `payload_kind`, `thresholds`, an optional
   `item_selector`, and an optional `payload_id_selector`.
2. Declare `eval_suites = ("<suite-id>", ...)` on the Department class.
3. Require a passing `eval_report` evidence in the machine step that gates the
   payload (see `company/evals/` and `company eval list`).

The evals framework itself (`company/evals/`) is department-agnostic:
one engine, pluggable judge connectors (`agent:cli` default, `http:provider`
seam), registry auto-discovery from `evals.py` modules, and a `company eval`
CLI (`list`, `run`).

## Production handoff

After copy is complete, the same Artifact receives design, rendering,
approval, Buffer, and analytics fields. These fields preserve the identity
chain `campaign_id → batch_id → item_id → content_id → creative_signature`, but
they are not writing instructions.

The daily target remains 50 Threads posts and 50 YouTube Shorts in batches of
five paired ideas. Each batch has one approval. Experiments and attribution
remain delivery and measurement metadata; they never expand the creative
prompt.

Campaign phases remain:

`strategy → designed → rendered → approved → delivered → measured → evaluated`

Generated Artifacts belong under `.spielos/artifacts/`.
