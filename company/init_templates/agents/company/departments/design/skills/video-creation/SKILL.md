---
name: video-creation
description: Create promo videos from HTML templates using Puppeteer frame capture, FFmpeg encoding, and multi-provider TTS narration (Gemini 2.5 Flash primary, with Mistral Voxtral, Cartesia, and ElevenLabs fallbacks). Use for any video creation task: product videos, social media clips, launch videos, before/after comparisons, explainer videos, or animated demos. Covers scene composition, CSS animation system, virtual clock, multi-aspect-ratio rendering, one-persona TTS narration, narration-only mixing, and batch generation.
---

# Video Creation

## Mission

Create flat, production-ready motion pieces from the existing SpielOS templates, encode them with FFmpeg, and deliver them with approved, narration-only audio. Preserve the established composition and branded goal line; the rendering method must never make the result feel like an HTML page recorded as video.

## Scope

Owns: Video creation, HTML-to-video rendering, scene composition, CSS animation system, virtual clock, multi-aspect-ratio rendering, batch generation, one-persona TTS narration through a multi-provider fallback chain, narration-only mixing, poster generation.

Does NOT own:
- Design tokens → see `../spielos-ui/SKILL.md`
- Analytics tracking → see `../analytics/SKILL.md`
- Content writing → see `../copywriting-en/SKILL.md`

## Reference files

Before creating videos, read:

- `company/departments/design/templates/registry.json` — the template archetype registry (ids, kinds, files, legacy flags, research maps)
- `company/departments/design/templates/video/scenario-b.html` — Before/After template
- `company/departments/design/templates/video/scenario-c.html` — Build It template
- `company/departments/design/templates/video/contrast-text.html` — Contrast statement archetype
- `company/departments/design/templates/video/storyboard.html` — Three-frame storyboard archetype
- `company/departments/design/templates/video/data-card.html` — Hero statistic archetype
- `company/departments/design/templates/video/question-hook.html` — Open-loop question archetype
- `company/departments/design/templates/video/brand-motion.css` — shared flat journey-line, bullseye goal, and brand-footer motion layer
- `company/departments/design/templates/video/narration.json` — persona pin, tone contract, script, provider chain, measured scene_timing, and narration-only mix brief
- `company/strategy/voice.md` — canonical One Idea Hierarchy
- `company/strategy/icp.md` and `positioning.md` — canonical buyer/positioning (reference, never restate)
- `scripts/tts-providers.js` — provider chain (Gemini → Mistral → Cartesia → ElevenLabs), voice pins, `--check`/`--list`/`--probe`
- `scripts/render-video.js` — Puppeteer + FFmpeg renderer (and the owner-contract `--check` gate)
- `company/departments/design/system/production.css` — tokens + website fonts resolved for the render context

## Template selection (per-item, no batch repeats)

Every registered Shorts archetype is a flat motion template with its own
measured `scene_timing` key in `narration.json` (`b`, `c`, `d`, `e`, `f`,
`g` for `scenario-b`, `scenario-c`, `contrast-text`, `storyboard`,
`data-card`, `question-hook`). The renderer's scenario keys (`b`/`c`) are
unchanged; a new archetype renders once its key is produced by the
measurement path.

Selection rule (owner directive 2026-08-17, full detail in
`company/departments/design/README.md`):

1. **One archetype per item_id.** The design handoff picks an archetype per
   item, never a batch-wide template.
2. **No batch repeats one template.** Within one batch, a template_id is used
   at most once per platform; larger batches round-robin across all
   archetypes.
3. **Balance both experiment cells.** Alternate/round-robin archetypes across
   item_ids so the control and variant cells get a comparable mix of
   template families.
4. **Legacy templates stay.** `scenario-b` and `scenario-c` remain registered
   and usable; they are members of the rotation, never removed or renamed.
5. **Narration stays one persona.** Whichever archetype is selected, the
   narration contract is unchanged: one pinned masculine persona through the
   provider chain, measured scene timing, narration-only mix.

The archetype choice is a design-system decision (semantic tokens, flat
composition, boxicons only); it never changes the creative contract above.

---

## Prerequisites

| Tool | Install | Purpose |
|---|---|---|
| Node.js 18+ | `brew install node` | Runtime |
| Puppeteer | `npm install puppeteer` | Headless Chrome for frame capture |
| FFmpeg | `brew install ffmpeg` | Frame-to-MP4 encoding, audio mixing |
| ffprobe | via FFmpeg | Measuring spoken clip durations |
| TTS keys | `.spielos/.env` (gitignored) | Five owner keys: `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `MISTRAL_API_KEY_2`, `CARTESIA_API_KEY`, `ELEVENLABS_API_KEY` |

### Check prerequisites

```bash
node --version    # Should be 18+
ffmpeg -version   # Should be 5+
node scripts/tts-providers.js --check  # exit 0: keys + chain order + voice pins
```

---

## Owner creative contract (2026-08-11 review + 2026-08-12 owner direction)

The gates below are enforced mechanically by `node scripts/render-video.js --check`
and `node scripts/render-design.js --check` — a deliverable that violates any of
them fails the gate:

1. **ONE narration persona.** `narration.json` `voice_selection` pins the exact
   persona voice (`Charon`). Every clip for every scenario is generated with
   that same persona. There is no per-call voice argument, no auditioning,
   no mixing clips from different generations. `tts-gemini.js` refuses voice
   overrides and purges stale clips before generating; `mix-audio.js` refuses
   mismatched provenance (narration.json + `.voice-manifest.json`).
2. **Multi-provider fallback chain (owner direction 2026-08-12).** Narration
   is produced through a deterministic chain: **Gemini 2.5 Flash TTS
   (primary)** → **Mistral Voxtral (fallback 1, both API keys with
   failover)** → **Cartesia (fallback 2)** → **ElevenLabs (fallback 3)**.
   On rate-limit/quota/auth/5xx failure the generator logs provider + status,
   purges the partial scenario clips, and the next provider retries the same
   clip. A clip is never silently dropped, the voice never changes
   mid-scenario, and stale clips are never reused. Per-scenario provider +
   voice provenance lands in `narration.json` (`scene_timing.<s>.provider` /
   `provider_voice`) and `.voice-manifest.json`. Every provider pins a
   masculine low-register voice matching the persona — the result must sound
   like the same guy across every clip and both scenarios.
3. **Full sentences — speech first, readable scenes.** Scene windows come from the
   MEASURED spoken clip durations written into `narration.json` →
   `scene_timing`, plus a 650ms visual lead, minimum 3s dwell (4s CTA), and a
   650ms post-speech hold. The Short expands to the measured schedule under
   60s; a hardcoded duration can never cut a sentence or rush a title. Clips
   are silent-edge trimmed only (no atempo, no mid-sentence trims).
4. **No music.** The mix is narration-only: no music bed, no duck bus. The
   spec in `narration.json` (`mix.music: "none"`) carries no music fields.
5. **Node pulses on the line, once.** Stations ride the journey path
   (`path.getPointAtLength` at each scene's measured start fraction) and fire
   a one-shot subtle ring flash exactly when the line reaches them. Never an
   infinite ring animation on stations.
6. **Website typography.** Titles are Outfit weight 800 and centered. Fonts
   must resolve in the render context exactly like the site (see Fonts
   section) — a system-font fallback fails the gate.
7. **Flat canvas graphics.** Social templates are canvas compositions
   (connected journey line, loop symbol, centered bold Outfit title), never
   card-with-arrows website-screenshot layouts.
8. **One controlled scene source.** Campaign narration must declare
   `scene_control_version: "1.0"`. Every scene carries spoken `text` plus a
   `visual` object containing `eyebrow`, the identical displayed `headline`,
   `supporting_text`, registered `component`, Boxicon `icon`, and `labels`.
   The hook text equals the complete designed title. Templates contain no
   fallback campaign copy or legacy product cards; render/TTS gates reject a
   missing field or spoken/displayed mismatch. The only declared exception is
   a CTA with `spoken_display_alignment: "url-pronunciation"`: speech must say
   “Go to SpielOS dot xyz slash services.” while the frame must display the
   real destination `spielos.xyz/services`.
9. **Pronunciation guidance is never copy.** Provider input may substitute
   phonetic spelling (`Shpeel O S`) but may never inject parentheticals such as
   “pronounced …” into the transcript. `node scripts/tts-gemini.js --check`
   enforces this without calling a provider.

## Pipeline overview

```
Order → Idea lock (One Idea Hierarchy) → scenario script (persona contract)
→ TTS through provider chain (pinned persona, measured scene_timing)
→ silent-edge trim + MEASURED scene_timing (speech first)
→ narration-only mix (-16 LUFS / -1 dBTP, 48kHz AAC)
→ base render (templates read scene_timing) → merge audio → stable hook thumbnail
→ audible-speech/provenance QA → campaign-local deliverable
```

How a scenario is produced:

1. Write narration script (one line per scene) in `templates/video/narration.json`
2. `node scripts/tts-gemini.js <b|c>` — narration through the provider chain
   with the pinned persona voice; purges stale clips for the scenario, measures
   each spoken take, saves `scene_timing` into `narration.json` and provenance
   into `public/videos/audio/.voice-manifest.json`. Fails on overrun (tighten
   the TEXT) and on any voice override. Falls through the chain on provider
   failure (see Troubleshooting).
3. `node scripts/mix-audio.js <b|c>` — narration-only mix from the measured
   schedule, loudnorm -16 LUFS / true peak -1 dBTP, 48kHz AAC. No music bed;
   refuses mismatched voice provenance or a missing measured schedule.
4. `node scripts/render-video.js <scenario> <aspect> 30 <out-base.mp4>` —
   Puppeteer frame capture + FFmpeg encode at 30fps. Templates read
   `scene_timing` from narration.json themselves.
5. Merge mix into base MP4 (copy video, AAC audio)
6. Thumbnail after the full hook composition is stable (normally 2.2s into
   the hook), never the half-revealed 0.6s frame.
7. QA gates verify streams, loudness, audible source clips, item provenance,
   narration-led duration, dimensions/FPS, and thumbnail dimensions.

Run the whole chain per scenario with:
`bash scripts/render-all.sh <b|c> [30] [aspects]`
Campaign deliverables land beside their campaign manifest under
`<batch>/youtube-shorts/<item-id>/{video.mp4,thumbnail.jpg,qa.json}`. Legacy
private showcase renders alone may use the historical Design production path.

## Video order flow (the department takes orders)

The Design department accepts video orders end-to-end:

1. **Order intake** — topic, channel/aspect, deadline/context.
2. **Idea lock** — One Idea Hierarchy from `strategy/voice.md`: company-promise
   connection + one topic-specific idea + one asset execution. Check the topic
   against the canonical ICP/positioning (`strategy/icp.md`, `positioning.md` —
   reference, never restate) so the asset stays buyer-aligned.
3. **Scenario script** — narration lines per the persona copywriting contract
   (below), one line per scene, CTA completed in full.
4. **TTS via provider chain** — `node scripts/tts-gemini.js <b|c>`.
5. **Narration-only mix** — `node scripts/mix-audio.js <b|c>`.
6. **Render** — base render, narration merge, stable hook thumbnail.
7. **QA gates** — contract gates plus audible speech, loudness, provenance,
   timing, dimensions/FPS, and thumbnail inspection.
8. **Deliverable** — lean three-file set beneath the campaign batch Artifact.

The runtime catalog exposes this as the `video-order` workflow in
`company/departments/design/department.py`; the existing `video-render`
workflow remains for render-and-verify work on settled scripts.

## One Idea Hierarchy and visual lock

Before scripting, lock the company-promise connection, one topic-specific idea,
and one asset execution. The title, narration, scenes, signature line, music,
and CTA must support the same topic. A video may explain a different mechanism,
problem, or objection than another video; it must still connect naturally to
the company offer.

The visual authority is the existing flat Gruvbox composition: subtle grid,
centered Outfit typography, restrained Boxicons, and the wandering goal line.
Completed travel is solid primary; future travel is muted dashed; the line ends
in a flat bullseye. Add only alignment, spacing, official logo, centered URL,
and readability polish. Do not introduce 3D, device mockups, glassmorphism,
card-heavy redesigns, or spectacle-led gradients.

> Note: in the narration lines above, "music" is a legacy word in the
> hierarchy rule — the final deliverables are narration-only; the rule's
> intent is that every element of the piece supports the same topic.

### Copywriting contract (per order, owner direction 2026-08-12)

The narration contract lives in `narration.json` → `tone_contract` and is the
creative law for every script:

- **ALWAYS a masculine voice.** No exceptions, no female voices, no ambiguous
  voices.
- **Tone:** Active, Very Confident, Demanding, Aggressive, but friendly —
  professional AND casual, NOT formal at all. He knows exactly what he is
  doing and saying, with 10000% confidence.
- **Copywriting:** proper short sentences, deliberate pauses, viral-style
  titles; every word makes the viewer curious about the next one. Proper flow,
  proper video scenarios.
- **Pace:** slow enough that the voice covers the full sentence within its
  scene. Scene timing derives from MEASURED spoken clip durations (speech
  first) — never fixed-window trims, no atempo.
- **One persona** across every clip, both scenarios, all providers. Each
  provider picks the masculine voice that best matches the persona; the result
  must sound like the same guy.
- **CTA line** lands fully and human-readable: "spielos dot xyz slash services".
- Lines are written short enough to keep the narration-led Short under 60s at
  the contract's slow, confident pace; titles are never rushed to hit 15s.

---

## TTS voice — one pinned persona, no auditions

### Provider chain (production)

`scripts/tts-gemini.js` orchestrates the chain defined in
`scripts/tts-providers.js`. All keys load ONLY from `.spielos/.env`; the
persona is pinned in `templates/video/narration.json` → `voice_selection`
(currently `Charon`, a natural low-register prebuilt male voice) and is read by
the generator — there is no CLI voice argument, so a clip can never be
generated with a different persona:

| Order | Provider | Voice pin (masculine, low-register) |
|---|---|---|
| 1 (primary) | Gemini 2.5 Flash TTS (`gemini-2.5-flash-preview-tts`) | Charon (prebuilt), via `prebuiltVoiceConfig` |
| 2 (fallback 1) | Mistral Voxtral (`https://api.mistral.ai/v1`) | Discovered at runtime from the voice catalog; masculine shortlist pinned in `tts-providers.js`; `MISTRAL_API_KEY` then `MISTRAL_API_KEY_2` on failover |
| 3 (fallback 2) | Cartesia (`https://api.cartesia.ai`) | `kurt` (deep masculine), cheapest strong tier (`sonic-2`, falls back to `sonic-english`) |
| 4 (fallback 3) | ElevenLabs (`https://api.elevenlabs.io/v1`) | `Adam` (premade masculine), `eleven_turbo_v2_5` |

Fallback contract: on rate-limit/quota/auth/5xx the generator logs
`provider + status`, purges the partial scenario, and the next provider
retries the same clip. **Never silently drop a clip, never switch voice
mid-scenario, never reuse stale clips.** If EVERY provider is exhausted, stop
and report honestly with partial state.

Operational modes:

```bash
node scripts/tts-providers.js --check  # keys + chain order + voice pins (exit 0/1)
node scripts/tts-providers.js --list   # providers/models/voices — no secrets
node scripts/tts-providers.js --probe  # live diagnostic clip per provider (never used for deliverables)
```

Follow the approved performance direction in `narration.json` (`voice_direction`
+ `tone_contract`): deep grounded adult male, active, very confident,
demanding, aggressive but friendly, professional AND casual — not formal at
all. Do not imitate or claim to reproduce any real person.

Deliberate pronunciation fixes (the legacy Kokoro take failed these):
- `SpielOS` is spoken as "shpeel-oh-es" (never "zyos");
- `spielos.xyz` is spoken as "spielos dot ex why zee";
- the URL CTA always ends fully: "... slash services".

The generator adds these automatically; do not remove them.

Rate limits: the generator spaces calls ~30s apart when primary (Gemini free
tier is 3 requests/min) and retries transient 429/5xx with backoff (20–70s).
Never parallelize TTS calls. If a provider is throttled, WAIT and retry —
prefer the chain fallback only when a provider is truly exhausted.

**No-cut rule:** clips are silent-edge trimmed only. Never atempo-fit a clip
and never trim mid-sentence. If the narration-led schedule reaches the 55s
production guardrail, tighten the narration TEXT and regenerate. Cutting a
sentence mid-word is a rejected deliverable.

### Legacy Kokoro fallback (deprecated — never production)

The robotic `am_michael` Kokoro clips caused rejected deliveries (bad
pronunciation, unnatural pacing, mid-sentence cuts) and mixed ~5 voices into
earlier renders. They are archived under `public/videos/audio/legacy-kokoro/`
and are NOT production assets; they are not referenced by the pipeline and
must never be mixed with chain clips.

---

## Scene fit and timing — speech first, then scenes

All clips in a scenario use the SAME pinned persona and a consistent human
pace. Scene timing is derived from MEASURED spoken clip durations, never from
hardcoded windows:

1. `tts-gemini.js` generates each line (pinned persona, through the chain),
   silent-edge trims, and measures the take with ffprobe.
2. Every scene establishes visually for 650ms before speech. It then holds
   until both the full measured take plus 650ms settle and the 3s readability
   minimum are satisfied; the CTA has a 4s minimum.
3. The measured schedule is persisted into `narration.json` → `scene_timing`
   (with the voice + provider + provider voice) and consumed by
   `scripts/mix-audio.js` AND the video templates (they `fetch()` narration.json
   at load — no template edit step needed, no window to drift).
4. The final scene end becomes the render/mix duration. If it exceeds the 55s
   production guardrail, tighten text and regenerate—never cut or speed words.

Scene windows in the templates: scene `i` is active from
`scene_timing[i].start` to `scene_timing[i].end` (the last scene holds to the
dynamic duration). Element reveals are small offsets after each scene's start. Station
nodes pop in and flash once when the line's progress reaches their scene
start fraction.

---

## Audio pipeline — narration only

### Narration scripts

**Scenario B (Before/After — disconnected AI tools need one operating system)**:
```
Hook:    "AI tools work alone."
Pain:    "Prompts vanish. Context resets."
Promise: "Give AI one system."
Pillars: "Roles. Skills. Evals. Workflows."
Director: "Set the goal. It runs."
CTA:     "Direct it. spielos dot xyz slash services."
```

**Scenario C (Build It — a real AI department is built from roles, context, standards, workflows)**:
```
Hook:    "Build your AI department."
Build:   "Roles. Context. Standards. Workflows."
Live:    "Now it's live."
Director: "Choose the goal. You judge."
CTA:     "Build it. spielos dot xyz slash services."
```

### Mix (narration-only)

`node scripts/mix-audio.js <b|c>` mixes the measured clips with per-scene
delays and fades, loudnorm −16 LUFS / TP −1 dBTP, 48kHz stereo AAC, for the
narration-led dynamic duration.
There is NO music input, no duck bus, and no music file requirement. The mix
refuses to run without a measured schedule (a sentence can never be cut by a
hardcoded window) and refuses mismatched voice provenance.

```bash
node scripts/mix-audio.js b .spielos/artifacts/audio/mix-b.m4a
node scripts/mix-audio.js c .spielos/artifacts/audio/mix-c.m4a
```

### Verify the mix

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 mix-b.m4a  # equals scene_timing.duration
ffprobe -v error -show_entries stream=codec_type,sample_rate -of json mix-b.m4a  # audio 48000
```

---

## Rendering

### Single video

```bash
node scripts/render-video.js <scenario> <aspect> [fps] [output]
```

**Scenarios**: `b` (Before/After), `c` (Build It)

**Aspects**:
| Name | Resolution | Use |
|---|---|---|
| landscape | 1920x1080 | YouTube, LinkedIn, X |
| portrait | 1080x1920 | Reels, TikTok, Shorts |
| square | 1080x1080 | Instagram feed |
| story | 1080x1350 | Instagram portrait |

### Examples

```bash
node scripts/render-video.js b landscape 30
node scripts/render-video.js b portrait 30
node scripts/render-video.js c landscape 30
node scripts/render-video.js c portrait 30
node scripts/render-video.js --check
```

### Owner-contract gate

```bash
node scripts/render-video.js --check
node scripts/render-design.js --check
node scripts/tts-providers.js --check
```

`--check` launches the real render context (repo root served over localhost)
and fails on: multi-voice narration.json, any music spec remnants in the
spec/pipeline/templates, missing Outfit font in-render
(`document.fonts.check("800 16px Outfit")`), titles not Outfit 800/centered,
stations off the journey line, hardcoded scene windows, and infinite ring
pulses. Run the gates before every render batch.

### Merge audio into video

```bash
ffmpeg -y -i base-video.mp4 -i mix.m4a -c:v copy -c:a aac -b:a 192k -shortest output-voiced.mp4
```

---

## Thumbnail generation

```bash
ffmpeg -y -ss <min(hookEnd-0.35,hookStart+2.2)> -i video.mp4 -vframes 1 -q:v 2 thumbnail.jpg
node scripts/verify-video-deliverable.js video.mp4 qa.json
```

---

## Full workflow

```bash
# 0. Gate the environment (keys + chain + voice pins)
node scripts/tts-providers.js --check

# 1. Generate + measure narration (ONE pinned persona, chain fallback, stale clips purged)
node scripts/tts-gemini.js b
node scripts/tts-gemini.js c

# 2. Narration-only mixes
node scripts/mix-audio.js b
node scripts/mix-audio.js c

# 3. Render base video (templates time themselves from scene_timing)
node scripts/render-video.js b landscape 30

# 4. Merge narration-only audio
ffmpeg -y -i .spielos/artifacts/design-restoration-polish-20260810/video/spielos-before-after-flat-polish-16x9-base.mp4 \
  -i .spielos/artifacts/audio/mix-b.m4a -c:v copy -c:a aac -b:a 192k -shortest \
  spielos-before-after-16x9-voiced.mp4

# 5. Stable hook thumbnail + final QA
ffmpeg -y -ss 2.2 -i video.mp4 -frames:v 1 thumbnail.jpg
node scripts/verify-video-deliverable.js video.mp4 qa.json
```

Or run the whole chain per scenario: `bash scripts/render-all.sh <b|c>`.

---

## HTML template anatomy

### Virtual clock

```javascript
window.__t = 0;        // Current time in seconds
window.__fps = 30;     // Frames per second
window.__duration = 15; // Total duration

window.__setFrame = function(frame, fps) {
  window.__fps = fps || 30;
  window.__t = frame / window.__fps;
};
```

### Measured scene schedule (speech first)

Templates fetch the measured schedule at load and gate on it — the frame
stays dark until the schedule arrives, so a render can never start on a
guessed window:

```javascript
window.__timing = null;
fetch('/company/departments/design/templates/video/narration.json')
  .then(r => r.json())
  .then(d => { window.__timing = d.scene_timing && d.scene_timing.b; });
```

### Scene system

```css
.scene {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; z-index: 10;
}
.scene.active { opacity: 1; pointer-events: auto; }
```

### Text reveal

```css
.r {
  opacity: 0; transform: translateY(24px); filter: blur(4px);
  transition: opacity 0.6s cubic-bezier(0.16,1,0.3,1),
              transform 0.6s cubic-bezier(0.16,1,0.3,1),
              filter 0.4s cubic-bezier(0.16,1,0.3,1);
}
.r.show { opacity: 1; transform: translateY(0); filter: blur(0); }
```

### Tick function pattern

```javascript
function tick() {
  var t = window.__t;
  if (!window.__timing) { requestAnimationFrame(tick); return; }
  var sc = window.__timing.scenes;         // measured windows
  var idx = -1;
  for (var i = 0; i < sc.length; i++) {
    if (t >= sc[i].start && (i === sc.length - 1 || t < sc[i + 1].start)) { idx = i; break; }
  }
  if (idx === 0) { act('s1'); /* reveals relative to sc[0].start */ }
  // ...
  requestAnimationFrame(tick);
}
tick();
```

### Stations on the line (one-shot node hit)

```javascript
// Place each station at its scene-start fraction of the path:
var pt = pathFill.getPointAtLength((sc[sceneIdx].start / lineEnd) * pathLen);
stationEl.setAttribute('transform', 'translate(' + pt.x + ',' + pt.y + ')');
// Fire ONCE when the line reaches it:
if (!fired && progress >= frac) { stationEl.classList.add('show'); ring.classList.add('hit'); }
```

The `.hit` class triggers the one-shot `nodeHit` flash in `brand-motion.css`
(`animation: nodeHit .55s ease-out 1`) — never an infinite ring.

---

## Fonts and tokens in the render context

Templates link `system/production.css`, which:

1. Declares Outfit (variable 100–900), JetBrains Mono (400–600), and boxicons
   `@font-face` blocks with repo-root-resolvable paths
   (`/public/assets/fonts/*.woff2`) — the website's `src/assets/fonts/fonts.css`
   uses built-only `/assets/...` URLs, so the design system declares the same
   families itself for renders.
2. Defines `--font-outfit`/`--font-jetbrains-mono` BEFORE importing the
   canonical tokens (`/src/styles/tokens/index.css`), so the token `--font-sans`
   stack stays valid.
3. Renders must serve the repo ROOT over localhost (both render scripts do) —
   never `file://`, where absolute site-root paths fail.

Titles must be `font-weight: 800` and centered; the gates verify both
in-render.

---

## Boxicons in headless Chrome

Boxicons require TWO things to render in Puppeteer:

1. **CSS link** in `<head>`:
```html
<link rel="stylesheet" href="/node_modules/boxicons/css/boxicons.min.css">
```

2. **A boxicons @font-face** — provided by `production.css`
(`/public/assets/fonts/boxicons.woff2`).

Without both, icons render as empty squares.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Icons empty squares | Confirm the boxicons CSS link + production.css font-face load (repo root served) |
| Gate: Outfit not loaded | Confirm production.css loads; render over localhost, never file:// |
| Gate: station off the line | Templates place stations via `path.getPointAtLength` — don't hand-place coords |
| Gate: scene_timing not applied | Run `tts-gemini.js` first; templates fetch narration.json at load |
| Provider throttled (429/5xx) | Generator waits and retries with backoff; if truly exhausted it falls to the next provider and RESTARTS the scenario (voice never changes mid-scenario) |
| ALL providers exhausted | Stop, keep partial artifacts, report honestly — never fabricate completion |
| `tts-providers.js --check` exit 1 | `.spielos/.env` missing one of the five keys (GEMINI, MISTRAL, MISTRAL_2, CARTESIA, ELEVENLABS), chain reordered, or a voice pin empty |
| Scene bleed (old text visible) | Remove CSS `transition` from `.scene` opacity |
| Frames directory error | Run renders sequentially, not parallel (shared frame dir) |
| Mix refuses to run | Measured `scene_timing` missing or voice provenance mismatch — regenerate with the pinned persona |

---

## Output rules

After creating a video, report:

- Template file path
- Output file path
- Aspect ratios rendered
- Persona used (must equal `narration.json` `voice_selection` for BOTH scenarios)
- Per-scenario provider + provider voice (from `scene_timing` / `.voice-manifest.json`), any fallbacks triggered
- Measured speech windows, readable visual windows, and dynamic duration
- Duration and FPS
- Total frames
- File size
- Any rendering issues
- Audio-stream, loudness, audible-source-clip, narration completeness, and
  voice/campaign provenance verification
- Thumbnail path and QA report path beneath the same batch/item directory
