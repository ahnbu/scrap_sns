#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "..");
const DEFAULT_IMAGE_ROOT = path.join(PROJECT_ROOT, "web_viewer", "images");
const DEFAULT_WEB_PREFIX = "web_viewer/images";

function parseArgs(argv) {
  const options = {
    target: "",
    dryRun: false,
    apply: false,
    imageRoot: DEFAULT_IMAGE_ROOT,
    webPrefix: DEFAULT_WEB_PREFIX,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--target") {
      options.target = argv[++index] || "";
    } else if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "--apply") {
      options.apply = true;
    } else if (arg === "--image-root") {
      options.imageRoot = argv[++index] || "";
    } else if (arg === "--web-prefix") {
      options.webPrefix = argv[++index] || "";
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }

  if (!options.target) {
    throw new Error("--target is required");
  }
  if (options.apply && options.dryRun) {
    throw new Error("choose only one of --dry-run or --apply");
  }
  if (!options.apply) {
    options.dryRun = true;
  }
  return options;
}

function readJsonWithBomInfo(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  return {
    hasBom: raw.startsWith("\uFEFF"),
    payload: JSON.parse(raw.replace(/^\uFEFF/, "")),
  };
}

function toKstTimestamp() {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(new Date())
    .replace(" ", "_")
    .replaceAll("-", "")
    .replaceAll(":", "");
  return parts;
}

function mediaExtension(url) {
  const lower = String(url || "").toLowerCase();
  if (lower.includes(".png")) return ".png";
  if (lower.includes(".webp")) return ".webp";
  return ".jpg";
}

function localImageForMedia(mediaUrl, imageRoot, webPrefix) {
  const hash = crypto.createHash("md5").update(String(mediaUrl), "utf8").digest("hex");
  const filename = `${hash}${mediaExtension(mediaUrl)}`;
  return {
    fsPath: path.join(imageRoot, filename),
    webPath: `${webPrefix.replace(/\/+$/, "")}/${filename}`,
  };
}

function isDownloadableImage(mediaUrl) {
  return !String(mediaUrl || "").toLowerCase().includes(".mp4");
}

function backfillPosts(posts, options) {
  const stats = {
    posts: posts.length,
    mediaPosts: 0,
    localPostsBefore: 0,
    localPostsAfter: 0,
    recoverablePosts: 0,
    recoveredImages: 0,
    changedPosts: 0,
  };

  for (const post of posts) {
    const media = Array.isArray(post.media) ? post.media.filter(isDownloadableImage) : [];
    const existing = Array.isArray(post.local_images) ? post.local_images : [];
    if (media.length > 0) stats.mediaPosts += 1;
    if (existing.length > 0) stats.localPostsBefore += 1;

    const merged = [];
    const seen = new Set();
    for (const item of existing) {
      if (!item || seen.has(item)) continue;
      merged.push(item);
      seen.add(item);
    }

    let recoveredForPost = 0;
    for (const mediaUrl of media) {
      const candidate = localImageForMedia(mediaUrl, options.imageRoot, options.webPrefix);
      if (!fs.existsSync(candidate.fsPath) || seen.has(candidate.webPath)) continue;
      merged.push(candidate.webPath);
      seen.add(candidate.webPath);
      recoveredForPost += 1;
    }

    if (recoveredForPost > 0) {
      stats.recoverablePosts += 1;
      stats.recoveredImages += recoveredForPost;
      stats.changedPosts += 1;
      post.local_images = merged;
    } else if (existing.length > 0) {
      post.local_images = merged;
    }

    if (Array.isArray(post.local_images) && post.local_images.length > 0) {
      stats.localPostsAfter += 1;
    }
  }

  return stats;
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const targetPath = path.resolve(PROJECT_ROOT, options.target);
  const imageRoot = path.resolve(PROJECT_ROOT, options.imageRoot);
  const { hasBom, payload } = readJsonWithBomInfo(targetPath);
  const posts = Array.isArray(payload.posts) ? payload.posts : [];
  const stats = backfillPosts(posts, { ...options, imageRoot });

  const result = {
    mode: options.apply ? "apply" : "dry-run",
    target: path.relative(PROJECT_ROOT, targetPath).replaceAll("\\", "/"),
    ...stats,
    backup: null,
  };

  if (options.apply && stats.changedPosts > 0) {
    const backupPath = `${targetPath}.${toKstTimestamp()}.bak`;
    fs.copyFileSync(targetPath, backupPath);
    const body = JSON.stringify(payload, null, 4);
    fs.writeFileSync(targetPath, `${hasBom ? "\uFEFF" : ""}${body}\n`, "utf8");
    result.backup = path.relative(PROJECT_ROOT, backupPath).replaceAll("\\", "/");
  }

  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
}
