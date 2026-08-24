#!/usr/bin/env node
/** Render one token-aligned Design template into registered channel sizes. */
import puppeteer from "puppeteer";
import { createServer } from "http";
import { existsSync, mkdirSync, readFileSync } from "fs";
import { join, resolve, extname } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const DESIGN_ROOT = join(ROOT, ".agents/company/departments/design");
const TEMPLATE = join(DESIGN_ROOT, "templates/social/harness-architecture.html");
const PRESETS_FILE = join(DESIGN_ROOT, "presets.json");
const OUTPUT_ROOT = join(ROOT, ".spielos/artifacts/design-showcase/graphics");
const CAMPAIGN_MANIFEST = process.env.CAMPAIGN_MANIFEST
  ? resolve(process.env.CAMPAIGN_MANIFEST) : null;
const CAMPAIGN_ITEM_ID = process.env.CAMPAIGN_ITEM_ID || "";
const MIME = { ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
  ".json": "application/json", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

/* ── Owner contract gate (shared with render-video.js --check): the
   narration spec must pin ONE voice with MEASURED scene timing for both
   scenarios, and must carry no music spec. A multi-voice, unmixed, or
   music-bearing spec fails the gate. ── */
function checkNarrationContract(failures) {
  const narrationPath = join(DESIGN_ROOT, "templates/video/narration.json");
  if (!existsSync(narrationPath)) { failures.push("narration.json missing"); return; }
  const narration = JSON.parse(readFileSync(narrationPath, "utf8"));
  const voice = narration.voice_selection;
  if (!voice) failures.push("narration.json: voice_selection empty — no pinned single voice");
  const mix = narration.mix || {};
  if (mix.music !== "none") failures.push(`narration.json: mix.music=${JSON.stringify(mix.music)} — voiced deliverables are narration-only (music must be "none")`);
  const raw = JSON.stringify(narration);
  for (const bad of ["music_direction", "music_duck_db", "music-ambient", "voice_audition", "audition_voices", "voice_candidates"]) {
    if (raw.includes(bad)) failures.push(`narration.json: music/audition remnant "${bad}"`);
  }
  const voices = new Set();
  for (const s of ["b", "c"]) {
    const st = narration.scene_timing?.[s];
    if (!st?.generated_at) { failures.push(`narration.json: scenario ${s} has no measured scene_timing — run scripts/tts-gemini.js first (speech first, then scenes)`); continue; }
    if (!st.voice || st.voice !== voice) failures.push(`narration.json: scenario ${s} scene_timing.voice=${st.voice} ≠ voice_selection=${voice} (mixed generations)`);
    voices.add(st.voice);
    const scenes = st.scenes || [];
    if (scenes.length < 4) { failures.push(`narration.json: scenario ${s} has ${scenes.length} scenes`); continue; }
    // narration-led-v2 (speech measured inside each scene, one narration-led
    // duration under 60s) or the legacy <=14.9s measured-window contract.
    const narrationLed = st.timing_contract === "narration-led-v2";
    let prev = -0.001;
    for (const sc of scenes) {
      const invalidBase = typeof sc.start !== "number" || typeof sc.end !== "number"
        || sc.start < prev || sc.end <= sc.start;
      const invalidNarrationLed = narrationLed && (typeof sc.speech_start !== "number"
        || typeof sc.speech_end !== "number" || sc.speech_start <= sc.start
        || sc.speech_end <= sc.speech_start || sc.end <= sc.speech_end);
      if (invalidBase || invalidNarrationLed) {
        failures.push(`narration.json: scenario ${s} scene ${sc.scene} window not measured/monotonic (${sc.start}→${sc.end})`);
        break;
      }
      const minimum = sc === scenes[scenes.length - 1] ? 4 : 3;
      if (narrationLed && sc.end - sc.start + 0.001 < minimum) {
        failures.push(`narration.json: scenario ${s} scene ${sc.scene} is shorter than the ${minimum}s readability minimum`);
        break;
      }
      prev = sc.start;
    }
    const last = scenes[scenes.length - 1];
    if (narrationLed && (!Number.isFinite(st.duration) || Math.abs(st.duration - last?.end) > 0.02 || st.duration >= 60)) {
      failures.push(`narration.json: scenario ${s} needs one narration-led duration under 60s matching its final scene`);
    } else if (!narrationLed && last && last.end > 14.9) {
      failures.push(`narration.json: scenario ${s} overruns 14.9s (${last.end}s) — tighten the TEXT, never cut speech`);
    }
  }
  if (voices.size > 1) failures.push(`narration.json: ${voices.size} different voices across scenarios (${[...voices].join(", ")}) — ONE voice required`);
}

function validateStatic(failures) {
  for (const file of [TEMPLATE, PRESETS_FILE, join(DESIGN_ROOT, "system/production.css")]) {
    if (!existsSync(file)) failures.push(`missing ${file}`);
  }
  if (failures.length) return;
  const html = readFileSync(TEMPLATE, "utf8");
  const css = readFileSync(join(DESIGN_ROOT, "system/production.css"), "utf8");
  if (!html.includes("production.css")) failures.push("template does not use the production design system");
  if (!html.includes("GOAL") || !html.includes("EVALUATE")) failures.push("template does not show the canonical loop");
  if (!html.includes("favicons/favicon.svg")) failures.push("template does not use the official tiled logo");
  if (!html.includes("signature-path")) failures.push("template does not use the journey-line signature");
  if (!html.includes("social-goal")) failures.push("template does not carry the goal bullseye");
  if (!html.includes("spielos.xyz")) failures.push("template does not show the canonical website");
  if (html.includes("Tools stay stable")) failures.push("template uses the retired Tool vocabulary");
  if (html.includes("batch-01.json")) failures.push("template is coupled to a hardcoded campaign batch");
  if (!html.includes("__applyCampaignRendition")) failures.push("template lacks the shared campaign rendition handoff");
  /* Canvas composition (owner contract №6): flat connected journey line +
     loop symbol + centered bold title — NOT a card-with-arrows layout. */
  if (!html.includes("canvas-title")) failures.push("template missing centered .canvas-title");
  if (!html.includes("loop-symbol")) failures.push("template missing the loop symbol");
  if (html.includes('class="loop"')) failures.push("template uses the retired card-with-arrows layout");
  if (!html.includes("non-scaling-stroke")) failures.push("journey line must keep constant stroke width in every aspect");
  if (/class="[^"]*\bcard\b[^"]*"/i.test(html)) failures.push("template contains card-class layout elements (card-with-arrows layout is rejected)");
  if (/music/i.test(html)) failures.push("template contains a music reference");
  if (/music/i.test(css)) failures.push("production CSS contains a music reference");
  if (!css.includes("src/styles/tokens/index.css")) failures.push("production CSS does not import canonical tokens");
  if (!css.includes('url("/public/assets/fonts/outfit-latin.woff2")')) failures.push("production CSS must load Outfit from repo-root-resolvable paths (no system-font fallback)");
  if (!css.includes("@font-face")) failures.push("production CSS must declare the website fonts itself for the render context");
  /* No second display font: every @font-face family must be a website family. */
  const faceFamilies = [...css.matchAll(/@font-face\s*\{[^}]*font-family\s*:\s*"([^"]+)"\s*;/g)].map((m) => m[1]);
  for (const fam of faceFamilies) {
    if (!["Outfit", "JetBrains Mono", "boxicons", "IRANSansX"].includes(fam)) failures.push(`production CSS declares unexpected display font family "${fam}" (website families only)`);
  }
  const presets = JSON.parse(readFileSync(PRESETS_FILE, "utf8"));
  if (Object.keys(presets).length < 6) failures.push("fewer than six channel presets");
}

/* In-render gate: the fonts, centered bold title, loop symbol, journey line,
   and stations must ACTUALLY render (not fall back, not empty). */
function checkFixture() {
  return { campaign_id: "contract-check", batch_id: "contract-check-batch", item_id: "contract-check-item",
    content_id: "contract-check-item-threads", design: {
      template_id: "harness-architecture", theme: "gruvbox-dark", surface: "background",
      color_role: "primary", alignment: "center", layout: "centered-journey",
      size_preset: "threads-portrait", eyebrow: "SpielOS campaign contract",
      title_lines: ["Context first.", "One clear idea."], accent_line: 1,
      supporting_text: "A render receives its title and hierarchy from one shared campaign Artifact.",
      station_labels: ["Strategy", "Design", "Publish", "Measure", "Decide"],
    } };
}

function campaignOrder(manifestPath, itemId) {
  if (!manifestPath || !itemId) {
    if (process.env.LEGACY_DESIGN_RENDER === "1") return checkFixture();
    throw new Error("Set CAMPAIGN_MANIFEST and CAMPAIGN_ITEM_ID to render a campaign asset");
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const item = (manifest.items || []).find((entry) => entry.item_id === itemId);
  if (!item) throw new Error(`Campaign item not found: ${itemId}`);
  const rendition = item.renditions?.threads;
  if (!rendition?.design) throw new Error(`Threads Design order missing for ${itemId}`);
  return { campaign_id: manifest.campaign_id, batch_id: manifest.batch_id, item_id: item.item_id,
    content_id: rendition.content_id, design: rendition.design };
}

async function applyOrder(page, order) {
  await page.waitForFunction(() => typeof window.__applyCampaignRendition === "function", { timeout: 8000 });
  await page.evaluate((value) => window.__applyCampaignRendition(value), order);
  await page.waitForFunction(() => document.documentElement.dataset.templateReady === "true", { timeout: 8000 });
}

async function renderGate(baseUrl, browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/.agents/company/departments/design/templates/social/harness-architecture.html`, { waitUntil: "networkidle0" });
  await applyOrder(page, checkFixture());
  await page.evaluate(() => document.fonts.ready);
  await new Promise((r) => setTimeout(r, 300));
  return page.evaluate(() => {
    const errs = [];
    if (!document.fonts.check("800 16px Outfit")) errs.push("Outfit 800 NOT loaded in render (system-font fallback)");
    const title = document.querySelector(".canvas-title");
    if (!title) errs.push("missing .canvas-title");
    else {
      const cs = getComputedStyle(title);
      if (!cs.fontFamily.includes("Outfit")) errs.push(`title font-family ${cs.fontFamily} (expected Outfit)`);
      if (cs.fontWeight !== "800") errs.push(`title font-weight ${cs.fontWeight} (expected 800)`);
      if (cs.textAlign !== "center") errs.push(`title text-align ${cs.textAlign} (expected center)`);
      const r = title.getBoundingClientRect();
      if (r.width < 120 || r.height < 20) errs.push("title has no visible box (empty render)");
      if (!title.textContent.trim()) errs.push("title has no text (background-only render)");
    }
    const loop = document.getElementById("loop-symbol");
    if (!loop) errs.push("missing #loop-symbol");
    else {
      const r = loop.getBoundingClientRect();
      if (r.width < 60 || r.height < 60) errs.push("loop symbol collapsed (not visible)");
    }
    const lines = [...document.querySelectorAll(".signature-path")].filter((p) => p.getTotalLength() > 40);
    if (lines.length < 1) errs.push("no connected journey line rendered (.signature-path)");
    const stations = document.querySelectorAll(".station");
    if (stations.length < 5) errs.push(`expected 5 journey stations, found ${stations.length}`);
    for (const st of stations) {
      const r = st.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) errs.push("journey station not visible (empty render)");
    }
    /* Every station MUST sit ON the journey line (contract №4/№6, canvas
       direction): map each node's rendered center back into the landscape
       signature path's viewBox space and measure the distance to the drawn
       line. The path is drawn THROUGH the station vertices, so any node more
       than 1.6 viewBox units away is off-line (a card/parallel layout). */
    const svg = document.querySelector(".journey-svg");
    const line = document.querySelector(".signature-path.landscape-path");
    if (svg && line && svg.getScreenCTM && stations.length) {
      const len = line.getTotalLength();
      const samples = [];
      for (let f = 0; f <= 240; f++) samples.push(line.getPointAtLength((f / 240) * len));
      const inv = svg.getScreenCTM().inverse();
      for (const st of stations) {
        const r = st.getBoundingClientRect();
        const pt = new DOMPoint(r.left + r.width / 2, r.top + r.height / 2).matrixTransform(inv);
        let min = Infinity;
        for (const s of samples) min = Math.min(min, Math.hypot(pt.x - s.x, pt.y - s.y));
        if (min > 1.6) errs.push(`station ${st.className.replace(/\s+/g, " ")} is ${min.toFixed(1)} viewBox units OFF the journey line`);
      }
    } else errs.push("could not verify stations against the journey line");
    return errs;
  });
}

function startServer() {
  return new Promise((done) => {
    const server = createServer((req, res) => {
      const path = join(ROOT, decodeURIComponent(req.url.split("?")[0]));
      let data;
      try { data = readFileSync(path); }
      catch { res.writeHead(404); res.end("Not found"); return; }
      res.writeHead(200, { "Content-Type": MIME[extname(path)] || "application/octet-stream" });
      res.end(data);
    });
    server.listen(0, "127.0.0.1", () => done({ server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

async function launch() {
  const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  return puppeteer.launch({ headless: "shell",
    ...(existsSync(systemChrome) ? { executablePath: systemChrome } : {}),
    args: ["--no-sandbox", "--font-render-hinting=none"] });
}

async function check() {
  const failures = [];
  validateStatic(failures);
  checkNarrationContract(failures);
  if (failures.length) { console.error(failures.join("\n")); process.exit(1); }
  console.log("Static design + narration contract OK (one voice, no music, measured timing)");
  const { server, base } = await startServer();
  let browser;
  try {
    browser = await launch();
    const errs = await renderGate(base, browser);
    if (errs.length) { console.error("In-render gate failures:\n" + errs.join("\n")); process.exit(1); }
  } finally {
    if (browser) await browser.close();
    server.close();
  }
  console.log("Design render gate OK: Outfit 800 centered title, flat canvas composition (journey line + loop symbol + on-line stations)");
  process.exit(0);
}

async function render() {
  const requested = process.argv[2] || "all";
  const output = resolve(process.argv[3] || OUTPUT_ROOT);
  const presets = JSON.parse(readFileSync(PRESETS_FILE, "utf8"));
  const selected = requested === "all" ? Object.entries(presets) : [[requested, presets[requested]]];
  if (selected.some(([, value]) => !value)) throw new Error(`Unknown preset: ${requested}`);
  mkdirSync(output, { recursive: true });
  const { server, base } = await startServer();
  const browser = await launch();
  const order = campaignOrder(CAMPAIGN_MANIFEST, CAMPAIGN_ITEM_ID);
  try {
    const page = await browser.newPage();
    for (const [name, size] of selected) {
      await page.setViewport({ ...size, deviceScaleFactor: 1 });
      await page.goto(`${base}/.agents/company/departments/design/templates/social/harness-architecture.html`, { waitUntil: "networkidle0" });
      await applyOrder(page, order);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(output, `${order.content_id}-${name}-${size.width}x${size.height}.png`) });
      console.log(`Rendered ${name} ${size.width}x${size.height}`);
    }
  } finally { await browser.close(); server.close(); }
}

if (process.argv[2] === "--check") {
  check().catch((e) => { console.error(e); process.exit(1); });
} else {
  render().catch((e) => { console.error(e); process.exit(1); });
}
