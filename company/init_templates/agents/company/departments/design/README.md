# Design Department

Design owns visual production, not brand strategy. It consumes the canonical
company strategy and SpielOS design system, then produces graphics, banners,
article heroes, posters, and videos with render evidence. The department takes
video orders end-to-end (see "Video order flow" below).

For campaigns, Design accepts only the shared campaign Artifact from Content.
It records the `designed` handoff, validates the template, theme, semantic
tokens, title hierarchy, alignment, and platform preset, then returns one
`render_report` covering every item/platform pair. Templates expose
`__applyCampaignRendition`; renderers inject the rendition selected by
`CAMPAIGN_MANIFEST` and `CAMPAIGN_ITEM_ID`. Templates never fetch a named batch,
own campaign copy, or become a second strategy source.

Rendered evidence preserves `campaign_id`, `batch_id`, `item_id`, `content_id`,
and the derived creative signature. Local paths are not publishable media: the
approval handoff must also record a verified stable HTTPS asset URL.

The source of truth is `src/styles/tokens/`; `system/production.css` imports it
instead of copying a palette. Templates are format-agnostic and presets carry
channel dimensions. `threads-portrait` is 1080×1350 and `youtube-shorts` is
1080×1920; each ContentPackage must use the corresponding rendition rather than
resizing a generic template. Workflows: `social-visual`, `rendition-pack`,
`video-render`, `video-order`.

## Flat creative signature

The production reference is the existing Gruvbox-dark motion frame: flat grid,
centered Outfit typography, restrained Boxicons, and one wandering line behind
the message. The line is the branded signature across graphics and video: work
already completed is a solid primary stroke; the route ahead is muted and
dashed; the route ends at a simple flat bullseye. Keep it light and quiet.

Do not introduce 3D scenes, device mockups, glassmorphism, decorative card
systems, or spectacle-led gradients. Polish the existing composition through
alignment, spacing, readable hierarchy, the official logo, and a centered
`spielos.xyz` footer. Every design brief must also carry the One Idea Hierarchy
from `company/strategy/voice.md`: company-promise connection,
topic-specific idea, and one focused asset execution.

The shared flat motion/brand layer lives in
`templates/video/brand-motion.css` (journey line, bullseye goal, safe-area
brand footer); video templates link it and keep only per-scenario overrides.

## Template archetype registry

`templates/registry.json` is the machine-readable authority for every
registered creative archetype (schema v1.0). It lists each archetype's id,
kind (`shorts` | `social`), template file, legacy flag, description, and a
research_map pointing at the sourced findings behind it. The research that
drives the archetype choices is business evidence in
`.spielos/artifacts/content-growth-20260812/research/shortform-template-research-20260817.md`
(sources with URLs and dates; per-archetype performance remains an open
experiment — the funnel goal owns that question).

Registered archetypes (14):

| id | kind | file | legacy |
|---|---|---|---|
| `scenario-b` | shorts | `templates/video/scenario-b.html` | yes (never remove/rename) |
| `scenario-c` | shorts | `templates/video/scenario-c.html` | yes (never remove/rename) |
| `contrast-text` | shorts | `templates/video/contrast-text.html` | no |
| `storyboard` | shorts | `templates/video/storyboard.html` | no |
| `data-card` | shorts | `templates/video/data-card.html` | no |
| `question-hook` | shorts | `templates/video/question-hook.html` | no |
| `harness-architecture` | social | `templates/social/harness-architecture.html` | yes (never remove/rename) |
| `single-fact` | social | `templates/social/single-fact.html` | no |
| `list-checklist` | social | `templates/social/list-checklist.html` | no |
| `testimonial-pull-quote` | social | `templates/social/testimonial-pull-quote.html` | no |

Website OG images are derivatives, not new archetypes: `og-single-fact` and
`og-pull-quote` (in the website repo `src/og-templates/`) adapt `single-fact`
and `testimonial-pull-quote` to exact 1200x630 for per-route OG generation
(`node scripts/generate-og.mjs`). Change the social archetypes here first;
port visual changes to the OG derivatives in the same change
| `loop-rail` | shorts | `templates/video/loop-rail.html` | no |
| `heartbeat` | shorts | `templates/video/heartbeat.html` | no |
| `department-map` | social | `templates/social/department-map.html` | no |
| `agent-brief` | social | `templates/social/agent-brief.html` | no |

### Per-item selection rule (owner directive 2026-08-17)

Repetition caused the batch-02 quality rejection, so the design handoff
selects an archetype per item, never a batch-wide template:

1. **One archetype per item_id per platform.** Every item gets exactly one
   Shorts archetype and one Threads/social archetype.
2. **No batch repeats one template.** A template_id may appear only once per
   platform within a batch (batch size ≤ registry count; larger batches
   repeat by round-robin across ALL archetypes, never the same template
   twice in a row).
3. **Balance both experiment cells.** The handoff alternates/round-robins
   archetypes across item_ids and balances the archetype mix between the
   control and variant cells of the active experiment, so no cell is starved
   of a template family.
4. **Legacy templates stay registered and usable.** `scenario-b`,
   `scenario-c`, and `harness-architecture` are never removed or renamed
   (tests assert they exist) — they are simply members of the rotation now.
5. **Registration requires a real template.** A new archetype may only be
   added with an existing, parseable HTML template and a documented research
   mapping in the research brief.

**Mechanically enforced at the gate (design department 3.4.0, change
`change-e69f419da9`).** `validate_design_order` now rejects a violating
design order with a clear error — there is no silent fallback to legacy
templates. The gate reads `templates/registry.json` (read-only, this README's
authority) and checks per platform:

- the item's `template_id` is a **registered archetype of the platform's
  kind** (shorts for YouTube, social for Threads);
- **no batch repeats** when the batch fits the registry count (a unique
  template_id per item);
- **bounded round-robin balance** for larger batches: every archetype of the
  kind may appear at most one more time than any other, and the same
  template never repeats twice in a row;
- **bounded cell balance**: items are assigned to the declared experiment
  cells cycled in item order (alternating control/variant for two-cell
  campaigns), and every cell with two or more items must see at least two
  distinct archetypes per platform — a cell collapsed to a single archetype
  family is rejected.

The quality gate, ICP rules, and the registry's 14 selectable archetypes are
unchanged; legacy templates remain valid registry entries that follow the
same rotation rule.

### Creative-variety-v2 archetypes (design 3.4.0)

Four archetypes were added 2026-08-18 from the owner-confirmed
creative-variety-v2 gallery (goal-creative-variety-v2-20260818 and polish run
`run-86882a9306`; vision QA all PASS in
`.spielos/artifacts/template-preview-20260817/vision-verdicts-20260818.md`):

- `loop-rail` (shorts) — centered five-column OperatingLoop rail,
  GOAL → OBSERVE → DECIDE → ACT → EVALUATE nodes on a gradient progress
  line. Content-relevance: **process/loop content**.
- `heartbeat` (shorts) — live heartbeat card with a centered north star,
  a run row, and a 2×2 stat grid. Content-relevance: **live-ops content**.
- `department-map` (social) — DepartmentMap hub with a branch tile grid.
  Content-relevance: **system/harness content**.
- `agent-brief` (social) — seven-step Agent Brief pipeline with a flat
  deliverable/milestone showcase rail (no form UI). Content-relevance:
  **brief/request content**.

The content-relevance field in `registry.json` states the confirmed guidance
for which content each new archetype should carry; the design gate selects
archetypes per item within that guidance. Residual (documented, not a
registration blocker): `scene_timing.h` and `scene_timing.i` are not yet in
`narration.json` — the blocked TTS pipeline goal
(`goal-tts-voice-contract-20260812`) owns measuring them, so until it lands
those two templates degrade to placeholder timing exactly as previewed.

Video archetypes are flat motion compositions (virtual clock, measured
`scene_timing` key per archetype in `narration.json`, scene system, semantic
tokens, one-persona narration); social archetypes are flat canvases
(`__applyCampaignRendition`, journey signature, semantic tokens, boxicons
only). New files must pass the registry validation in
`company/tests/test_harness_structure.py` (exists, parseable HTML,
boxicons only with no `bx-*-circle` variants, semantic tokens only).

## Owner creative contract (2026-08-11 review + 2026-08-12 owner direction)

The review gates are encoded in `scripts/render-design.js --check` and
`scripts/render-video.js --check` and enforced by the pipeline scripts:

1. **ONE narration persona.** `voice_selection` in `templates/video/narration.json`
   pins the persona voice (Charon, a natural low-register male prebuilt voice).
   `scripts/tts-gemini.js` refuses per-call voice overrides, purges stale clips
   for the scenario before generating, and writes the voice into `scene_timing`
   and `public/videos/audio/.voice-manifest.json`; `scripts/mix-audio.js` refuses
   to mix mismatched provenance. Never mix clips from different generations.
2. **Multi-provider fallback chain (2026-08-12).** Narration is generated through
   a deterministic chain: Gemini 2.5 Flash TTS (primary) → Mistral Voxtral
   (fallback 1, both `MISTRAL_API_KEY` / `MISTRAL_API_KEY_2` with failover) →
   Cartesia (fallback 2) → ElevenLabs (fallback 3). On rate-limit/quota/auth/5xx
   failure the generator logs provider + status, purges the partial scenario,
   and the next provider retries the same clip — a clip is never dropped,
   the voice never changes mid-scenario, and stale clips are never reused.
   All five keys live in `.spielos/.env` (gitignored); `.env.example` carries
   names only. `scripts/tts-providers.js --check` verifies keys, chain order,
   and per-provider masculine voice pins (exit 0/1); `--list` shows
   providers/voices without secrets; `--probe` runs a live diagnostic clip per
   provider (never used for deliverables). Every provider pins a masculine
   low-register voice matching the persona.
3. **Full sentences.** Scene windows come from the MEASURED spoken clip
   durations (`scene_timing` in narration.json, written by tts-gemini.js).
   The video templates fetch narration.json at load and drive their scene
   switches from it — there is no hardcoded window to trim against. Clips get
   silent-edge trim only (never atempo, never mid-sentence cuts); if the
   measured schedule would overrun 14.9s the generator FAILS and the text is
   tightened instead.
4. **No music.** The mix is narration-only. `scripts/mix-audio.js` has no
   music bus, `narration.json` `mix.music` is `"none"`, and no music file is
   referenced anywhere in the pipeline or docs.
5. **Node pulses on the line, once.** Station nodes ride the journey path
   (`path.getPointAtLength` at each scene's measured start fraction — see
   `brand-motion.css`), and each fires a ONE-SHOT subtle ring flash when the
   line reaches it. No infinite ring animations on stations.
6. **Website typography.** Titles are Outfit 800, centered. `production.css`
   declares the website's font families with repo-root-resolvable
   `/public/assets/fonts/...` sources (the site's `src/assets/fonts/fonts.css`
   uses built-only `/assets/...` URLs, so the design system declares the same
   families itself). The gates verify in-render via
   `document.fonts.check("800 16px Outfit")` and computed styles — a
   system-font fallback fails the gate.
7. **Flat canvas social graphics.** `templates/social/harness-architecture.html`
   is a canvas composition: a connected journey line drawn THROUGH the
   department stations (vertices), a central loop symbol with the
   GOAL → OBSERVE → DECIDE → ACT → EVALUATE phases and the goal bullseye at
   its core, and a centered bold Outfit 800 title. No card-with-arrows
   website-screenshot layouts.

## Copywriting contract (per order)

Every video's narration follows the owner contract in `narration.json`
(`tone_contract`): ALWAYS a masculine voice; active, very confident, demanding,
aggressive but friendly, professional AND casual — NOT formal; short punchy
sentences with deliberate pauses; viral-style titles; each line connects to the
scenario's One Idea (strategy/voice.md — reference, never restate) without
mechanically repeating the company headline; the CTA lands the full
"spielos dot xyz slash services" read human-readable. Copy is written SHORT so
the measured schedule fits 14.9s at a slow, confident pace.

## Video order flow (department takes orders)

The `video-order` workflow accepts an order and runs it end-to-end:

1. **Intake** — accept the order (topic, channel aspect, run context).
2. **Idea lock** — One Idea Hierarchy from `company/strategy/voice.md`:
   company-promise connection + one topic-specific idea + one asset execution.
   The topic must be allowed by the canonical ICP/positioning
   (`company/strategy/icp.md`, `positioning.md` — reference, never restate).
3. **Scenario script** — narration lines per the copywriting contract
   (masculine persona, short lines, viral title, full CTA), stored in
   `templates/video/narration.json` (scenario lines + `scene_timing`).
4. **TTS via provider chain** — `node scripts/tts-gemini.js <b|c>` (chain in
   `scripts/tts-providers.js`): measured spoken durations, provider + voice
   provenance recorded, 14.9s overrun = tighten text.
5. **Narration-only mix** — `node scripts/mix-audio.js <b|c>` (-16 LUFS /
   -1 dBTP, 48kHz AAC, no music).
6. **Render** — `node scripts/render-video.js <b|c> <aspect> 30 <out>`;
   templates self-time from `scene_timing`; merge mix; posters + CTA frames.
7. **QA gates** — `render-design.js --check`, `render-video.js --check`,
   `tts-providers.js --check`, ffprobe stream/duration checks, frame
   inspection (pulses on line, Outfit 800, no empty renders).
8. **Deliverable** — complete set lands in
   `.spielos/artifacts/design-production-upgrade-20260810/` (video + audio +
   posters + CTA + graphics).

The `video-render` workflow (existing) remains the focused
render-and-verify step used when a script is already settled.

## Motion production (executed pipeline)

Video deliverables are produced end-to-end by scripts:

1. `scripts/tts-gemini.js <b|c>` — TTS through the provider chain with the
   pinned persona voice (stale clips purged first, silent-edge trim only),
   saving the MEASURED scene schedule into `templates/video/narration.json` →
   `scene_timing` (+ provider/voice provenance in `.voice-manifest.json`).
2. `scripts/mix-audio.js <b|c>` — narration-only mix from the measured
   schedule, loudnorm −16 LUFS / true peak −1 dBTP, 48kHz stereo AAC. No
   music bed; refuses mismatched voice provenance.
3. `scripts/render-video.js <b|c> <aspect> 30 <out>` — 30fps base render.
   The templates read `scene_timing` from narration.json themselves, so
   scene switches always follow the spoken durations.
4. Merge the mix into the base MP4 (copy video, AAC audio) + poster (0.6s)
   + CTA frame (0.45s after the last scene starts) + social graphics re-render.

Run everything per scenario with `bash scripts/render-all.sh <b|c> [30] [aspects]`.
The production set goes to `.spielos/artifacts/design-production-upgrade-20260810/`
(replacing any stale set); review samples go to
`.spielos/artifacts/design-restoration-polish-20260810/`.
