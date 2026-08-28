#!/usr/bin/env node
/**
 * validate-design.js — Sends rendered design outputs to a vision-capable model
 * for structured visual QA. Reads GEMINI_API_KEY from .spielos/.env.
 *
 * Usage:
 *   node scripts/validate-design.js <image1> [image2] ...
 *
 * Checks per image: composition, headline hierarchy, signature line +
 * bullseye, logo + website, dead space, text truncation/overlap, flat
 * Gruvbox consistency. Prints a PASS/FAIL verdict per image.
 */

import { readFileSync, existsSync } from "fs";
import { join, resolve } from "path";
import { fileURLToPath } from "url";

const ROOT = resolve(fileURLToPath(new URL("../../../..", import.meta.url)));
const images = process.argv.slice(2);
if (!images.length) {
  console.error("Usage: node scripts/validate-design.js <image> [image...]");
  process.exit(1);
}
for (const img of images) {
  if (!existsSync(img)) {
    console.error(`Missing image: ${img}`);
    process.exit(1);
  }
}

const env = readFileSync(join(ROOT, ".spielos/.env"), "utf8");
const key = env.match(/^GEMINI_API_KEY=(.+)$/m)?.[1]?.trim();
if (!key) {
  console.error("GEMINI_API_KEY not found in .spielos/.env");
  process.exit(1);
}

const SYSTEM = `You are the visual QA reviewer for SpielOS, a flat Gruvbox-dark brand.
Brand contract to check against:
- Flat, quiet Gruvbox composition (warm dark background, restrained palette).
- One dominant headline, clear hierarchy, no competing visual noise.
- The wandering goal line: completed travel is a solid primary stroke, the
  route ahead is muted and dashed, ending in a simple flat bullseye. The line
  may deliberately run off-canvas; the bullseye may be cropped at the edge.
- Official SpielOS tiled logo and "spielos.xyz" must be present, readable,
  and in fixed safe areas.
- No 3D, device mockups, glassmorphism, spectacle gradients, or clutter.
For each image reply in exactly this format:
IMAGE: <filename>
PASS|FAIL
Issues: <bullet list of concrete issues, or "none">
Notes: <1-2 sentences on composition quality>`;

const parts = [
  { text: SYSTEM + "\n\nValidate each of the following images against the contract:" },
  ...images.map((img) => ({
    inline_data: {
      mime_type: img.endsWith(".png") ? "image/png" : "image/jpeg",
      data: readFileSync(img).toString("base64"),
    },
  })),
];

const res = await fetch(
  `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${key}`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts }],
      generationConfig: { temperature: 0.2, maxOutputTokens: 4096 },
    }),
  }
);
if (!res.ok) {
  console.error(`API error ${res.status}: ${await res.text()}`);
  process.exit(1);
}
const data = await res.json();
const text = data.candidates?.[0]?.content?.parts?.map((p) => p.text).join("\n");
if (!text) {
  console.error("Empty response from vision model");
  process.exit(1);
}
console.log(text);
