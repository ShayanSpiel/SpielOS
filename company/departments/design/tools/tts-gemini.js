#!/usr/bin/env node
/**
 * tts-gemini.js — Generates scene narration clips through the TTS provider
 * chain. The CLI name is preserved (SKILL.md and the render gates call
 * `tts-gemini.js <key>` for keys b..i — the registered Shorts archetypes).
 * b/c keep private demo lines for template regression; d..i are campaign-only
 * (they require CAMPAIGN_MANIFEST + CAMPAIGN_ITEM_ID).
 *
 * Owner contract (2026-08-11 review + 2026-08-12 owner direction):
 *  - ONE narration persona: MASTER_VOICE is pinned here AND in narration.json
 *    `voice_selection` (Charon — a natural low-register male prebuilt voice).
 *    There is no per-call voice argument, no auditioning, no mixed
 *    generations. Every clip for every scenario uses the same persona; each
 *    provider's masculine voice is chosen to match it, and the scenario is
 *    RESTARTED from scratch when a provider fails — the voice never changes
 *    mid-scenario and stale partial clips are purged.
 *  - Provider fallback chain (deterministic): Gemini (primary) → Mistral
 *    Voxtral (fallback 1, both keys with failover) → Cartesia (fallback 2) →
 *    ElevenLabs (fallback 3). On rate-limit/quota/auth/5xx failure the
 *    provider + status are logged, partial clips for the scenario are purged,
 *    and the next provider retries the same clip. A clip is never silently
 *    dropped and stale clips are never reused.
 *  - Full sentences: scene timing is derived from the MEASURED spoken clip
 *    durations (speech first, then scenes). Clips are only silent-edge
 *    trimmed — never atempo-fitted and never trimmed mid-sentence. The
 *    Visual scene windows add a readable lead and hold around the measured
 *    speech. The Short expands to that narration-led schedule instead of
 *    squeezing every line into a hardcoded 15-second canvas.
 *  - Provenance: per-scenario provider + voice are recorded in narration.json
 *    (`scene_timing.<s>.provider` / `provider_voice`) and in
 *    public/videos/audio/.voice-manifest.json. scripts/mix-audio.js refuses
 *    to mix clips whose manifest voice differs from the pinned persona voice.
 *
 * Usage:
 *   node scripts/tts-gemini.js <b|c|d|e|f|g|h|i>
 *   node scripts/tts-gemini.js --check
 *
 * Writes clips to public/videos/audio/<scenario>-<scene>.wav (44.1kHz mono)
 * and saves the measured scene schedule into narration.json under
 * `scene_timing`, which scripts/mix-audio.js and the templates consume.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync, rmSync } from "fs";
import { execSync } from "child_process";
import { join, resolve } from "path";
import { fileURLToPath } from "url";
import { CHAIN, VOICE_PINS, loadEnv, keyFor, synthesize, ProviderError, TRANSIENT_STATUSES, discoverVoices } from "./tts-providers.js";

const ROOT = resolve(fileURLToPath(new URL("../../../..", import.meta.url)));
const AUDIO = join(ROOT, "public/videos/audio");
const MANIFEST = join(AUDIO, ".voice-manifest.json");
const NARRATION = join(ROOT, "company/departments/design/templates/video/narration.json");
const config = JSON.parse(readFileSync(NARRATION, "utf8"));
const CAMPAIGN_PATH = process.env.CAMPAIGN_MANIFEST
  ? resolve(process.env.CAMPAIGN_MANIFEST) : null;
const CAMPAIGN_ITEM_ID = process.env.CAMPAIGN_ITEM_ID || "";

/* ── The single pinned persona voice (owner contract №1). ──
   Charon is a natural low-register male prebuilt Gemini voice. It must match
   narration.json `voice_selection`; a mismatch is a hard failure. Fallback
   providers pick their own masculine voice that matches this persona, but the
   recorded provenance voice stays the persona pin so generations can never
   mix. */
const MASTER_VOICE = config.voice_selection || "Charon";

/* Structural scene order per archetype key. The ids match BOTH the registered
   template scene nodes (registry.json scene_control.scenes) AND the campaign
   narration scenes the strategist writes for that archetype. b/c also have
   private demo lines in narration.json (config.scenarios) for template
   regression; d..i are campaign-only. */
const SCENE_ORDER = {
  b: ["hook", "pain", "promise", "pillars", "director", "cta"],
  c: ["hook", "build", "live", "director", "cta"],
  d: ["hook", "claim", "proof", "resolve", "cta"],
  e: ["problem", "turn", "result", "cta"],
  f: ["stat", "claim", "proof", "cta"],
  g: ["question", "stakes", "resolve", "cta"],
  h: ["band", "goal", "watch", "run", "cta"],
  i: ["band", "goal", "watch", "cta"],
};

/* Per-scene delivery intent (scene_control_version 1.1): the storyteller locks
   how each line lands, and the primary LLM narrator follows it. Pure TTS
   engines receive only the plain line (they would speak the direction). */
const SCENE_INTENTS = new Set(["question/rising", "statement/falling", "command/falling"]);
const SCENE_DELIVERY = {
  "question/rising": "Land this line as a rising question — pitch climbing at the end, curiosity, never flat reading.",
  "statement/falling": "Land this line as a certain flat statement — conviction at the end, decisive fall, no lift.",
  "command/falling": "Land this line as a direct command — clean close, no salesy upswing.",
};

const checkOnly = process.argv[2] === "--check";
const scenario = checkOnly ? "b" : process.argv[2];
if (process.argv[3]) {
  console.error("Voice override is not allowed: EVERY clip must use the pinned master voice.");
  process.exit(1);
}
if (!SCENE_ORDER[scenario]) {
  console.error(`Unknown scenario: ${scenario}. Registered Shorts archetype keys: ${Object.keys(SCENE_ORDER).join(", ")}.`);
  process.exit(1);
}

const env = loadEnv();

/* Speech first, with enough visual time to read. Each scene establishes for
   650ms before narration, holds after the final word, and never becomes
   shorter than the template's complete reveal. Shorts remain under 60s. */
const SPEECH_LEAD = 0.65;
const POST_SPEECH_HOLD = 0.65;
const MIN_VISUAL_DWELL = 3.0;
const CTA_MIN_VISUAL_DWELL = 4.0;
const MAX_SHORT_DURATION = Number(config.max_duration_seconds || 55);

const PRONUNCIATION = [
  [/spielos\.xyz\/services/gi, "Shpeel O S dot ex why zee slash services"],
  [/spielos dot xyz slash services/gi, "Shpeel O S dot ex why zee slash services"],
  [/spielos\.xyz/gi, "Shpeel O S dot ex why zee"],
  [/SpielOS/g, "Shpeel O S"],
];

const PERFORMANCE = config.voice_direction +
  " Deliver the take like a founder who owns the room: short punchy sentences," +
  " deliberate pauses, zero formality, total certainty. Keep lists moving but" +
  " land each word. No robotic spacing, no dead air, no rushed endings — finish" +
  " every word, and complete the final line fully.";

function pipe(text) {
  let out = text;
  for (const [bad, good] of PRONUNCIATION) out = out.replace(bad, good);
  return out;
}

function sceneCopyAligned(scene) {
  const spoken = String(scene.text || "").trim().toLowerCase();
  const visual = scene.visual || {};
  const displayed = String(visual.headline || "").trim().toLowerCase();
  if (visual.spoken_display_alignment === "url-pronunciation") {
    return visual.component === "cta" && displayed === "spielos.xyz/services" &&
      spoken === "go to spielos dot xyz slash services.";
  }
  return Boolean(displayed) && displayed === spoken;
}

if (checkOnly) {
  const sample = pipe("SpielOS connects the work. SpielOS dot xyz slash services.");
  if (/pronounc|\(|\)/i.test(sample) || !sample.includes("Shpeel O S")) {
    console.error("TTS pronunciation check failed: guidance must alter phonemes without becoming spoken copy.");
    process.exit(1);
  }
  console.log("TTS text check OK: SpielOS phonemes are guided without spoken pronunciation instructions");
  process.exit(0);
}

function dur(file) {
  return parseFloat(execSync(`ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 ${file}`).toString().trim());
}

/* Convert a provider raw take into the canonical 44.1kHz mono wav. */
function toWav(raw, meta, wav) {
  if (meta.isRawPcm) {
    const rate = meta.sampleRate || 24000;
    execSync(`ffmpeg -y -v error -f s16le -ar ${rate} -ac 1 -i ${raw} -ar 44100 -ac 1 -c:a pcm_s16le ${wav}`);
  } else {
    execSync(`ffmpeg -y -v error -i ${raw} -ar 44100 -ac 1 -c:a pcm_s16le ${wav}`);
  }
  rmSync(raw, { force: true });
}

/* One take through one provider, with transient retries. Non-transient or
   exhausted providers throw ProviderError so the orchestrator can fall
   through the chain. */
async function synth(provider, line, idx, sceneIntent) {
  const speech = pipe(line);
  /* Gemini is an LLM TTS: it understands the performance direction and speaks
     only the quoted line. Pure TTS engines (Mistral/Cartesia/ElevenLabs) read
     EVERYTHING aloud — sending them the direction block produced ~55s takes
     of instructions, so they only ever receive the plain line. */
  const delivery = SCENE_DELIVERY[sceneIntent] ? `\nDelivery (this line): ${SCENE_DELIVERY[sceneIntent]}` : "";
  const text = provider === "gemini" ? `${PERFORMANCE}${delivery}\nNarrate: "${speech}"` : speech;
  const raw = join(AUDIO, `.tmp-${scenario}-${idx}.raw`);
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const meta = await synthesize(provider, { text, outFile: raw, env });
      const wav = join(AUDIO, `.tmp-${scenario}-${idx}.wav`);
      toWav(raw, meta, wav);
      return { wav, voice: meta.voice, provider };
    } catch (err) {
      const status = err instanceof ProviderError ? err.status : 0;
      const transient = err instanceof ProviderError && TRANSIENT_STATUSES.has(status);
      if (transient && attempt < maxAttempts) {
        const wait = 20 + attempt * 25;
        console.log(`    ${provider} throttled (${status}) — waiting ${wait}s (attempt ${attempt}/${maxAttempts})`);
        await new Promise((r) => setTimeout(r, wait * 1000));
        continue;
      }
      throw err;
    }
  }
  throw new ProviderError(provider, 0, "transient retries exhausted");
}

function trimEdges(file) {
  const out = `${file}.t.wav`;
  execSync(`ffmpeg -y -v error -i ${file} -af "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,areverse" -ar 44100 -ac 1 -c:a pcm_s16le ${out}`);
  return out;
}

/* SCENE_ORDER is declared above (all 8 registered Shorts keys). */

let campaign = null;
let campaignItem = null;
let campaignRendition = null;
if (CAMPAIGN_PATH || CAMPAIGN_ITEM_ID) {
  if (!CAMPAIGN_PATH || !CAMPAIGN_ITEM_ID) {
    console.error("Set both CAMPAIGN_MANIFEST and CAMPAIGN_ITEM_ID for campaign narration.");
    process.exit(1);
  }
  campaign = JSON.parse(readFileSync(CAMPAIGN_PATH, "utf8"));
  campaignItem = (campaign.items || []).find((item) => item.item_id === CAMPAIGN_ITEM_ID);
  campaignRendition = campaignItem?.renditions?.youtube;
  if (!campaignRendition?.narration?.scenes) {
    console.error(`Campaign YouTube narration is missing for ${CAMPAIGN_ITEM_ID}.`);
    process.exit(1);
  }
  const sceneControlVersion = campaignRendition.narration.scene_control_version;
  if (sceneControlVersion !== "1.0" && sceneControlVersion !== "1.1") {
    console.error(`Campaign scene-control contract must be 1.0 or 1.1 for ${CAMPAIGN_ITEM_ID}.`);
    process.exit(1);
  }
  if (sceneControlVersion === "1.1") {
    if (!String(campaignRendition.narration.script || "").trim()) {
      console.error(`scene_control_version 1.1 requires one complete narration.script before scene-splitting for ${CAMPAIGN_ITEM_ID}.`);
      process.exit(1);
    }
    for (const scene of campaignRendition.narration.scenes) {
      if (!SCENE_INTENTS.has(String(scene.intent || ""))) {
        console.error(`Narration scene ${scene.id || "?"} needs a delivery intent ${[...SCENE_INTENTS].join("|")} for ${CAMPAIGN_ITEM_ID}.`);
        process.exit(1);
      }
    }
  }
  const designedHook = (campaignRendition.design?.title_lines || []).join(" ").replace(/\s+/g, " ").trim();
  for (const scene of campaignRendition.narration.scenes) {
    if (!sceneCopyAligned(scene)) {
      console.error(`Spoken/displayed scene mismatch for ${CAMPAIGN_ITEM_ID}/${scene.id}.`);
      process.exit(1);
    }
  }
  if (campaignRendition.narration.scenes[0].text.replace(/\s+/g, " ").trim().toLowerCase() !== designedHook.toLowerCase()) {
    console.error(`Hook narration must equal the complete designed title for ${CAMPAIGN_ITEM_ID}.`);
    process.exit(1);
  }
  if (campaignRendition.narration.scenes.length !== SCENE_ORDER[scenario].length) {
    console.error(`Scenario ${scenario} needs ${SCENE_ORDER[scenario].length} campaign narration scenes.`);
    process.exit(1);
  }
}

const activeLines = campaignRendition
  ? campaignRendition.narration.scenes.map((scene) => String(scene.text || "").trim())
  : config.scenarios[scenario];
if (!Array.isArray(activeLines) || activeLines.some((line) => !line)) {
  console.error(campaignRendition
    ? "Every campaign narration scene needs complete spoken text."
    : `Scenario ${scenario} has no demo lines; Shorts archetypes d..i require CAMPAIGN_MANIFEST + CAMPAIGN_ITEM_ID.`);
  process.exit(1);
}

function purgeScenario() {
  for (const f of readdirSync(AUDIO)) {
    if (f.startsWith(`${scenario}-`) && f.endsWith(".wav")) {
      rmSync(join(AUDIO, f), { force: true });
      console.log(`  purged stale clip ${f}`);
    }
  }
}

/* Try to generate the WHOLE scenario with one provider. On failure, purge
   every clip this provider produced so a half-finished generation can never
   leak into a mix — the next provider restarts from scratch (never switch
   voice mid-scenario). */
async function tryProvider(provider) {
  const lines = activeLines;
  const scenes = SCENE_ORDER[scenario];
  const pin = VOICE_PINS[provider];
  const key = keyFor(provider, env);
  if (!key) {
    console.log(`  ${provider}: skipped (${pin.envKeys.join("/")} not set in .spielos/.env)`);
    return null;
  }
  let voice = pin.voice;
  try {
    const discovered = await discoverVoices(provider, env);
    if (discovered.voice) voice = discovered.voice;
    if (!discovered.ok && provider !== "gemini") {
      console.log(`  ${provider}: skipped (voice discovery failed: ${discovered.reason})`);
      return null;
    }
  } catch (e) {
    console.log(`  ${provider}: skipped (discovery error: ${String(e.message || e).slice(0, 120)})`);
    return null;
  }

  console.log(`  Generating ${lines.length} clips with ${provider}${voice ? ` (voice ${voice})` : ""} for scenario ${scenario}`);
  console.log(`  Pinned single persona — no overrides, no mixing, no atempo (edge-trim only)\n`);

  const fitted = [];
  for (let i = 0; i < lines.length; i++) {
    const scene = scenes[i];
    try {
      const sceneIntent = campaignRendition?.narration?.scenes?.[i]?.intent;
      const { wav } = await synth(provider, lines[i], i, sceneIntent);
      const trimmed = trimEdges(wav);
      rmSync(wav, { force: true });
      const final = join(AUDIO, `${scenario}-${scene}.wav`);
      execSync(`ffmpeg -y -v error -i ${trimmed} -ar 44100 -ac 1 -c:a pcm_s16le ${final}`);
      rmSync(trimmed, { force: true });
      const d = dur(final);
      /* One scene cannot consume nearly the whole Shorts budget. Treat such
         output as provider padding/garbage and retry the complete scenario
         with the next provider; never cut the take. */
      if (d > MAX_SHORT_DURATION - 5) {
        console.error(`  ${provider} clip ${scene} measures ${d.toFixed(2)}s — not a usable Short take; treating ${provider} as failed`);
        for (const f of fitted) rmSync(join(AUDIO, `${scenario}-${f.scene}.wav`), { force: true });
        rmSync(final, { force: true });
        return null;
      }
      console.log(`  ${scene.padEnd(9)} ${d.toFixed(2)}s (measured, full take)`);
      fitted.push({ scene, duration: d });
      /* Gemini's free tier needs its conservative call spacing. The fallback
         TTS providers do not share that quota, so applying the same delay to
         them makes a single six-line fallback render appear to stall and can
         be interrupted before its measured batch completes. */
      await new Promise((r) => setTimeout(r, provider === "gemini" ? 30000 : 500));
    } catch (err) {
      const status = err instanceof ProviderError ? err.status : 0;
      console.error(`  ${provider} failed on ${scene} (status ${status || "?"}): ${String(err.message || err).slice(0, 160)}`);
      for (const f of fitted) rmSync(join(AUDIO, `${scenario}-${f.scene}.wav`), { force: true });
      console.error(`  purged ${fitted.length} partial clip(s) — falling to the next provider (voice never changes mid-scenario)`);
      return null;
    }
  }
  return { provider, voice, fitted };
}

async function main() {
  const lines = activeLines;
  console.log(`\n  Scenario ${scenario}: ${lines.length} lines through chain [${CHAIN.join(" -> ")}] (persona: ${MASTER_VOICE})\n`);

  /* Stale-proof: remove every previous clip for this scenario so the mix can
     never reuse an old voice or an old generation. */
  purgeScenario();

  let chosen = null;
  for (const provider of CHAIN) {
    chosen = await tryProvider(provider);
    if (chosen) break;
    console.log("");
  }
  if (!chosen) {
    console.error("  EVERY provider in the chain is exhausted — no clips generated for this scenario. Partial state kept; do not fabricate completion.");
    process.exit(1);
  }
  const fitted = chosen.fitted;
  const provider = chosen.provider;
  const providerVoice = chosen.voice;

  /* Schedule: readable visuals lead, measured speech plays in full, then the
     scene holds. The next scene cannot begin until both speech and minimum
     visual dwell are satisfied. */
  let t = 0.0;
  const timing = [];
  for (let index = 0; index < fitted.length; index++) {
    const f = fitted[index];
    const start = t;
    const speechStart = start + SPEECH_LEAD;
    const speechEnd = speechStart + f.duration;
    const minimum = index === fitted.length - 1 ? CTA_MIN_VISUAL_DWELL : MIN_VISUAL_DWELL;
    const end = Math.max(start + minimum, speechEnd + POST_SPEECH_HOLD);
    timing.push({
      scene: f.scene,
      start: +start.toFixed(2),
      speech_start: +speechStart.toFixed(2),
      speech_end: +speechEnd.toFixed(2),
      end: +end.toFixed(2),
    });
    t = end;
  }
  const totalEnd = t;
  console.log(`\n  Schedule (from measured spoken durations, provider ${provider}/${providerVoice}):`);
  for (const s of timing) console.log(`    ${s.scene.padEnd(9)} visual ${s.start.toFixed(2)}s → ${s.end.toFixed(2)}s · speech ${s.speech_start.toFixed(2)}s → ${s.speech_end.toFixed(2)}s`);
  console.log(`  Narration-led Short duration: ${totalEnd.toFixed(2)}s`);

  if (totalEnd > MAX_SHORT_DURATION) {
    console.error(`  OVERRUN ${(totalEnd - MAX_SHORT_DURATION).toFixed(2)}s beyond the ${MAX_SHORT_DURATION}s Shorts guardrail — tighten the narration TEXT and regenerate; never cut or speed speech.`);
    process.exit(1);
  }

  /* Persist the schedule + provider/voice provenance for the mix pipeline and templates. */
  config.scene_timing = config.scene_timing || {};
  config.scene_timing[scenario] = {
    timing_contract: "narration-led-v2",
    scene_control_version: campaignRendition?.narration?.scene_control_version || "1.0",
    voice: MASTER_VOICE,
    provider,
    provider_voice: providerVoice,
    generated_at: new Date().toISOString(),
    duration: +totalEnd.toFixed(2),
    speech_lead: SPEECH_LEAD,
    minimum_visual_dwell: MIN_VISUAL_DWELL,
    cta_minimum_visual_dwell: CTA_MIN_VISUAL_DWELL,
    scenes: timing,
  };
  writeFileSync(NARRATION, JSON.stringify(config, null, 2) + "\n");
  if (campaignRendition) {
    campaignRendition.narration.scene_timing = config.scene_timing[scenario];
    campaignRendition.narration.voice = MASTER_VOICE;
    campaignRendition.narration.provider = provider;
    campaignRendition.narration.provider_voice = providerVoice;
    writeFileSync(CAMPAIGN_PATH, JSON.stringify(campaign, null, 2) + "\n");
  }

  /* Persist the manifest for mix-audio.js stale-proofing. */
  let manifest = {};
  if (existsSync(MANIFEST)) {
    try { manifest = JSON.parse(readFileSync(MANIFEST, "utf8")); } catch { manifest = {}; }
    if (manifest.voice && manifest.voice !== MASTER_VOICE) {
      console.error(`  Stale manifest voice ${manifest.voice} — refusing to mix generations. Regenerate everything with ${MASTER_VOICE}.`);
      process.exit(1);
    }
  }
  manifest = {
    voice: MASTER_VOICE,
    voice_selection: config.voice_selection,
    chain: CHAIN,
    updated_at: new Date().toISOString(),
    scenarios: {
      ...(manifest.scenarios || {}),
      [scenario]: {
        provider,
        provider_voice: providerVoice,
        campaign_id: campaign?.campaign_id || null,
        batch_id: campaign?.batch_id || null,
        item_id: campaignItem?.item_id || null,
        generated_at: new Date().toISOString(),
        clips: Object.fromEntries(fitted.map((f) => [f.scene, +f.duration.toFixed(3)])),
      },
    },
  };
  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`  Saved scene_timing + voice manifest (persona ${MASTER_VOICE}, provider ${provider}/${providerVoice}) → narration.json + .voice-manifest.json\n`);
}

main().catch((e) => { console.error(e); process.exit(1); });
