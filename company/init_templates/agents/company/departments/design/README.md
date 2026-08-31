# Design Department

Design owns visual production. It consumes the Content campaign Artifact and
returns verified graphics, renditions, video, and render evidence. It does not
own ICP, positioning, copy, or a second campaign strategy.

## Campaign handoff

Content passes one strategy-complete Artifact. Design validates the handoff,
advances it to `designed`, selects registered archetypes, renders every
item/platform pair, and returns one `render_report`. The identity chain remains
`campaign_id → batch_id → item_id → content_id → creative_signature`; every
asset needs a local path, SHA-256, render-report ID, and stable HTTPS URL before
approval. `applyCampaignRendition`, `CAMPAIGN_MANIFEST`, and
`CAMPAIGN_ITEM_ID` keep templates data-driven.

Machine authority:

- `templates/registry.json` — registered archetypes and research mapping.
- `presets.json` — channel sizes (`threads-portrait`, `youtube-shorts`).
- `templates/video/narration.json` — pinned persona, scripts, measured timing,
  scene order, and audio mix.
- `system/production.css` plus `templates/video/brand-motion.css` — semantic
  tokens, flat motion, safe areas, and the journey-line signature.

These files are read-only for workflow compression; templates are never removed,
renamed, or rewritten.

## Creative contract

Use the existing flat Gruvbox-dark canvas: centered Outfit 800 typography,
restrained Boxicons, semantic tokens, official logo, centered `spielos.xyz`
footer, and one quiet journey line (solid completed route, dashed route ahead,
flat bullseye). Do not add 3D scenes, device mockups, glassmorphism, card
systems, spectacle gradients, or raw colors.

The registry rotation gate enforces, per platform: a registered archetype for
every item; no batch repeats one template when the batch fits the registry; balanced round-robin
counts and no adjacent repeat for larger batches, and at least two archetypes
per experiment cell when a cell has two or more items. Legacy IDs remain valid.
Content relevance guides template fit; Design makes the final selection.

## Video order

`video-order` accepts a topic/aspect/run context and runs:

`intake → idea_lock → scenario_script → tts_chain → narration_mix → render → qa → deliverable`

The One Idea comes from `strategy/voice.md` and must fit `icp.md` and
`positioning.md`. Write one complete narration before scenes; use the registry's
scene order and one pinned masculine founder persona. TTS uses the configured
provider fallback chain, records voice provenance, purges partial/stale clips,
and restarts the scenario on provider failure—never switch voice silently.

Scene timing comes from measured speech in `narration.json`; templates read that
schedule. Use full sentences, silent-edge trimming only, narration-only audio
(`mix.music: none`), 48 kHz AAC, −16 LUFS, and −1 dBTP. No music bus or hardcoded
scene window. Station nodes pulse once as the journey line reaches them.

Run the existing tools from the repository root:

```text
node scripts/tts-gemini.js <b|c>
node scripts/mix-audio.js <b|c>
node scripts/render-video.js <b|c> <aspect> 30 <out>
bash scripts/render-all.sh <b|c> [30] [aspects]
node scripts/render-design.js --check
node scripts/render-video.js --check
node scripts/tts-providers.js --check
```

Verify ffprobe streams/duration, measured timing, audio provenance, Outfit 800,
line pulses, no empty frames, plain hook thumbnail, and stable CTA frame. The
focused `video-render` workflow remains available when narration is already
settled. Deliverables stay under `.spielos/artifacts/`.
