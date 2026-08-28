#!/usr/bin/env node
/**
 * tts-providers.js — Multi-provider TTS fallback chain for SpielOS narration.
 *
 * Owner contract (2026-08-12):
 *  - Deterministic provider order: Gemini (primary) → Mistral Voxtral
 *    (fallback 1, both keys with failover) → Cartesia (fallback 2) →
 *    ElevenLabs (fallback 3).
 *  - Every provider is pinned to a MASCULINE low-register voice matching the
 *    owner persona (pins below; exact voice ids are confirmed/discovered at
 *    generation time and recorded as provenance). The persona is ONE
 *    consistent voice across both scenarios — scripts/tts-gemini.js restarts
 *    a scenario from scratch on the next provider rather than ever switching
 *    voice mid-scenario.
 *  - On rate-limit/quota/auth/5xx failure: log provider + status, fall to the
 *    next provider, retry the same clip. Never silently drop a clip.
 *  - Keys are loaded ONLY from .spielos/.env (gitignored). This file never
 *    prints a key or a clip.
 *
 * CLI:
 *   node scripts/tts-providers.js --check  # exit 0: all 5 env keys present +
 *                                          # non-empty, chain order exact,
 *                                          # per-provider masculine voice
 *                                          # pinned; exit 1 otherwise.
 *                                          # Prints booleans only — no secrets.
 *   node scripts/tts-providers.js --list   # providers, models, voices
 *                                          # (no secrets, no network).
 *   node scripts/tts-providers.js --probe  # live diagnostic: synthesize one
 *                                          # short line through every provider
 *                                          # that has a key, into
 *                                          # .spielos/artifacts/audio/probe/;
 *                                          # reports chosen voices. Never used
 *                                          # for deliverables.
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync, statSync } from "fs";
import { join, resolve } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(fileURLToPath(new URL("../../../..", import.meta.url)));
const ENV_PATH = join(ROOT, ".spielos/.env");

/* ── Deterministic chain (owner contract) ──
   Order is fixed and enforced by --check; never reorder for convenience. */
export const CHAIN = ["gemini", "mistral", "cartesia", "elevenlabs"];

/* ── Per-provider masculine voice pins (persona: deep, low-register male,
   very confident, demanding, aggressive-but-friendly, casual). `voice` is the
   pinned first choice; `masculine_shortlist` is the ordered fallback shortlist
   used during runtime discovery when the API exposes voice metadata. Never
   empty: --check fails if any pin is missing. Pins verified against the live
   catalogs 2026-08-12: Mistral `en_paul_confident` (bold, punchy, confident),
   Cartesia `5ee9feff...` (intense, deep young adult male), ElevenLabs Adam
   (dominant, firm). ── */
export const VOICE_PINS = {
  gemini: {
    label: "Gemini 2.5 Flash TTS (primary)",
    envKeys: ["GEMINI_API_KEY"],
    base: "https://generativelanguage.googleapis.com/v1beta",
    model: "gemini-2.5-flash-preview-tts",
    voice: "Charon",
    masculine_shortlist: ["Charon"],
  },
  mistral: {
    label: "Mistral Voxtral (fallback 1)",
    envKeys: ["MISTRAL_API_KEY", "MISTRAL_API_KEY_2"],
    base: "https://api.mistral.ai/v1",
    model: "voxtral-mini-tts-latest", // confirmed live: voxtral-mini-tts-2603
    voice: "en_paul_confident", // confirmed live: bold, punchy, confident (male)
    masculine_shortlist: ["en_paul_confident", "en_paul_frustrated", "en_paul_angry", "en_paul_neutral", "gb_oliver_neutral"],
  },
  cartesia: {
    label: "Cartesia (fallback 2)",
    envKeys: ["CARTESIA_API_KEY"],
    base: "https://api.cartesia.ai",
    model: "sonic-2", // cheapest strong quality tier; sonic-english fallback
    voice: "5ee9feff-1265-424a-9d7f-8e4d431a12c7", // "Intense, deep young adult male" (confirmed live)
    masculine_shortlist: ["5ee9feff-1265-424a-9d7f-8e4d431a12c7", "ef191366-f52f-447a-a398-ed8c0f2943a1", "47c38ca4-5f35-497b-b1a3-415245fb35e1", "630ed21c-2c5c-41cf-9d82-10a7fd668370"],
  },
  elevenlabs: {
    label: "ElevenLabs (fallback 3)",
    envKeys: ["ELEVENLABS_API_KEY"],
    base: "https://api.elevenlabs.io/v1",
    model: "eleven_turbo_v2_5", // fast/cheap tier that still sounds strong
    voice: "pNInz6obpgDQGcFmaJgB", // Adam — Dominant, Firm (confirmed live)
    masculine_shortlist: ["pNInz6obpgDQGcFmaJgB", "IKne3meq5aSn9XLyUdCD", "nPczCjzI2devNBz1zQrb", "CwhRBWXzGAHq8TQ4Fs17"],
  },
};

/* ── Env loading (single source: .spielos/.env, gitignored) ── */
export function loadEnv() {
  const out = {};
  if (existsSync(ENV_PATH)) {
    for (const line of readFileSync(ENV_PATH, "utf8").split("\n")) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && m[2] !== undefined) out[m[1]] = m[2].trim();
    }
  }
  return out;
}

export function keyFor(providerId, env = loadEnv()) {
  const pins = VOICE_PINS[providerId];
  if (!pins) return null;
  for (const name of pins.envKeys) {
    if (env[name]) return { name, value: env[name] };
  }
  return null;
}

/** All five owner keys present and non-empty. */
export function allKeysPresent(env = loadEnv()) {
  const needed = ["GEMINI_API_KEY", "MISTRAL_API_KEY", "MISTRAL_API_KEY_2", "CARTESIA_API_KEY", "ELEVENLABS_API_KEY"];
  return needed.every((name) => !!env[name]);
}

export function chainOrderCorrect() {
  return JSON.stringify(CHAIN) === JSON.stringify(["gemini", "mistral", "cartesia", "elevenlabs"]);
}

export function voicesPinned() {
  return CHAIN.every((id) => {
    const p = VOICE_PINS[id];
    return p && typeof p.voice === "string" && p.voice.trim().length > 0 &&
      Array.isArray(p.masculine_shortlist) && p.masculine_shortlist.length > 0;
  });
}

/* ── Small helpers ── */
async function httpJson(url, { headers = {}, method = "GET", body } = {}) {
  const res = await fetch(url, {
    method,
    headers: { Accept: "application/json", ...headers },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { json = null; }
  return { status: res.status, ok: res.ok, json, text };
}

async function httpBytes(url, { headers = {}, method = "POST", body } = {}) {
  const res = await fetch(url, {
    method,
    headers: { Accept: "audio/*", ...headers },
    ...(body ? { body: typeof body === "string" ? body : JSON.stringify(body) } : {}),
  });
  const buf = Buffer.from(await res.arrayBuffer());
  return { status: res.status, ok: res.ok, buf, headers: res.headers };
}

function identify(meta) {
  const primary = (meta && typeof meta.gender === "string") ? meta.gender.toLowerCase() : "";
  const labels = JSON.stringify(meta || {}).toLowerCase();
  const keyboard = /(male|man |masculine|deep|low|baritone)/.test(labels);
  return { male: keyboard || primary === "male" || primary === "man", labels };
}

/* ── Runtime voice discovery (cached per session) ── */
const voiceCache = {};

async function discoverMistral(env) {
  const key = keyFor("mistral", env);
  if (!key) return { ok: false, reason: "no mistral key" };
  const h = { Authorization: `Bearer ${key.value}` };
  // 1) confirm the Voxtral TTS model (pin is already verified: voxtral-mini-tts-latest)
  let model = VOICE_PINS.mistral.model;
  try {
    const r = await httpJson(`${VOICE_PINS.mistral.base}/models`, { headers: h });
    if (r.ok && Array.isArray(r.json?.data)) {
      const ttsModels = r.json.data.map((m) => m.id).filter((id) => /voxtral.*tts|^tts/i.test(id));
      if (ttsModels.length) model = ttsModels.includes("voxtral-mini-tts-latest") ? "voxtral-mini-tts-latest" : ttsModels[0];
    }
  } catch { /* keep pin */ }
  // 2) list preset voices (confirmed route: /audio/voices)
  let voices = [];
  try {
    const r = await httpJson(`${VOICE_PINS.mistral.base}/audio/voices`, { headers: h });
    if (r.ok && Array.isArray(r.json?.items)) voices = r.json.items;
  } catch { voices = []; }
  const shortlist = VOICE_PINS.mistral.masculine_shortlist;
  let voice = null;
  // shortlist is ORDERED (pinned first choice wins when present): iterate the
  // shortlist, not the API list order, or a cheerful catalog-first voice could
  // shadow the pinned persona.
  const catalog = new Set(voices.map((v) => v.slug || v.id || v.name).filter(Boolean));
  for (const slug of shortlist) {
    if (catalog.has(slug)) { voice = slug; break; }
  }
  if (!voice) {
    for (const v of voices) {
      const slug = v.slug || v.id || v.name;
      if (slug && (v.gender === "male" || identify(v).male) && /confident|bold|punchy|gruff/i.test(JSON.stringify(v.tags || ""))) { voice = slug; break; }
    }
  }
  if (!voice) {
    for (const v of voices) {
      const slug = v.slug || v.id || v.name;
      if (slug && (v.gender === "male" || identify(v).male)) { voice = slug; break; }
    }
  }
  if (!voice) voice = shortlist[0]; // pinned candidate fallback
  return { ok: Boolean(model && voice), model, voice, keyName: key.name, reason: model && voice ? "ok" : "no voxtral model/voice" };
}

async function discoverCartesia(env) {
  const key = keyFor("cartesia", env);
  if (!key) return { ok: false, reason: "no cartesia key" };
  const h = { "X-API-Key": key.value };
  let voices = [];
  try {
    const r = await httpJson(`${VOICE_PINS.cartesia.base}/voices`, { headers: h });
    if (r.ok && Array.isArray(r.json?.data)) voices = r.json.data;
    else if (r.ok && Array.isArray(r.json)) voices = r.json;
    else if (r.ok && Array.isArray(r.json?.voices)) voices = r.json.voices;
  } catch { voices = []; }
  const shortlist = VOICE_PINS.cartesia.masculine_shortlist;
  let voice = null;
  // shortlist is ORDERED (pinned first choice wins when present): iterate the
  // shortlist, not the API list order, or a cheerful catalog-first voice could
  // shadow the pinned deep-male persona.
  const catalog = new Set(voices.map((v) => v.id || v.voice_id || v.name).filter(Boolean));
  for (const id of shortlist) {
    if (catalog.has(id)) { voice = id; break; }
  }
  if (!voice) {
    // persona match: deep / intense / confident masculine descriptions first
    for (const v of voices) {
      const desc = String(v.description || "");
      if (/intense|deep|confident/i.test(desc) && /male|man/i.test(desc)) { voice = v.id || v.voice_id || v.name; break; }
    }
  }
  if (!voice) {
    for (const v of voices) {
      const id = v.id || v.voice_id || v.name;
      if (id && identify(v).male) { voice = id; break; }
    }
  }
  if (!voice) voice = shortlist[0];
  // cheapest strong model tier: sonic-2 pinned (no /models route on the hosted
  // API — confirmed 404, so keep the pin and fall back only on synth 4xx)
  const model = VOICE_PINS.cartesia.model;
  return { ok: Boolean(voice && model), model, voice, keyName: key.name, reason: voice ? "ok" : "no voices listed" };
}

async function discoverElevenLabs(env) {
  const key = keyFor("elevenlabs", env);
  if (!key) return { ok: false, reason: "no elevenlabs key" };
  /* NOTE: the token must be sent as `X-Api-Key` — the key is a full API key
     and `xi-api-key` misreads it as a key ID (400 invalid_api_key). */
  const h = { "X-Api-Key": key.value };
  let voices = [];
  try {
    const r = await httpJson(`${VOICE_PINS.elevenlabs.base}/voices`, { headers: h });
    if (r.ok && Array.isArray(r.json?.voices)) voices = r.json.voices;
  } catch { voices = []; }
  const shortlist = VOICE_PINS.elevenlabs.masculine_shortlist;
  const shortNames = ["adam", "charlie", "brian", "roger"];
  let voice = null;
  // shortlist is ORDERED (pinned first choice wins when present): iterate the
  // shortlist, not the API list order, so the pinned Adam persona is kept.
  const catalog = new Set(voices.map((v) => v.voice_id).filter(Boolean));
  for (const id of shortlist) {
    if (catalog.has(id)) { voice = id; break; }
  }
  if (!voice) {
    for (const v of voices) {
      const name = String(v.name || "").toLowerCase();
      if (shortNames.some((n) => name.startsWith(n)) && /male/i.test((v.labels || {}).gender || "")) { voice = v.voice_id; break; }
    }
  }
  if (!voice) {
    for (const v of voices) {
      if (identify(v.labels || v).male) { voice = v.voice_id; break; }
    }
  }
  if (!voice) voice = null; // no masculine voice → caller treats provider as unavailable
  return { ok: Boolean(voice), model: VOICE_PINS.elevenlabs.model, voice, keyName: key.name, reason: voice ? "ok" : "no masculine voice found" };
}

export async function discoverVoices(providerId, env = loadEnv()) {
  if (voiceCache[providerId]) return voiceCache[providerId];
  let result;
  if (providerId === "mistral") result = await discoverMistral(env);
  else if (providerId === "cartesia") result = await discoverCartesia(env);
  else if (providerId === "elevenlabs") result = await discoverElevenLabs(env);
  else {
    const pin = VOICE_PINS.gemini;
    result = { ok: Boolean(keyFor("gemini", env)), model: pin.model, voice: pin.voice, keyName: "GEMINI_API_KEY", reason: "pinned" };
  }
  voiceCache[providerId] = result;
  return result;
}

/* ── Synthesis: writes raw provider audio to outFile; returns provenance. ── */
async function synthGemini(key, pin, { text, outFile }) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${pin.model}:generateContent?key=${key.value}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ["AUDIO"],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: pin.voice } } },
        },
      }),
    }
  );
  if (!res.ok) throw new ProviderError("gemini", res.status, (await res.text()).slice(0, 200));
  const data = await res.json();
  const part = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
  if (!part?.inlineData?.data) throw new ProviderError("gemini", 0, "no audio in Gemini response");
  const mime = part.inlineData.mimeType || "audio/wav";
  const started = Buffer.from(part.inlineData.data, "base64");
  const isRawPcm = mime.includes("L16") || mime.includes("pcm");
  writeFileSync(outFile, started);
  return { provider: "gemini", voice: pin.voice, mime, isRawPcm, sampleRate: Number(mime.match(/rate=(\d+)/)?.[1] || "24000"), status: 200 };
}

async function synthMistral(key, discovered, { text, outFile }) {
  if (!key) throw new ProviderError("mistral", 0, "no mistral key");
  if (!discovered.ok) throw new ProviderError("mistral", 0, `voice discovery failed: ${discovered.reason}`);
  const base = VOICE_PINS.mistral.base;
  const h = { Authorization: `Bearer ${key.value}`, "Content-Type": "application/json" };
  /* Confirmed live (2026-08-12): POST /v1/audio/speech with {model, input,
     voice (preset slug), response_format:"wav"}. sample_rate is NOT a valid
     body field (422 extra_forbidden); wav returns 200 application/json with
     {audio_data: base64}. */
  const body = {
    model: discovered.model,
    input: text,
    voice: discovered.voice,
    response_format: "wav",
  };
  const r = await httpBytes(`${base}/audio/speech`, { headers: h, body });
  if (r.ok && r.buf.length > 44) {
    /* Response is either raw audio bytes or JSON {audio_data: base64}. */
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("application/json")) {
      let data = null;
      try { data = JSON.parse(r.buf.toString("utf8")); } catch { data = null; }
      if (data?.audio_data) {
        writeFileSync(outFile, Buffer.from(data.audio_data, "base64"));
        return { provider: "mistral", voice: discovered.voice, model: discovered.model, mime: "audio/wav", isRawPcm: false, status: 200 };
      }
      throw new ProviderError("mistral", 200, "JSON response without audio_data");
    }
    writeFileSync(outFile, r.buf);
    return { provider: "mistral", voice: discovered.voice, model: discovered.model, mime: "audio/wav", isRawPcm: false, status: r.status };
  }
  throw new ProviderError("mistral", r.status, "no usable TTS response");
}

async function synthCartesia(key, discovered, { text, outFile }) {
  if (!key) throw new ProviderError("cartesia", 0, "no cartesia key");
  if (!discovered.ok) throw new ProviderError("cartesia", 0, `voice discovery failed: ${discovered.reason}`);
  const h = { "X-API-Key": key.value, "Cartesia-Version": "2024-06-10", "Content-Type": "application/json" };
  const body = {
    transcript: text,
    model_id: discovered.model,
    voice: { mode: "id", id: discovered.voice },
    output_format: { container: "wav", encoding: "pcm_s16le", sample_rate: 44100 },
    language: "en",
  };
  let r = await httpBytes(`${VOICE_PINS.cartesia.base}/tts/bytes`, { headers: h, body });
  if (!r.ok && discovered.model === "sonic-2") {
    // cheapest strong tier rejected — retry with the proven sonic-english tier
    const fb = { ...body, model_id: "sonic-english" };
    r = await httpBytes(`${VOICE_PINS.cartesia.base}/tts/bytes`, { headers: h, body: fb });
  }
  if (!r.ok || r.buf.length <= 44) throw new ProviderError("cartesia", r.status, "no usable audio from Cartesia");
  writeFileSync(outFile, r.buf);
  return { provider: "cartesia", voice: discovered.voice, model: discovered.model === "sonic-2" && r.status !== 200 ? "sonic-english" : discovered.model, mime: "audio/wav", isRawPcm: false, status: r.status };
}

async function synthElevenLabs(key, discovered, { text, outFile }) {
  if (!key) throw new ProviderError("elevenlabs", 0, "no elevenlabs key");
  if (!discovered.ok || !discovered.voice) throw new ProviderError("elevenlabs", 0, `voice discovery failed: ${discovered.reason}`);
  const body = { text, model_id: discovered.model };
  let headers = { "xi-api-key": key.value, "Content-Type": "application/json" };
  let r = await httpBytes(`${VOICE_PINS.elevenlabs.base}/text-to-speech/${discovered.voice}?output_format=pcm_44100`, { headers, body });
  if (r.status === 401 || r.status === 400) {
    /* Auth-header fallback: some API surfaces read X-Api-Key instead. */
    headers = { "X-Api-Key": key.value, "Content-Type": "application/json" };
    r = await httpBytes(`${VOICE_PINS.elevenlabs.base}/text-to-speech/${discovered.voice}?output_format=pcm_44100`, { headers, body });
  }
  if (!r.ok || r.buf.length <= 44) {
    const detail = r.buf.length ? r.buf.toString("utf8").slice(0, 140) : "";
    throw new ProviderError("elevenlabs", r.status, detail || "no usable audio from ElevenLabs");
  }
  writeFileSync(outFile, r.buf);
  return { provider: "elevenlabs", voice: discovered.voice, model: discovered.model, mime: "audio/wav", isRawPcm: false, status: r.status };
}

export class ProviderError extends Error {
  constructor(provider, status, detail) {
    super(`${provider} :: ${status} :: ${detail}`);
    this.provider = provider;
    this.status = status;
  }
}

export const TRANSIENT_STATUSES = new Set([429, 500, 502, 503, 504]);

/** Synthesize one line with one provider; throws ProviderError on failure. */
export async function synthesize(providerId, { text, outFile, env = loadEnv() }) {
  const pin = VOICE_PINS[providerId];
  if (!pin) throw new ProviderError(providerId, 0, `unknown provider`);
  const key = keyFor(providerId, env);
  if (!key) throw new ProviderError(providerId, 0, `missing ${pin.envKeys.join("/")} in .spielos/.env`);
  const discovered = await discoverVoices(providerId, env);
  if (!discovered.ok) throw new ProviderError(providerId, 0, `discovery failed: ${discovered.reason}`);
  if (providerId === "gemini") return synthGemini(key, pin, { text, outFile });
  if (providerId === "mistral") return synthMistral(key, discovered, { text, outFile });
  if (providerId === "cartesia") return synthCartesia(key, discovered, { text, outFile });
  if (providerId === "elevenlabs") return synthElevenLabs(key, discovered, { text, outFile });
  throw new ProviderError(providerId, 0, "unknown provider");
}

export function clearDiscoveryCache() { for (const k of Object.keys(voiceCache)) delete voiceCache[k]; }

/* ═══ CLI ═══ */
function runCheck() {
  const env = loadEnv();
  const keys = {
    gemini: !!env.GEMINI_API_KEY,
    mistral: !!env.MISTRAL_API_KEY,
    mistral_2: !!env.MISTRAL_API_KEY_2,
    cartesia: !!env.CARTESIA_API_KEY,
    elevenlabs: !!env.ELEVENLABS_API_KEY,
  };
  const order = chainOrderCorrect();
  const voices = voicesPinned();
  const ok = Object.values(keys).every(Boolean) && order && voices;
  console.log(`tts-providers --check`);
  console.log(`  keys         gemini=${keys.gemini} mistral=${keys.mistral} mistral_2=${keys.mistral_2} cartesia=${keys.cartesia} elevenlabs=${keys.elevenlabs}`);
  console.log(`  chain_order  ${order} (${CHAIN.join(" -> ")})`);
  console.log(`  voices_pinned ${voices}`);
  console.log(ok ? "  RESULT: exit 0 (all five keys, chain order, masculine voice pins)" : "  RESULT: exit 1");
  process.exit(ok ? 0 : 1);
}

function runList() {
  console.log(`tts-providers --list (no secrets)`);
  for (const id of CHAIN) {
    const p = VOICE_PINS[id];
    const keys = p.envKeys.map((k) => `${k}(set=${!!loadEnv()[k]})`).join(", ");
    console.log(`  ${id.padEnd(10)} ${p.label}`);
    console.log(`    model ${p.model || "(discovered at runtime)"} · pinned voice ${p.voice || "(discovered at runtime)"} · masculine shortlist [${p.masculine_shortlist.join(", ")}]`);
    console.log(`    env   ${keys}`);
  }
}

async function runProbe() {
  const env = loadEnv();
  const outDir = join(ROOT, ".spielos/artifacts/audio/probe");
  mkdirSync(outDir, { recursive: true });
  console.log(`tts-providers --probe (diagnostic only; never used for deliverables)`);
  for (const id of CHAIN) {
    const key = keyFor(id, env);
    if (!key) { console.log(`  ${id}: SKIPPED (no key)`); continue; }
    const outFile = join(outDir, `probe-${id}.bin`);
    try {
      const r = await synthesize(id, {
        text: "SpielOS. One system. The work runs itself.",
        outFile,
        env,
      });
      const bytes = statSync(outFile).size;
      console.log(`  ${id}: OK  voice=${r.voice} model=${r.model} status=${r.status} bytes=${bytes}`);
    } catch (e) {
      console.log(`  ${id}: FAIL ${e.message.slice(0, 160)}`);
    }
  }
}

/* Dispatch only when this file is the entry module: consumers (tts-gemini.js)
   import these exports and must not be killed by the CLI usage exit. */
const isMainModule = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMainModule) {
  const arg = process.argv[2];
  if (arg === "--check") runCheck();
  else if (arg === "--list") runList();
  else if (arg === "--probe") runProbe().catch((e) => { console.error(e); process.exit(1); });
  else {
    console.error("Usage: node scripts/tts-providers.js --check | --list | --probe");
    process.exit(1);
  }
}
