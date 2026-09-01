---
name: video-creation
description: Produce and verify SpielOS narration-led videos from the Design registry and measured audio schedule.
---

# Video creation

This skill executes Design's bounded production contract. It does not invent
strategy, copy, templates, or a second workflow. Read the campaign Artifact,
`.agents/company/departments/design/README.md`, `templates/registry.json`,
`templates/video/narration.json`, `presets.json`, `system/production.css`, and
the shared `brand-motion.css` before rendering.

## Inputs and selection

Require a strategy-complete campaign with `campaign_id`, `batch_id`, `item_id`,
`content_id`, one idea, complete `narration.script`, ordered scenes, design
identity, CTA, and the correct platform preset. Select one registered
archetype per item/platform. No batch repeats one template when the registry
can cover the batch; larger batches use balanced
round-robin counts, no adjacent repeat, and balanced control/variant cells.
Never silently fall back or rename legacy templates.

The script is written as one story before scene splitting:

`Hook → Pain/Context → Why it matters → AI/workflow mechanism → SpielOS role → Outcome → CTA`

Keep the registry scene order and one delivery intent per scene. The hook is a
plain frame thumbnail; no glass-card or still-title overlay.

## Creative and voice contract

Use the flat Gruvbox-dark motion language: centered Outfit 800, semantic tokens,
restrained Boxicons, official logo, centered `spielos.xyz` footer, and one quiet
journey line with solid completed route, dashed route ahead, and bullseye goal.
No 3D, mockups, glassmorphism, decorative card systems, spectacle gradients, or
raw colors. Nodes pulse once as the line reaches them.

Use the persona and tone pinned in `narration.json`: one confident masculine
founder voice, active and casual, short punchy sentences, deliberate pauses,
and a human-readable `spielos dot xyz slash services` CTA. Never switch voice
mid-scenario or mix generations.

## Production order

1. Gate keys, provider order, voice pins, registry, presets, and tool versions.
2. Generate narration and measured timing; purge stale/partial scenario clips.
3. Retry the same scenario through the configured provider chain on quota,
   auth, rate-limit, or server failure; record provider and voice provenance.
4. Trim silent edges only. Full sentences stay intact; never use atempo or
   mid-sentence cuts. If the measured schedule exceeds the configured template
   duration, tighten copy and regenerate.
5. Mix narration only (`mix.music: none`) at 48 kHz AAC, −16 LUFS, −1 dBTP;
   refuse mismatched provenance.
6. Render the base video; templates read `scene_timing` from `narration.json`.
7. Merge the verified mix, generate the plain hook poster and CTA frame, and
   return video, audio, poster, CTA, and evidence under the campaign Artifact.

Commands (run from the repository root):

```text
node scripts/tts-providers.js --check
node scripts/tts-gemini.js <b|c>
node scripts/mix-audio.js <b|c>
node scripts/render-video.js <b|c> <aspect> 30 <out>
bash scripts/render-all.sh <b|c> [30] [aspects]
node scripts/render-design.js --check
node scripts/render-video.js --check
```

The configured fallback chain is authoritative; provider-specific voice pins,
keys, and probes stay in the scripts and `.spielos/.env`. Deprecated local
fallbacks are diagnostic only and never production deliverables.

## Verification

Check registry membership, batch rotation, semantic tokens, Outfit 800, scene
order, measured timing, ffprobe streams/duration, audio provenance, narration
presence, line pulses, no empty frames, plain thumbnail, stable HTTPS asset URL,
and the typed `render_report` identity. A failure blocks the handoff; do not
waive it. Deliverables belong in `.spielos/artifacts/`, never in strategy,
assets, skills, templates, or public source.
