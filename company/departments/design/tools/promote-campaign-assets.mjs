#!/usr/bin/env node

import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const ORIGIN = "https://spielos.xyz";

const readFlag = (args, flag) => {
  const index = args.indexOf(flag);
  return index < 0 ? "" : String(args[index + 1] || "");
};

const approvalId = (batchApprovalId, contentId, checksum) =>
  `batch-${createHash("sha256").update(`${batchApprovalId}|${contentId}|${checksum}`).digest("hex").slice(0, 20)}`;

/**
 * One canonical public filename for a promoted asset.
 *
 * Renderers already name some assets with a `{content_id}-` prefix
 * (e.g. render-design.js names Threads PNGs
 * `{content_id}-{size_preset}-{W}x{H}.png`). Pre-pending content_id again
 * produced doubled URLs like
 * `.../batch-03-item-04-threads-batch-03-item-04-threads-threads-portrait-1080x1350.png`
 * which broke Buffer media fetch. The public name therefore keeps the asset's
 * own basename whenever the content_id segment is already present anywhere in
 * it (no repetition), and only falls back to `{content_id}-{basename}` for
 * assets whose basename carries no identity (e.g. YouTube `video.mp4`),
 * preserving existing URLs. The invariant is unconditional: the returned name
 * never contains the content_id segment more times than the basename did.
 *
 * @param {string} contentId rendition content id, e.g. "batch-03-item-04-threads"
 * @param {string} localPath local asset path, e.g. ".../threads/batch-03-item-04-threads-threads-portrait-1080x1350.png"
 * @returns {string} clean public filename that never repeats the content_id segment
 */
export function publicAssetFilename(contentId, localPath) {
  const name = basename(localPath);
  return name.includes(contentId) ? name : `${contentId}-${name}`;
}

async function promote(args) {
  const manifestPath = readFlag(args, "--manifest");
  const batchApprovalId = readFlag(args, "--approval-id");
  if (!manifestPath || !batchApprovalId) throw new Error("Expected --manifest and --approval-id");
  const manifest = JSON.parse(await readFile(resolve(manifestPath), "utf8"));
  if (manifest.phase !== "rendered") throw new Error("Campaign Artifact must be rendered before promotion");
  const output = resolve(readFlag(args, "--output") || manifestPath.replace(/\.json$/, "-approved.json"));
  const result = structuredClone(manifest);
  const approvals = [];
  for (const item of result.items || []) {
    for (const platform of ["threads", "youtube"]) {
      const rendition = item.renditions?.[platform];
      const asset = rendition?.asset;
      if (!rendition?.content_id || !asset?.local_path || !asset?.sha256) {
        throw new Error(`Missing rendered provenance for ${item.item_id}/${platform}`);
      }
      const publicPath = `/campaign-assets/${result.batch_id}/${platform}/${publicAssetFilename(rendition.content_id, asset.local_path)}`;
      await mkdir(dirname(resolve("public", `.${publicPath}`)), { recursive: true });
      await copyFile(resolve(asset.local_path), resolve("public", `.${publicPath}`));
      const id = approvalId(batchApprovalId, rendition.content_id, asset.sha256);
      asset.public_url = `${ORIGIN}${publicPath}`;
      rendition.approval = { status: "approved", approval_id: id };
      approvals.push({ item_id: item.item_id, platform, approval_id: id, public_url: asset.public_url });
    }
  }
  result.phase = "approved";
  result.handoffs = [...(result.handoffs || []), {
    from: "rendered", to: "approved",
    evidence: { batch_approval_id: batchApprovalId, approvals, asset_host: ORIGIN },
  }];
  await writeFile(output, `${JSON.stringify(result, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ ok: true, output, approvals }, null, 2)}\n`);
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href;
if (isMain) {
  const args = process.argv.slice(2);
  if (args.includes("--check")) {
    process.stdout.write(JSON.stringify({ ok: true, origin: ORIGIN }) + "\n");
  } else {
    promote(args).catch((error) => {
      process.stderr.write(`${error.message}\n`);
      process.exitCode = 1;
    });
  }
}