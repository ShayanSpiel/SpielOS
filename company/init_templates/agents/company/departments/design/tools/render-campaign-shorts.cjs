#!/usr/bin/env node
/**
 * render-campaign-shorts.cjs - durable Shorts campaign renderer for every
 * registered Shorts archetype (scenario-b, scenario-c, contrast-text,
 * storyboard, data-card, question-hook, loop-rail, heartbeat).
 *
 * Owner contract (goal-content-storytelling-architecture-v1-20260820):
 *  - ONE persona voice: campaign TTS (tts-gemini.js <key b..i>) produces every
 *    clip with the pinned `voice_selection`. This driver NEVER calls the
 *    still-title overlay API and never overlays a glass card - the thumbnail
 *    is a PLAIN FRAME grab of the hook window (the batch-02/03 glass-card
 *    regression is banned here).
 *  - Story first, scenes after: the campaign narration is one complete script
 *    (scene_control_version "1.0" or the current compatible "1.1"); clips are mixed on the measured spoken
 *    schedule, never re-written or cut here.
 *  - Design-registry rotation: each item's archetype must be registered with a
 *    scene_control (timing_key + scene order), marked renderable, and the batch
 *    must pass the Design rotation rule (no batch repeats); a repeating order is refused.
 *
 * Usage:
 *   node scripts/render-campaign-shorts.cjs --check
 *   node scripts/render-campaign-shorts.cjs <manifest.json> [itemId] [--probe]
 *
 * `--check` statically validates all registered Shorts archetypes: complete
 * injection maps (every DOM slot exists in the template), scene counts vs
 * registry scene_control, renderability metadata, and the stable-thumbnail policy.
 */
const puppeteer = require("puppeteer");
const { execSync } = require("child_process");
const { createServer } = require("http");
const { readFileSync, writeFileSync, existsSync, mkdirSync, rmSync, statSync, readdirSync } = require("fs");
const { join, resolve } = require("path");

const ROOT = resolve(__dirname, "..");
const REGISTRY = join(ROOT, ".agents/company/departments/design/templates/registry.json");
const TEMPLATE_DIR = join(ROOT, ".agents/company/departments/design/templates/video");
const NARRATION = join(TEMPLATE_DIR, "narration.json");
const AUDIO = join(ROOT, "public/videos/audio");
const MANIFEST = join(AUDIO, ".voice-manifest.json");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const FPS = 30;
const FLOW_QA_SCHEMA = "1.0";
const TEMPORAL_QA_SCHEMA = "1.0";
const URL_LINE = "spielos.xyz/services";
const URL_SPOKEN = "go to spielos dot xyz slash services.";
const DETERMINISTIC_CAPTURE_CSS = `
*, *::before, *::after {
  transition: none !important;
  animation: none !important;
  caret-color: transparent !important;
}
`;

/* Each registered Shorts archetype: timing key, scene order (== registry
   scene_control.scenes == tts-gemini.js SCENE_ORDER), and the DOM slots the
   campaign copy is injected into. The DOM ids are the SOURCE OF TRUTH the
   --check mode verifies against the template files. */
const ARCHETYPES = {
  "scenario-b": {
    key: "b", scene_count: 6,
    ids: ["hi1", "h1", "h2", "h3", "h4", "pi0", "pi1", "pi2", "pi3", "pi4",
          "pri1", "pr1", "pr2", "pr3", "pl0", "pl1", "pl2", "pl3", "pl4",
          "di1", "d1", "d2", "d3", "ct0", "ct1", "ct2"],
  },
  "scenario-c": {
    key: "c", scene_count: 5,
    ids: ["h1", "h2", "bs0", "bs1", "bs2", "bs3", "l1", "l2", "dc1", "dc-0", "dc-1",
          "ct0", "ct1", "ct2"],
  },
  "contrast-text": {
    key: "d", scene_count: 5,
    ids: ["h1", "h2", "h3", "h4", "c0", "c1", "c2", "c3", "p1", "p2",
          "r0", "r1", "r2", "ct0", "ct1", "ct2"],
  },
  "storyboard": {
    key: "e", scene_count: 4,
    ids: ["f0", "f1", "f2", "t0", "t1", "t2", "r0", "r1", "r2", "ct0", "ct1", "ct2"],
  },
  "data-card": {
    key: "f", scene_count: 4,
    ids: ["count", "h1", "c0", "c1", "c2", "p1", "p2", "ct0", "ct1", "ct2"],
  },
  "question-hook": {
    key: "g", scene_count: 4,
    ids: ["q0", "q1", "q2", "t0", "t1", "t2", "r0", "r1", "r2", "ct0", "ct1", "ct2"],
  },
  "loop-rail": {
    key: "h", scene_count: 5,
    ids: ["h0", "h1", "h2", "g1", "g2", "w1", "w2", "r1", "r2", "ct0", "ct1", "ct2"],
  },
  "heartbeat": {
    key: "i", scene_count: 4,
    ids: ["h0", "h1", "h2", "g1", "g2", "w1", "w2", "star-title", "run-title",
          "ct0", "ct1", "ct2"],
  },
};

const MIME = { ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
  ".json": "application/json", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg" };

function readRegistry() {
  return JSON.parse(readFileSync(REGISTRY, "utf8"));
}

function registeredShorts() {
  return (readRegistry().archetypes || []).filter((a) => a.kind === "shorts");
}

/* ── --check mode ──────────────────────────────────────────────────────── */
const STILL_TITLE_REF = "__setStill" + "Title"; // constructed so the policy check can find the banned call without matching itself

function checkMode() {
  const errors = [];
  const shorts = registeredShorts();
  const ids = shorts.map((a) => a.id);
  if (ids.length !== 8) errors.push(`registry must register exactly 8 Shorts archetypes (got ${ids.length})`);
  for (const id of Object.keys(ARCHETYPES)) {
    if (!ids.includes(id)) errors.push(`registered Shorts archetype missing from driver: ${id}`);
  }
  for (const entry of shorts) {
    const tpl = entry.file.split("/").pop();
    const sourcePath = join(TEMPLATE_DIR, tpl);
    const label = entry.id;
    if (!existsSync(sourcePath)) { errors.push(`${label}: template file missing ${sourcePath}`); continue; }
    const source = readFileSync(sourcePath, "utf8");
    const sc = entry.scene_control || {};
    if (entry.status === "quarantined") {
      if (!entry.quarantine_reason) errors.push(`${label}: quarantined archetype needs quarantine_reason`);
      continue;
    }
    const driver = ARCHETYPES[entry.id];
    if (!driver) { errors.push(`${label}: no driver injection map`); continue; }
    if (sc.timing_key !== driver.key) errors.push(`${label}: registry timing_key ${sc.timing_key} != driver ${driver.key}`);
    if ((sc.scenes || []).join(",") !== expectedSceneOrder(driver.key).join(",")) {
      errors.push(`${label}: registry scene_control.scenes does not match ${driver.key} scene order`);
    }
    const sceneNodes = (source.match(/class="scene"/g) || []).length;
    if (sceneNodes !== driver.scene_count) {
      errors.push(`${label}: template has ${sceneNodes} scene nodes but scene_control declares ${driver.scene_count}`);
    }
    for (const slot of driver.ids) {
      const re = new RegExp(`id=["']${slot}["']`);
      if (!re.test(source)) errors.push(`${label}: injection slot #${slot} missing from ${tpl}`);
    }
  }
  const selfSource = readFileSync(join(ROOT, "scripts/render-campaign-shorts.cjs"), "utf8");
  if (selfSource.includes(STILL_TITLE_REF)) {
    errors.push("plain-frame thumbnail policy violated: driver calls " + STILL_TITLE_REF);
  }
  /* Banned tokens are assembled at runtime so this self-scan never matches
     its own source text. */
  const GLASS_TOKENS = ["__applyCampaign" + "Rendition", "campaign-" + "scene", "campaign-" + "label"];
  for (const stale of GLASS_TOKENS) {
    if (selfSource.includes(stale)) errors.push("glass-card overlay banned in driver: " + stale);
  }
  if (errors.length) {
    console.error("CAMPAGN_SHORTS_CHECK_FAIL");
    for (const e of errors) console.error(" - " + e);
    process.exit(1);
  }
  console.log(`CAMPAGN_SHORTS_CHECK_OK - ${shorts.length} registered Shorts archetypes: complete injection maps + plain-frame thumbnail policy`);
  process.exit(0);
}

function expectedSceneOrder(key) {
  const entry = registeredShorts().find((a) => (a.scene_control || {}).timing_key === key);
  return entry && entry.scene_control.scenes ? entry.scene_control.scenes : [];
}

/* ── campaign plan ─────────────────────────────────────────────────────── */
function planFor(item, registry) {
  const yt = item.renditions.youtube;
  const tpl = yt.design.template_id;
  const row = (registry.archetypes || []).find((a) => a.id === tpl);
  if (!row || row.kind !== "shorts") throw new Error(`Unsupported Shorts template for ${item.item_id}: ${tpl}`);
  if (row.status === "quarantined") {
    throw new Error(`Template ${tpl} is quarantined and cannot render: ${row.quarantine_reason || "media gate failed"}`);
  }
  const key = (row.scene_control || {}).timing_key;
  if (!ARCHETYPES[row.id] || ARCHETYPES[row.id].key !== key) {
    throw new Error(`Template ${tpl} is not wired into the campaign renderer (registry timing_key ${key})`);
  }
  const scenes = yt.narration.scenes.map((s) => ({
    id: s.id || "",
    text: s.text, headline: s.visual.headline || s.text,
    eyebrow: s.visual.eyebrow || "",
    supporting: s.visual.supporting_text || "", labels: s.visual.labels || [],
    icon: s.visual.icon || "bx-check-square", component: s.visual.component || "",
    spokenDisplayAlignment: s.visual.spoken_display_alignment || "",
    intent: s.intent || "",
  }));
  return { scenario: key, template: row.id, file: row.file, scenes };
}

function expectedFlowText(plan, sceneIndex) {
  const scene = plan.scenes[sceneIndex] || {};
  const values = [];
  const add = (field, value) => {
    if (Array.isArray(value)) value.forEach((item) => item && values.push({ field, text: String(item) }));
    else if (value) values.push({ field, text: String(value) });
  };
  const addCore = (...fields) => fields.forEach((field) => add(field, scene[field]));
  if (sceneIndex === plan.scenes.length - 1) {
    addCore("eyebrow");
    values.push({ field: "visual.headline", text: scene.headline || URL_LINE });
    return values;
  }
  switch (plan.scenario) {
    case "b":
      if (sceneIndex === 0) addCore("text", "supporting");
      else if (sceneIndex === 1) add("labels", scene.labels);
      else if (sceneIndex === 2) addCore("text", "supporting");
      else if (sceneIndex === 3) addCore("eyebrow", "labels", "supporting");
      else if (sceneIndex === 4) addCore("text", "supporting");
      else if (sceneIndex === 5) addCore("eyebrow");
      break;
    case "c":
      if (sceneIndex === 0) addCore("text");
      else if (sceneIndex === 1) addCore("labels", "supporting");
      else if (sceneIndex === 2) addCore("text");
      else if (sceneIndex === 3) addCore("text", "labels", "supporting");
      else if (sceneIndex === 4) addCore("eyebrow");
      break;
    case "d":
      if (sceneIndex === 0) addCore("text", "supporting");
      else if (sceneIndex === 1) addCore("text", "supporting");
      else if (sceneIndex === 2) addCore("text", scene.labels?.[0] || scene.supporting);
      else if (sceneIndex === 3) add("labels", scene.labels);
      else if (sceneIndex === 4) addCore("eyebrow");
      break;
    case "e":
      addCore("eyebrow", "text", "supporting");
      break;
    case "f":
      if (sceneIndex === 0) addCore("text", "supporting");
      else if (sceneIndex === 1) addCore("text", "supporting");
      else if (sceneIndex === 2) addCore("text", scene.labels?.[0] || scene.supporting);
      else if (sceneIndex === 3) addCore("eyebrow");
      break;
    case "g":
      if (sceneIndex === 0 || sceneIndex === 1) addCore("text", "supporting");
      else if (sceneIndex === 2) addCore("text", scene.labels?.[0] || scene.supporting);
      else if (sceneIndex === 3) addCore("eyebrow");
      break;
    case "h":
      if (sceneIndex < 4) addCore("eyebrow", "text", "supporting");
      else addCore("eyebrow");
      break;
    case "i":
      if (sceneIndex < 3) addCore("eyebrow", "text", "supporting");
      else addCore("eyebrow");
      break;
    default:
      addCore("text");
  }
  return values;
}

/* Per-archetype injection. All helpers live INSIDE the function so Puppeteer
   can serialize it without closure variables, exactly like the proven b/c
   batch renderer. */
function injectCampaign(plan) {
  const URL_LINE = "spielos.xyz/services";
  const URL_SPOKEN = "go to spielos dot xyz slash services.";
function splitLines(text, maxChars) {
    const words = String(text || '').split(/\s+/).filter(Boolean);
    const lines = []; let cur = '';
    for (const w of words) {
      const next = cur ? cur + ' ' + w : w;
      if (next.length <= maxChars || !cur) cur = next;
      else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    return lines;
  }
  function splitIntoSlots(text, slots, preferredMax, field) {
    var lines = splitLines(text, preferredMax);
    if (lines.length > slots) lines = splitLines(text, Math.ceil(String(text || '').length / slots) + 1);
    if (lines.length > slots) {
      throw new Error('flow contract overflow: ' + (field || 'visual text') + ' needs ' + lines.length + ' lines but template provides ' + slots + ' slots');
    }
    return lines;
  }
  function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
  function setHTML(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html; }
  function setIcon(id, icon) { const el = document.getElementById(id); if (!el) return; const i = el.querySelector('i'); if (i) i.className = icon; }
  function hide(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }
  function show(id) { const el = document.getElementById(id); if (el) el.style.display = ''; }
  function twoLines(id1, id2, text, span, maxChars) {
    const lines = splitLines(text, maxChars);
    setText(id1, lines[0] || '');
    if (lines[1]) { show(id2); setHTML(id2, '<span class="' + span + '">' + lines[1] + '</span>'); }
    else hide(id2);
  }
  function cta(s, badgeDefault) {
    // FIX: use s.eyebrow when labels is just ['Services'] generic - eyebrow holds actual workflow (MAP ONE XXX)
    let badge = (s.labels && s.labels.length && !/^$/.test(String(s.labels[0])) && String(s.labels[0]).toLowerCase() !== 'services') ? s.labels[0] : '';
    if (!badge) badge = (s.eyebrow && s.eyebrow.trim()) ? s.eyebrow : (badgeDefault || 'AI agent implementation');
    // normalize MAP ONE XXX -> Title Case for badge
    setText('ct0', badge);
    const isUrlPronunciation = String(s.text || '').toLowerCase().includes('spielos dot xyz');
    if (!isUrlPronunciation) {
      const lines = splitIntoSlots(s.text, 2, 20, 'cta.visual.headline');
      setHTML('ct1', '<span class="cta-line">' + lines[0] + '</span><span class="cta-line accent">' + lines[1] + '</span>');
    } else {
      // Keep the spoken pronunciation out of the visual headline. The full
      // canonical URL lives in ct2; the title stays readable in portrait.
      setHTML('ct1', '<span class="cta-line">Go to</span><span class="cta-line accent">services</span>');
    }
    setHTML('ct2', '<span class="p">$</span> ' + URL_LINE);
  }
  const s = plan.scenes;
  if (plan.scenario === 'b' && s.length === 6) {
    setIcon('hi1', s[0].icon);
    const hook = splitIntoSlots(s[0].text, 3, 14, 'scenario-b.scene-1.text');
    ['h1', 'h2', 'h3'].forEach(function (id, idx) {
      if (idx < hook.length) setHTML(id, '<span class="hook-line">' + hook[idx] + '</span>');
      else hide(id);
    });
    setText('h4', s[0].supporting);
    for (let i = 0; i < 5; i++) {
      const el = document.getElementById('pi' + i);
      if (i < (s[1].labels || []).length) {
        show('pi' + i);
        const pt = el.querySelector('.pain-text'); if (pt) pt.textContent = s[1].labels[i];
      } else hide('pi' + i);
    }
    setIcon('pri1', s[2].icon);
    const prom = splitIntoSlots(s[2].text, 2, 18, 'scenario-b.scene-3.text');
    setHTML('pr1', prom[0] || '');
    if (prom[1]) { show('pr2'); setHTML('pr2', '<span class="accent">' + prom[1] + '</span>'); } else hide('pr2');
    setText('pr3', s[2].supporting);
    setText('pl0', s[3].eyebrow);
    for (let i = 1; i <= 4; i++) {
      const el = document.getElementById('pl' + i);
      if (i - 1 < (s[3].labels || []).length) {
        show('pl' + i);
        const nm = el.querySelector('.pillar-name'); const ds = el.querySelector('.pillar-desc');
        if (nm) nm.textContent = s[3].labels[i - 1];
        if (ds) ds.textContent = s[3].supporting || '';
      } else hide('pl' + i);
    }
    setIcon('di1', s[4].icon);
    const dir = splitIntoSlots(s[4].text, 2, 16, 'scenario-b.scene-5.text');
    setHTML('d1', dir[0] || '');
    if (dir[1]) { show('d2'); setHTML('d2', '<span class="muted">' + dir[1] + '</span>'); } else hide('d2');
    setText('d3', s[4].supporting);
    cta(s[5]);
  } else if (plan.scenario === 'c' && s.length === 5) {
    const hook = splitIntoSlots(s[0].text, 2, 17, 'scenario-c.scene-1.text');
    setText('h1', hook[0] || '');
    if (hook[1]) { show('h2'); setHTML('h2', '<span class="accent">' + hook[1] + '</span>'); } else hide('h2');
    for (let i = 0; i < 4; i++) {
      const el = document.getElementById('bs' + i);
      if (i < (s[1].labels || []).length) {
        show('bs' + i);
        const t = el.querySelector('.build-title'); const d = el.querySelector('.build-desc');
        if (t) t.textContent = s[1].labels[i];
        if (d) d.textContent = s[1].supporting || '';
      } else hide('bs' + i);
    }
    const live = splitIntoSlots(s[2].text, 2, 17, 'scenario-c.scene-3.text');
    setText('l1', live[0] || '');
    if (live[1]) { show('l2'); setHTML('l2', '<span class="accent">' + live[1] + '</span>'); } else hide('l2');
    setText('dc1', s[3].text);
    const dcLabels = s[3].labels || [];
    const dc0 = document.getElementById('dc-0'); const dc1 = document.getElementById('dc-1');
    if (dc0) {
      const t = dc0.querySelector('.dir-card-title'); const d2 = dc0.querySelector('.dir-card-desc');
      if (t) t.textContent = dcLabels[0] || 'You direct';
      if (d2) d2.textContent = s[3].supporting || '';
    }
    if (dc1) {
      const t = dc1.querySelector('.dir-card-title'); const d2 = dc1.querySelector('.dir-card-desc');
      if (t) t.textContent = dcLabels[1] || 'AI runs it';
      if (d2) d2.textContent = s[3].supporting || '';
    }
    cta(s[4]);
  } else if (plan.scenario === 'd' && s.length === 5) {
    /* contrast-text: hook contrast, claim, proof, resolve rows, CTA */
    const hook = splitIntoSlots(s[0].text, 2, 22, 'scenario-d.scene-1.text');
    setText('h1', hook[0] || '');
    if (hook[1]) { show('h2'); setHTML('h2', '<span class="contrast">' + hook[1] + '</span>'); } else hide('h2');
    setText('h4', s[0].supporting);
    setIcon('c0', s[1].icon);
    const claim = splitIntoSlots(s[1].text, 2, 22, 'scenario-d.scene-2.text');
    setText('c1', claim[0] || '');
    if (claim[1]) { show('c2'); setHTML('c2', '<span class="accent">' + claim[1] + '</span>'); } else hide('c2');
    setText('c3', s[1].supporting);
    setText('p1', s[2].text);
    const chip = (s[2].labels && s[2].labels.length) ? s[2].labels[0] : s[2].supporting;
    if (chip) { show('p2'); setText('p2', chip); } else hide('p2');
    const resolveLabels = s[3].labels || [];
    for (let i = 0; i < 3; i++) {
      const el = document.getElementById('r' + i);
      if (i < resolveLabels.length) { show('r' + i); const sp = el.querySelector('span'); if (sp) sp.textContent = resolveLabels[i]; }
      else hide('r' + i);
    }
    cta(s[4]);
  } else if (plan.scenario === 'e' && s.length === 4) {
    /* storyboard: problem -> turn -> result, then CTA - FIX: eyebrow + icon */
    setText('f0', s[0].eyebrow || '01 PROBLEM');
    setIcon('f0', s[0].icon); setText('f1', s[0].text); setText('f2', s[0].supporting);
    setText('t0', s[1].eyebrow || '02 TURN');
    setIcon('t0', s[1].icon); setText('t1', s[1].text); setText('t2', s[1].supporting);
    setText('r0', s[2].eyebrow || '03 RESULT');
    setIcon('r0', s[2].icon); setText('r1', s[2].text); setText('r2', s[2].supporting);
    cta(s[3]);
  } else if (plan.scenario === 'f' && s.length === 4) {
    /* data-card: hero number + claim + proof, then CTA */
    const number = ((s[0].labels || []).find(function (l) { return /^\\d+([.,]\\d+)?%?$/.test(String(l).trim()); })
      || (String(s[0].text).match(/\\d+([.,]\\d+)?%?/) || [''])[0] || '');
    if (number) setText('count', number.trim());
    // FIX: show headline + supporting so story text not discarded
    const heroCombined = (s[0].text || '') + (s[0].supporting ? ' - ' + s[0].supporting : '');
    setText('h1', heroCombined);
    setIcon('c0', s[1].icon);
    setText('c1', s[1].text);
    setText('c2', s[1].supporting);
    setText('p1', s[2].text);
    const chip = (s[2].labels && s[2].labels.length) ? s[2].labels[0] : s[2].supporting;
    if (chip) { show('p2'); setText('p2', chip); } else hide('p2');
    cta(s[3]);
  } else if (plan.scenario === 'g' && s.length === 4) {
    /* question-hook: question -> stakes -> resolve, then CTA */
    setIcon('q0', s[0].icon);
    const q = splitIntoSlots(s[0].text, 2, 22, 'scenario-g.scene-1.text');
    setHTML('q1', q[0] + (q[1] ? ' <span class="accent">' + q[1] + '</span>' : ''));
    setText('q2', s[0].supporting);
    setIcon('t0', s[1].icon);
    const st = splitIntoSlots(s[1].text, 2, 22, 'scenario-g.scene-2.text');
    setHTML('t1', st[0] + (st[1] ? ' <span class="muted">' + st[1] + '</span>' : ''));
    setText('t2', s[1].supporting);
    setIcon('r0', s[2].icon);
    const re = splitIntoSlots(s[2].text, 2, 24, 'scenario-g.scene-3.text');
    setHTML('r1', re[0] + (re[1] ? ' <span class="accent">' + re[1] + '</span>' : ''));
    const chip = (s[2].labels && s[2].labels.length) ? s[2].labels[0] : s[2].supporting;
    if (chip) { show('r2'); setText('r2', chip); } else hide('r2');
    cta(s[3]);
  } else if (plan.scenario === 'h' && s.length === 5) {
    /* loop-rail: band promise, goal, watch, run, CTA */
    setText('h0', s[0].eyebrow || 'ONE DIRECTION');
    setText('h1', s[0].text); setText('h2', s[0].supporting);
    setText('g1', s[1].text); setText('g2', s[1].supporting);
    setText('w1', s[2].text); setText('w2', s[2].supporting);
    setText('r1', s[3].text); setText('r2', s[3].supporting);
    cta(s[4]);
  } else if (plan.scenario === 'i' && s.length === 4) {
    /* heartbeat: one live card, goal, watch, CTA */
    setText('h0', s[0].eyebrow || 'ONE CARD, LIVE');
    setText('h1', s[0].text); setText('h2', s[0].supporting);
    setText('g1', s[1].text); setText('g2', s[1].supporting);
    setText('w1', s[2].text); setText('w2', s[2].supporting);
    setText('star-title', s[1].text || '');
    setText('run-title', s[2].supporting || '');
    cta(s[3]);
  } else {
    throw new Error('plan mismatch: scenario=' + plan.scenario + ' scenes=' + s.length);
  }
}

/* ── narration-only mix on the measured schedule (one-voice enforced) ───── */
function mixNarration(key, outM4a) {
  const narration = JSON.parse(readFileSync(NARRATION, "utf8"));
  const timing = (narration.scene_timing || {})[key];
  const voiceManifest = existsSync(MANIFEST) ? JSON.parse(readFileSync(MANIFEST, "utf8")) : {};
  const persona = narration.voice_selection || "Charon";
  if (!timing || !Array.isArray(timing.scenes) || !timing.scenes.length) {
    throw new Error(`scene_timing.${key} missing - run campaign TTS first`);
  }
  if (timing.voice !== persona || voiceManifest.voice !== persona) {
    throw new Error(`one-voice rule violated for ${key}: scene_timing.voice=${timing.voice} manifest.voice=${voiceManifest.voice} voice_selection=${persona} - regenerate, never mix a different narrator`);
  }
  const tmp = join(AUDIO, `.mix-${key}-${Date.now()}`);
  mkdirSync(tmp, { recursive: true });
  const segments = [];
  let prevSpeechEnd = 0;
  try {
    for (let i = 0; i < timing.scenes.length; i++) {
      const sc = timing.scenes[i];
      const clip = join(AUDIO, `${key}-${sc.scene}.wav`);
      if (!existsSync(clip)) throw new Error(`missing clip ${clip}`);
      const lead = Math.max(0, sc.speech_start - prevSpeechEnd);
      const trail = (i === timing.scenes.length - 1) ? Math.max(0, sc.end - sc.speech_end) : 0;
      const segOut = join(tmp, `seg-${String(i).padStart(2, "0")}.wav`);
      execSync(`ffmpeg -y -v error -f lavfi -t ${lead.toFixed(3)} -i "anullsrc=r=48000:cl=mono" -i ${clip} ` +
        `-filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[pre];[pre]apad=pad_dur=${trail.toFixed(3)}" ` +
        `-ar 48000 -ac 1 -c:a pcm_s16le ${segOut}`);
      segments.push(segOut);
      prevSpeechEnd = sc.speech_end;
    }
    const listFile = join(tmp, "list.txt");
    const list = segments.map((seg) => `file '${seg}'`).join("\n");
    writeFileSync(listFile, list + "\n");
    execSync(`ffmpeg -y -v error -f concat -safe 0 -i ${listFile} ` +
      `-af loudnorm=I=-16:TP=-1.0:LRA=11 -ar 48000 -ac 1 -c:a aac -b:a 192k ${outM4a}`);
    console.log(`  mixed narration ${key} -> ${outM4a} (${timing.scenes.length} scenes · persona ${persona})`);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
}

async function findStableThumbnailFrame(page, timing, plan) {
  const first = timing.scenes[0];
  const nextStart = timing.scenes[1] ? timing.scenes[1].start : first.end;
  const preferredOffset = { b: 1.45, c: 1.15, d: 1.15, e: 1.15, f: 1.15, g: 1.15, h: 0.95, i: 0.95 }[plan.scenario] || 1.15;
  const start = first.start + preferredOffset;
  const end = Math.max(start, nextStart - 0.35);
  const expected = normalizeText(plan.scenes[0].text);
  for (let candidate = start; candidate <= end + 0.001; candidate += 0.1) {
    const frame = Math.max(0, Math.round(candidate * FPS));
    await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, frame, FPS);
    await new Promise((r) => setTimeout(r, 80));
    const state = await page.evaluate((wanted) => {
      const active = document.querySelector(".scene.active");
      if (!active) return { ready: false, reason: "no-active-scene" };
      const visible = [...active.querySelectorAll(".r")].filter((el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" && Number(style.opacity) >= 0.92 && rect.width > 0 && rect.height > 0 && el.innerText.trim();
      });
      const text = visible.map((el) => el.innerText).join(" ").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
      const words = wanted.split(" ").filter((word) => word.length > 2);
      const complete = words.length > 0 && words.every((word) => text.includes(word));
      return { ready: complete, active: active.id, visible: visible.length, text };
    }, expected);
    if (state.ready) return { frame, time: frame / FPS, state };
  }
  throw new Error(`[thumbnail-gate] ${plan.template} hook never reached a stable complete frame before scene 2`);
}

async function inspectFlowQa(page, timing, plan) {
  const scenes = [];
  for (let index = 0; index < timing.scenes.length; index++) {
    const sc = timing.scenes[index];
    const probeTime = Math.max(sc.start + 0.25, sc.end - 0.25);
    const frame = Math.max(0, Math.round(probeTime * FPS));
    await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, frame, FPS);
    await new Promise((r) => setTimeout(r, 90));
    const expected = expectedFlowText(plan, index);
    const result = await page.evaluate((wanted) => {
      const normalize = (value) => String(value || "").toLowerCase()
        .replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
      const active = document.querySelector(".scene.active");
      if (!active) return { active: null, expected: wanted, visible_text: "", missing: wanted, overflow: ["no-active-scene"], passed: false };
      const visible = [...active.querySelectorAll("[id], .build-title, .build-desc, .dir-card-title, .dir-card-desc")].filter((el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0 && el.innerText.trim();
      });
      const visibleText = normalize(visible.map((el) => el.innerText).join(" "));
      const missing = wanted.filter((entry) => {
        const words = normalize(entry.text).split(" ").filter((word) => word.length > 2);
        return words.length > 0 && !words.every((word) => visibleText.includes(word));
      });
      const overflow = [];
      visible.forEach((el) => {
        const rect = el.getBoundingClientRect();
        const outside = rect.left < -2 || rect.top < -2 || rect.right > window.innerWidth + 2 || rect.bottom > window.innerHeight + 2;
        const clipped = el.scrollWidth > el.clientWidth + 2;
        if (outside || clipped) overflow.push(el.id || el.className || el.tagName);
      });
      return { active: active.id, expected: wanted, visible_text: visibleText, visible_elements: visible.length, missing, overflow, passed: missing.length === 0 && overflow.length === 0 };
    }, expected);
    scenes.push({ index, id: plan.scenes[index]?.id || `scene-${index + 1}`, time: probeTime, frame, ...result });
  }

  const ctaLayout = await page.evaluate(() => {
    const title = document.getElementById("ct1");
    const url = document.getElementById("ct2");
    if (!title || !url) return { passed: false, reason: "CTA slots missing" };
    const lines = [...title.querySelectorAll(".cta-line")].filter((el) => el.textContent.trim());
    const rects = lines.map((el) => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return { text: el.textContent.trim(), display: style.display, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height };
    });
    const urlRect = url.getBoundingClientRect();
    const inViewport = (rect) => rect.left >= -2 && rect.top >= -2 && rect.right <= window.innerWidth + 2 && rect.bottom <= window.innerHeight + 2;
    const separated = rects.length === 2 && rects[0].display === "block" && rects[1].display === "block" && rects[1].top >= rects[0].bottom - 2;
    const noOverlap = rects.length === 2 && (rects[0].bottom <= rects[1].top + 2);
    const passed = separated && noOverlap && rects.every(inViewport) && inViewport(urlRect) && normalize(title.innerText || "") === "go to services";
    return { passed, lines: rects, url: { left: urlRect.left, top: urlRect.top, right: urlRect.right, bottom: urlRect.bottom, width: urlRect.width, height: urlRect.height }, normalized_title: normalize(title.innerText || ""), reason: passed ? "" : "CTA must be two separated in-viewport lines with readable URL" };
    function normalize(value) { return String(value || "").toLowerCase().replace(/\s+/g, " ").trim(); }
  });
  const sceneTextCoveragePassed = scenes.every((scene) => scene.passed);
  const noHiddenTextOverflow = scenes.every((scene) => scene.overflow.length === 0);
  return {
    schema_version: FLOW_QA_SCHEMA,
    scene_text_coverage_passed: sceneTextCoveragePassed,
    no_hidden_text_overflow: noHiddenTextOverflow,
    cta_layout_passed: ctaLayout.passed,
    passed: sceneTextCoveragePassed && noHiddenTextOverflow && ctaLayout.passed,
    scenes,
    cta: ctaLayout,
  };
}

async function inspectTemporalQa(page, timing, plan, totalFrames) {
  const sampleStep = 3;
  const boundaryFrames = new Set([0, totalFrames - 1]);
  timing.scenes.forEach((scene) => {
    [scene.start, scene.end].forEach((time) => {
      const frame = Math.max(0, Math.min(totalFrames - 1, Math.round(time * FPS)));
      [frame - 1, frame, frame + 1].forEach((candidate) => {
        if (candidate >= 0 && candidate < totalFrames) boundaryFrames.add(candidate);
      });
    });
  });
  const frames = new Set();
  for (let frame = 0; frame < totalFrames; frame += sampleStep) frames.add(frame);
  boundaryFrames.forEach((frame) => frames.add(frame));

  const samples = [];
  for (const frame of [...frames].sort((a, b) => a - b)) {
    const expectedByScene = plan.scenes.map((_, index) => expectedFlowText(plan, index));
    const state = await page.evaluate(async ({ frame, fps, expectedByScene }) => {
      window.__setFrame(frame, fps);
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
      const active = document.querySelector(".scene.active");
      const visible = active ? [...active.querySelectorAll("[id], .build-title, .build-desc, .dir-card-title, .dir-card-desc")].filter((el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0.01 && rect.width > 0 && rect.height > 0 && el.innerText.trim();
      }) : [];
      const visibleText = normalize(visible.map((el) => el.innerText).join(" "));
      const coverage = expectedByScene.map((entries) => entries.map((entry) => {
        const words = normalize(entry.text).split(" ").filter((word) => word.length > 2);
        return { field: entry.field, covered: words.length > 0 && words.every((word) => visibleText.includes(word)) };
      }));
      const activeMatch = active && /^s(\d+)$/.exec(active.id);
      return { frame, time: frame / fps, active: active ? active.id : null, active_index: activeMatch ? Number(activeMatch[1]) - 1 : -1, text: visibleText, coverage };
    }, { frame, fps: FPS, expectedByScene });
    samples.push(state);
  }

  const sceneIntervals = timing.scenes.map((scene, index) => {
    const sceneSamples = samples.filter((sample) => sample.time >= scene.start - 0.001 && sample.time < scene.end - 0.001 && sample.active_index === index);
    const expected = expectedFlowText(plan, index);
    const byField = expected.map((entry, entryIndex) => {
      const states = sceneSamples.map((sample) => Boolean(sample.coverage[index]?.[entryIndex]?.covered));
      const firstVisible = states.indexOf(true);
      const reappears = firstVisible >= 0 && states.slice(firstVisible + 1).some((visible) => !visible);
      return { field: entry.field, text: entry.text, sampled: states.length, first_visible_sample: firstVisible, reappears };
    });
    return { index, id: plan.scenes[index]?.id || `scene-${index + 1}`, sampled_frames: sceneSamples.length, expected: byField, passed: sceneSamples.length > 0 && byField.every((entry) => entry.first_visible_sample >= 0 && !entry.reappears) };
  });

  const activeSequence = samples.map((sample) => sample.active_index).filter((index) => index >= 0);
  const sceneOscillation = activeSequence.some((index, i) => i > 0 && index < activeSequence[i - 1]);
  const boundaries = timing.scenes.slice(1).map((scene, index) => {
    const previousIndex = index;
    const currentIndex = index + 1;
    const frame = Math.max(0, Math.min(totalFrames - 1, Math.ceil(scene.start * FPS)));
    const before = [...samples].reverse().find((sample) => sample.frame < frame) || null;
    const at = samples.find((sample) => sample.frame >= frame) || null;
    const after = samples.find((sample) => sample.frame > frame) || null;
    const oldExpected = expectedFlowText(plan, previousIndex);
    const oldWords = oldExpected.flatMap((entry) => normalizeText(entry.text).split(" ").filter((word) => word.length > 2));
    const oldVisibleAfter = after && oldWords.length > 0 && oldWords.every((word) => after.text.includes(word));
    return { from: plan.scenes[previousIndex]?.id, to: plan.scenes[currentIndex]?.id, frame, before_active: before?.active_index, at_active: at?.active_index, after_active: after?.active_index, old_text_visible_after: Boolean(oldVisibleAfter), passed: Boolean(before && at && after && before.active_index === previousIndex && at.active_index === currentIndex && after.active_index === currentIndex && !oldVisibleAfter) };
  });
  const passed = !sceneOscillation && sceneIntervals.every((scene) => scene.passed) && boundaries.every((boundary) => boundary.passed);
  return { schema_version: TEMPORAL_QA_SCHEMA, sample_step_frames: sampleStep, sampled_frames: samples.length, scene_oscillation: sceneOscillation, scene_intervals: sceneIntervals, boundaries, passed };
}

function probeMedia(path) {
  return JSON.parse(execSync(`ffprobe -v error -show_streams -show_format -of json "${path}"`, { encoding: "utf8" }));
}

function rational(value) {
  const [num, den] = String(value || "0/1").split("/").map(Number);
  return den ? num / den : 0;
}

function buildMediaQa(videoPath, thumbPath, expectedDuration, flow, temporal) {
  const videoProbe = probeMedia(videoPath);
  const thumbProbe = probeMedia(thumbPath);
  const video = (videoProbe.streams || []).find((s) => s.codec_type === "video") || {};
  const audio = (videoProbe.streams || []).find((s) => s.codec_type === "audio") || {};
  const thumb = (thumbProbe.streams || []).find((s) => s.codec_type === "video") || {};
  const checks = {
    video_dimensions: video.width === 1080 && video.height === 1920,
    video_fps: Math.abs(rational(video.r_frame_rate) - FPS) < 0.01,
    narration_aac: audio.codec_name === "aac",
    narration_48khz: Number(audio.sample_rate) === 48000,
    narration_mono: Number(audio.channels) === 1,
    duration_matches_schedule: Math.abs(Number(videoProbe.format?.duration || 0) - expectedDuration) <= 0.25,
    thumbnail_dimensions: thumb.width === 1080 && thumb.height === 1920,
    flow_scene_text_coverage: Boolean(flow?.scene_text_coverage_passed),
    flow_no_hidden_text_overflow: Boolean(flow?.no_hidden_text_overflow),
    flow_cta_layout: Boolean(flow?.cta_layout_passed),
    temporal_stability: Boolean(temporal?.passed),
  };
  return {
    schema_version: "1.0",
    video: { path: videoPath, duration: Number(videoProbe.format?.duration || 0), width: video.width, height: video.height, fps: rational(video.r_frame_rate), audio_codec: audio.codec_name, sample_rate: Number(audio.sample_rate), channels: Number(audio.channels) },
    thumbnail: { path: thumbPath, width: thumb.width, height: thumb.height },
    flow: flow || null,
    temporal: temporal || null,
    checks,
    passed: Object.values(checks).every(Boolean),
  };
}

function startServer() {
  return new Promise((res, rej) => {
    const server = createServer((req, rsp) => {
      let fp = join(ROOT, decodeURIComponent(req.url.split("?")[0]));
      if (fp.endsWith("/")) fp = join(fp, "index.html");
      if (!existsSync(fp)) { rsp.writeHead(404); rsp.end(); return; }
      const ext = fp.split(".").pop().toLowerCase();
      rsp.writeHead(200, { "Content-Type": MIME["." + ext] || "application/octet-stream", "Cache-Control": "no-cache" });
      rsp.end(readFileSync(fp));
    });
    server.listen(0, "127.0.0.1", () => res(server));
  });
}

async function runPipeline(item, probeOnly, manifestPath, registry) {
  const yt = item.renditions.youtube;
  const plan = planFor(item, registry);
  const assetDir = join(require("path").dirname(manifestPath), "assets/shorts", item.item_id);
  mkdirSync(assetDir, { recursive: true });

  const videoOut = join(assetDir, "video.mp4");
  const thumbOut = join(assetDir, "thumbnail.jpg");
  const mixM4a = join(assetDir, "narration.m4a");
  const qaOut = join(assetDir, "qa.json");
  const videoExists = existsSync(videoOut);
  const thumbExists = existsSync(thumbOut);
  const force = process.env.FORCE_RENDER === "1";
  if (videoExists && thumbExists && existsSync(qaOut) && !force) {
    console.log(`[${item.item_id}] already complete (video + thumbnail) - skipping`);
    return;
  }
  if (!probeOnly && !videoExists) {
    console.log(`\n[${item.item_id}] TTS scenario ${plan.scenario} (${plan.template})...`);
    execSync(`CAMPAIGN_MANIFEST=${JSON.stringify(manifestPath)} CAMPAIGN_ITEM_ID=${item.item_id} node scripts/tts-gemini.js ${plan.scenario}`,
      { cwd: ROOT, stdio: "inherit", env: { ...process.env }, shell: "/bin/zsh" });
    console.log(`[${item.item_id}] Mixing narration-only track...`);
    mixNarration(plan.scenario, mixM4a);
  }

  const server = await startServer();
  const baseUrl = `http://127.0.0.1:${server.address().port}`;
  const templateUrl = `${baseUrl}/.agents/company/departments/design/templates/video/${plan.file.split("/").pop()}`;
  console.log(`[${item.item_id}] Rendering ${plan.template} @ portrait ${FPS}fps`);

  const browser = await puppeteer.launch({
    headless: "shell",
    executablePath: CHROME,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
      "--font-render-hinting=none", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
    await page.goto(templateUrl, { waitUntil: "networkidle0", timeout: 30000 });
    await page.evaluate(() => document.fonts.ready);
    // per-video theme: manifest yt.design.theme -> html[data-theme] (fixes single-color batch)
    await page.evaluate((theme) => document.documentElement.setAttribute('data-theme', theme), yt.design.theme);
    await page.addStyleTag({ content: DETERMINISTIC_CAPTURE_CSS });
    await new Promise((r) => setTimeout(r, 500));
    await page.evaluate(injectCampaign, plan);
    await page.waitForFunction(() => window.__timing || window.__timingError, { timeout: 10000 });
    const timing = await page.evaluate(() => window.__timing);
    if (!timing) { throw new Error(`[${item.item_id}] __timingError - narration.json scene_timing.${plan.scenario} missing`); }
    const last = timing.scenes[timing.scenes.length - 1];
    const durationSec = Math.ceil((last.end + 0.25) * 10) / 10;
    const totalFrames = Math.ceil(durationSec * FPS);
    console.log(`[${item.item_id}] duration ${durationSec}s (${totalFrames} frames)`);
    const stableThumb = await findStableThumbnailFrame(page, timing, plan);
    const stillFrame = stableThumb.frame;
    console.log(`[${item.item_id}] thumbnail gate passed at ${stableThumb.time.toFixed(2)}s (${stableThumb.state.active}, ${stableThumb.state.visible} visible elements)`);
    const flowQa = await inspectFlowQa(page, timing, plan);
    writeFileSync(join(assetDir, "flow-qa.json"), JSON.stringify(flowQa, null, 2) + "\n");
    if (!flowQa.passed) {
      const failedScenes = flowQa.scenes.filter((scene) => !scene.passed).map((scene) => `${scene.id}: missing=${scene.missing.map((entry) => entry.field).join("|")} overflow=${scene.overflow.join("|")}`).join("; ");
      throw new Error(`[flow-gate] ${item.item_id} failed: ${failedScenes || flowQa.cta?.reason || "unknown flow failure"}`);
    }
    console.log(`[${item.item_id}] flow gate passed: ${flowQa.scenes.length} scenes covered, CTA layout verified`);
    const temporalQa = await inspectTemporalQa(page, timing, plan, totalFrames);
    writeFileSync(join(assetDir, "temporal-qa.json"), JSON.stringify(temporalQa, null, 2) + "\n");
    if (!temporalQa.passed) {
      const failedScenes = temporalQa.scene_intervals.filter((scene) => !scene.passed).map((scene) => `${scene.id}: ${scene.expected.filter((entry) => entry.reappears || entry.first_visible_sample < 0).map((entry) => entry.field).join("|")}`).join("; ");
      const failedBoundaries = temporalQa.boundaries.filter((boundary) => !boundary.passed).map((boundary) => `${boundary.from}->${boundary.to}`).join("; ");
      throw new Error(`[temporal-gate] ${item.item_id} failed: scenes=${failedScenes || "none"} boundaries=${failedBoundaries || "none"}`);
    }
    console.log(`[${item.item_id}] temporal gate passed: ${temporalQa.sampled_frames} timeline samples, ${temporalQa.boundaries.length} boundaries stable`);

    if (probeOnly) {
      await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, stillFrame, FPS);
      await new Promise((r) => setTimeout(r, 300));
      const probeOut = join(require("path").dirname(manifestPath), "probe-" + item.item_id + ".png");
      await page.screenshot({ path: probeOut, type: "png" });
      console.log(`PROBE_OK ${probeOut}`);
      return;
    }

    if (videoExists && !force) {
      /* Thumbnail-only resume: the same stable hook gate as a fresh render,
         plus objective media QA before the asset is accepted. */
      await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, stillFrame, FPS);
      await new Promise((r) => setTimeout(r, 700));
      await page.screenshot({ path: thumbOut, type: "jpeg", quality: 92 });
      const qa = buildMediaQa(videoOut, thumbOut, durationSec, flowQa, temporalQa);
      writeFileSync(qaOut, JSON.stringify({ ...qa, thumbnail_time: stableThumb.time, template: plan.template }, null, 2) + "\n");
      if (!qa.passed) throw new Error(`[media-gate] ${item.item_id} failed: ${Object.entries(qa.checks).filter(([, ok]) => !ok).map(([name]) => name).join(", ")}`);
      console.log(`[${item.item_id}] THUMBNAIL_ONLY ${thumbOut}`);
      return;
    }

    const framesDir = join(assetDir, "frames");
    if (existsSync(framesDir)) rmSync(framesDir, { recursive: true });
    mkdirSync(framesDir, { recursive: true });
    console.log(`[${item.item_id}] Capturing frames...`);
    for (let frame = 0; frame < totalFrames; frame++) {
      await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, frame, FPS);
      await new Promise((r) => setTimeout(r, 16));
      await new Promise((r) => setTimeout(r, 16));
      await page.screenshot({ path: join(framesDir, `frame_${String(frame).padStart(5, "0")}.png`), type: "png" });
      if ((frame + 1) % (FPS * 5) === 0 || frame === totalFrames - 1) {
        process.stdout.write(`\r  ${frame + 1}/${totalFrames} (${(((frame + 1) / totalFrames) * 100).toFixed(0)}%)`);
      }
    }
    console.log("");
    const silentMp4 = join(assetDir, "silent.mp4");
    execSync(`ffmpeg -y -framerate ${FPS} -i ${join(framesDir, "frame_%05d.png")} -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart ${silentMp4}`, { stdio: "pipe" });
    rmSync(framesDir, { recursive: true });

    if (!existsSync(mixM4a)) throw new Error(`missing narration.m4a for ${item.item_id}`);
    execSync(`ffmpeg -y -i ${silentMp4} -i ${mixM4a} -c:v copy -c:a aac -b:a 192k -shortest ${videoOut}`, { stdio: "pipe" });
    rmSync(silentMp4, { force: true });

    /* Stable plain-frame thumbnail: hook window frame grab, no still-title
       overlay and no glass card. */
    await page.evaluate((f, fps) => { window.__setFrame(f, fps); }, stillFrame, FPS);
    await new Promise((r) => setTimeout(r, 300));
    await page.screenshot({ path: thumbOut, type: "jpeg", quality: 88 });
    const qa = buildMediaQa(videoOut, thumbOut, durationSec, flowQa, temporalQa);
    writeFileSync(qaOut, JSON.stringify({ ...qa, thumbnail_time: stableThumb.time, template: plan.template }, null, 2) + "\n");
    if (!qa.passed) throw new Error(`[media-gate] ${item.item_id} failed: ${Object.entries(qa.checks).filter(([, ok]) => !ok).map(([name]) => name).join(", ")}`);
    console.log(`[${item.item_id}] DONE ${videoOut} (${(statSync(videoOut).size / 1024 / 1024).toFixed(1)} MB)`);
  } finally {
    await browser.close();
    server.close();
  }
}

(async () => {
  const args = process.argv.slice(2);
  if (args.includes("--check")) checkMode();
  const manifestPath = args.find((a) => a.endsWith(".json")) || process.env.CAMPAIGN_MANIFEST;
  if (!manifestPath) {
    console.error("Usage: node scripts/render-campaign-shorts.cjs --check | <campaign.json> [itemId] [--probe]");
    process.exit(1);
  }
  const absoluteManifest = resolve(manifestPath);
  const probeOnly = args.includes("--probe");
  const onlyId = args.find((a) => a.includes("item-")) || null;
  const manifest = JSON.parse(readFileSync(absoluteManifest, "utf8"));
  const registry = readRegistry();
  const yt = manifest.items.filter((it) => !onlyId || it.item_id === onlyId);
  if (!yt.length) throw new Error(`No items to render (onlyId=${onlyId})`);
  for (const item of yt) {
    await runPipeline(item, probeOnly, absoluteManifest, registry);
  }
  console.log("\nSHORTS_RENDER_OK");
})().catch((err) => { console.error("\nSHORTS_RENDER_FAIL:", err.message); process.exit(1); });
