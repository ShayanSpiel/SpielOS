#!/usr/bin/env node
/**
 * mix-audio.js — Builds the SpielOS narration-only audio mix.
 *
 * Owner contract (2026-08-11 review):
 *  - NO music bed. There is no music input, no duck bus, no music file
 *    requirement. Voiced deliverables are narration-only.
 *  - Speech first: scene windows come from the MEASURED scene_timing in
 *    narration.json (written by scripts/tts-gemini.js from real spoken clip
 *    durations). The FALLBACK window table is gone — mixing refuses to run
 *    without a measured schedule, so a sentence can never be cut by a
 *    hardcoded window.
 *  - One voice: the mix refuses if the recorded voice for the scenario is
 *    missing, or if it differs from narration.json `voice_selection` or from
 *    the .voice-manifest.json provenance.
 *
 * Loudness spec lives in narration.json:
 *   narration_lufs -16 · true_peak_dbtp -1 · deliverable 48kHz AAC · music none
 *
 * Usage:
 *   node scripts/mix-audio.js <b|c> [output.m4a]
 *
 * Output defaults to .spielos/artifacts/audio/mix-<scenario>.m4a.
 */

import { execSync } from "child_process";
import { existsSync, mkdirSync, readFileSync } from "fs";
import { join, resolve } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const AUDIO = join(ROOT, "public/videos/audio");
const MANIFEST = join(AUDIO, ".voice-manifest.json");
const TEMPLATES = join(ROOT, ".agents/company/departments/design/templates/video");
const SCENARIOS = { b: ["hook", "pain", "promise", "pillars", "director", "cta"], c: ["hook", "build", "live", "director", "cta"] };

const LUFS_TARGET = -16;
const TRUE_PEAK = -1;

function run(cmd) {
  try {
    return execSync(cmd, { stdio: "pipe", maxBuffer: 32 * 1024 * 1024 });
  } catch (err) {
    console.error("Command failed:", cmd);
    console.error(err.stderr?.toString() || err.message);
    process.exit(1);
  }
}

const scenario = process.argv[2];
const output = resolve(process.argv[3] || join(ROOT, `.spielos/artifacts/audio/mix-${scenario}.m4a`));

if (!SCENARIOS[scenario]) {
  console.error(`Unknown scenario: ${scenario}. Use b or c.`);
  process.exit(1);
}

const narrationPath = join(TEMPLATES, "narration.json");
if (!existsSync(narrationPath)) {
  console.error("Missing narration.json — the mix spec and voice provenance live there.");
  process.exit(1);
}
const cfg = JSON.parse(readFileSync(narrationPath, "utf8"));

/* One-voice contract: the recorded voice must match the pinned selection. */
const timing = cfg.scene_timing?.[scenario];
const cfgVoice = cfg.voice_selection;
if (!timing?.generated_at) {
  console.error("No measured scene_timing — run scripts/tts-gemini.js first so scenes follow the spoken clip durations.");
  process.exit(1);
}
if (!timing.voice || timing.voice !== cfgVoice) {
  console.error(`Voice mismatch: scene_timing.voice=${timing.voice} vs voice_selection=${cfgVoice}. Regenerate every clip with the pinned voice; never mix generations.`);
  process.exit(1);
}
const DURATION = Number(timing.duration || timing.scenes?.at(-1)?.end || 0);
const MAX_DURATION = Number(cfg.max_duration_seconds || 55);
if (!Number.isFinite(DURATION) || DURATION <= 0 || DURATION > MAX_DURATION) {
  console.error(`Invalid narration-led duration: ${DURATION}. Limit: ${MAX_DURATION} seconds.`);
  process.exit(1);
}

/* Manifest provenance (stale-proofing against leftover clips). */
if (existsSync(MANIFEST)) {
  const manifest = JSON.parse(readFileSync(MANIFEST, "utf8"));
  const clips = manifest.scenarios?.[scenario]?.clips || {};
  if (manifest.voice !== cfgVoice) {
    console.error(`Stale clip manifest voice ${manifest.voice} ≠ ${cfgVoice}. Regenerate ALL clips with the pinned voice.`);
    process.exit(1);
  }
  for (const scene of SCENARIOS[scenario]) {
    if (!(scene in clips)) {
      console.error(`Manifest missing clip ${scenario}-${scene}.wav — regenerate the scenario.`);
      process.exit(1);
    }
  }
}

const scenes = timing.scenes.map((s) => ({ ...s, clip: `${scenario}-${s.scene}.wav` }));
for (const s of scenes) {
  if (!existsSync(join(AUDIO, s.clip))) {
    console.error(`Missing narration clip: ${join(AUDIO, s.clip)}`);
    process.exit(1);
  }
}

console.log(`\n  Mixing scenario ${scenario} — ${scenes.length} narration clips (voice: ${timing.voice}), NARRATION-ONLY (no music bed)`);
console.log(`  Spec: ${LUFS_TARGET} LUFS · TP ${TRUE_PEAK} dBTP · 48kHz AAC\n`);

/* Voice bus uses the explicit measured speech window, not the larger visual
   scene window. This preserves the readable visual lead/hold without adding
   silence to, truncating, or shifting the spoken take. */
const inputs = scenes.map((s, i) => `-i ${join(AUDIO, s.clip)}`).join(" ");
const prepped = scenes.map((s, i) => {
  const speechStart = Number(s.speech_start);
  const speechEnd = Number(s.speech_end);
  const window = speechEnd - speechStart;
  if (!Number.isFinite(window) || window <= 0) {
    console.error(`Invalid measured speech window for ${s.scene}`);
    process.exit(1);
  }
  const trim = `atrim=0:${window.toFixed(2)}`;
  const fade = `afade=t=in:st=0:d=0.04,afade=t=out:st=${(window - 0.06).toFixed(2)}:d=0.06`;
  const delayMs = Math.round(speechStart * 1000);
  return `[${i}:a]${trim},${fade},adelay=${delayMs}|${delayMs},aformat=channel_layouts=stereo[v${i}]`;
});

const mixInputs = scenes.map((_, i) => `[v${i}]`).join("");
const final = `${mixInputs}amix=inputs=${scenes.length}:normalize=0:dropout_transition=0,loudnorm=I=${LUFS_TARGET}:TP=${TRUE_PEAK - 0.5}:LRA=11,apad=whole_dur=${DURATION}[out]`;

const filter = [...prepped, final].join(";");

const codec = output.endsWith(".wav") ? "-c:a pcm_s16le" : "-c:a aac -b:a 192k";
mkdirSync(resolve(output, ".."), { recursive: true });
const cmd = [
  "ffmpeg", "-y", "-v", "error",
  ...inputs.split(" "),
  "-filter_complex", `"${filter}"`,
  "-map", '"[out]"',
  "-t", String(DURATION),
  "-ar", "48000",
  ...codec.split(" "),
  output,
].join(" ");

run(cmd);

/* Verify */
const dur = run(`ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 ${output}`).toString().trim();
const stats = run(`ffmpeg -v info -i ${output} -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|LRA:|Peak:" | tail -3`).toString().trim();
console.log(`  Done! ${output} (${dur}s)`);
console.log(`  ${stats.replace(/\n/g, "\n  ")}`);
console.log("");
