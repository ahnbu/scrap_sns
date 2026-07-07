#!/usr/bin/env node
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8").replace(/^\uFEFF/, ""));
}

function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function timestamp() {
  const d = new Date();
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(d);
  return parts.replace(/[-: ]/g, "");
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (!next || next.startsWith("--")) {
        args[key] = true;
      } else {
        args[key] = next;
        i += 1;
      }
    } else {
      args._.push(arg);
    }
  }
  return args;
}

export function extractPosts(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.posts)) return payload.posts;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

function byId(posts) {
  const map = new Map();
  for (const post of posts) {
    const id = String(post?.platform_id || post?.code || "").trim();
    if (id && !map.has(id)) map.set(id, post);
  }
  return map;
}

function textExcerpt(post) {
  return String(post?.full_text || post?.text || "").replace(/\s+/g, " ").trim().slice(0, 160);
}

function mediaAssetId(url) {
  const match = String(url || "").match(/\/image\/v\d\/([^/]+)/);
  return match?.[1] || "";
}

function walkStrings(value, visitor, path = "$") {
  if (value == null) return;
  if (typeof value === "string") {
    visitor(value, path);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => walkStrings(item, visitor, `${path}[${index}]`));
    return;
  }
  if (typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      walkStrings(child, visitor, `${path}.${key}`);
    }
  }
}

function findRawEvidence(rawRecords, { platformId, mediaUrl }) {
  const assetId = mediaAssetId(mediaUrl);
  const needles = [assetId, mediaUrl].filter(Boolean);
  const hits = [];
  for (const record of rawRecords) {
    walkStrings(record, (value, path) => {
      if (needles.some((needle) => value.includes(needle))) {
        hits.push({
          file: record.file || "",
          path,
          value,
        });
      }
    });
  }
  hits.sort((a, b) => evidenceScore(b, platformId) - evidenceScore(a, platformId));
  return hits[0] || null;
}

function evidenceScore(hit, platformId) {
  const path = String(hit?.path || "").toLowerCase();
  const value = String(hit?.value || "");
  let score = 0;
  if (path.includes("entityembeddedobject")) score += 10;
  if (path.includes("detaildata.vectorimage")) score += 4;
  if (value.includes(platformId)) score += 3;
  if (path.includes("nonentityprofilepicture") || path.includes("profilepicture")) score -= 6;
  return score;
}

export function classifyMediaSource({ path = "", url = "" } = {}) {
  const pathLower = String(path).toLowerCase();
  const urlLower = String(url).toLowerCase();
  const joined = `${pathLower} ${urlLower}`;

  if (
    joined.includes("nonentityprofilepicture") ||
    joined.includes("profilepicture") ||
    joined.includes("companylogo") ||
    joined.includes("company-logo") ||
    joined.includes("profile-displayphoto")
  ) {
    return { label: "actor_image_false_positive", reason: "actor_profile_or_company_image" };
  }

  if (
    joined.includes("articleshare-shrink") ||
    joined.includes("article-cover_image") ||
    joined.includes("articlecomponent") ||
    joined.includes("linkpreview")
  ) {
    return { label: "article_or_link_thumbnail", reason: "article_or_link_preview_image" };
  }

  if (
    pathLower.includes("entityembeddedobject.image") ||
    joined.includes("feedshare-image-high-res") ||
    joined.includes("feedshare-shrink_800") ||
    joined.includes("feedshare-shrink_1280")
  ) {
    return { label: "post_media_confirmed", reason: "embedded_feedshare_media" };
  }

  return { label: "needs_browser_check", reason: "source_path_not_decisive" };
}

function zeroSummary() {
  return {
    total_mismatch: 0,
    post_media_confirmed: 0,
    baseline_missing_media: 0,
    actor_image_false_positive: 0,
    article_or_link_thumbnail: 0,
    needs_browser_check: 0,
  };
}

export function buildMediaAudit({ compareReport, shadowPosts, baselinePosts, rawRecords }) {
  const shadowMap = byId(shadowPosts);
  const baselineMap = byId(baselinePosts);
  const mismatches = Array.isArray(compareReport?.media_count_mismatch)
    ? compareReport.media_count_mismatch
    : [];
  const items = mismatches.map((mismatch) => {
    const platformId = String(mismatch.platform_id || "");
    const shadow = shadowMap.get(platformId) || {};
    const baseline = baselineMap.get(platformId) || {};
    const shadowMedia = Array.isArray(shadow.media) ? shadow.media : [];
    const baselineMedia = new Set(Array.isArray(baseline.media) ? baseline.media : []);
    const mediaUrl = shadowMedia.find((url) => !baselineMedia.has(url)) || shadowMedia[0] || "";
    const evidence = findRawEvidence(rawRecords, { platformId, mediaUrl });
    const classification = classifyMediaSource({
      path: evidence?.path || "",
      url: mediaUrl || evidence?.value || "",
    });

    return {
      platform_id: platformId,
      label: classification.label,
      reason: classification.reason,
      shadow_media_count: mismatch.shadow_media_count,
      baseline_media_count: mismatch.baseline_media_count,
      shadow_media_url: mediaUrl,
      post_url: shadow.url || baseline.url || "",
      text_excerpt: textExcerpt(shadow) || textExcerpt(baseline),
      raw_file: evidence?.file || "",
      raw_path: evidence?.path || "",
      raw_value_excerpt: String(evidence?.value || "").slice(0, 240),
    };
  });

  const summary = zeroSummary();
  summary.total_mismatch = items.length;
  for (const item of items) {
    if (Object.hasOwn(summary, item.label)) summary[item.label] += 1;
  }

  return {
    generated_at: new Date().toISOString(),
    summary,
    decision: decide(summary),
    items,
  };
}

function decide(summary) {
  if (summary.actor_image_false_positive > 1 || summary.needs_browser_check > 10) {
    return {
      recommendation: "hold",
      media_risk: "높음",
      reason: "actor/profile 오탐 또는 확인 필요 후보가 허용 기준을 넘음",
    };
  }
  if (summary.article_or_link_thumbnail > 0) {
    return {
      recommendation: "fallback_only",
      media_risk: "중간",
      reason: "link/article thumbnail 수집 정책 결정이 필요함",
    };
  }
  return {
    recommendation: "go_candidate",
    media_risk: "낮음",
    reason: "media 오탐 리스크가 기준 이하임",
  };
}

export function selectSpotcheckSamples(audit, perLabel = 5) {
  const byLabel = new Map();
  for (const item of audit?.items || []) {
    if (!byLabel.has(item.label)) byLabel.set(item.label, []);
    byLabel.get(item.label).push(item);
  }
  const labels = [
    "post_media_confirmed",
    "baseline_missing_media",
    "actor_image_false_positive",
    "article_or_link_thumbnail",
    "needs_browser_check",
  ];
  const samples = [];
  for (const label of labels) {
    const items = (byLabel.get(label) || [])
      .slice()
      .sort((a, b) => String(a.platform_id).localeCompare(String(b.platform_id)));
    samples.push(...items.slice(0, perLabel));
  }
  return samples;
}

function loadRawRecords(rawDir) {
  return readdirSync(rawDir)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => ({
      file: name,
      ...readJson(join(rawDir, name)),
    }));
}

function renderAuditMarkdown(audit, context) {
  const s = audit.summary;
  return `# LinkedIn OpenCLI Media Audit

## 입력

- Compare report: ${context.compareReport}
- Shadow: ${context.shadow}
- Baseline: ${context.baseline}
- Raw dir: ${context.rawDir}

## 요약

| 항목 | 값 |
|---|---:|
| total_mismatch | ${s.total_mismatch} |
| post_media_confirmed | ${s.post_media_confirmed} |
| baseline_missing_media | ${s.baseline_missing_media} |
| actor_image_false_positive | ${s.actor_image_false_positive} |
| article_or_link_thumbnail | ${s.article_or_link_thumbnail} |
| needs_browser_check | ${s.needs_browser_check} |

## 판정

- recommendation: ${audit.decision.recommendation}
- media_risk: ${audit.decision.media_risk}
- reason: ${audit.decision.reason}

## 확인 필요 후보

${audit.items
  .filter((item) => item.label !== "post_media_confirmed")
  .slice(0, 50)
  .map((item) => `- ${item.platform_id}: ${item.label} / ${item.post_url}`)
  .join("\n") || "없음"}
`;
}

function renderSpotcheckMarkdown(sample) {
  const lines = ["# LinkedIn OpenCLI Media Spotcheck", ""];
  lines.push("| platform_id | label | post_url | raw_path | check_result | note |");
  lines.push("|---|---|---|---|---|---|");
  for (const item of sample.items) {
    lines.push(
      `| ${item.platform_id} | ${item.label} | ${item.post_url} | ${item.raw_path} |  |  |`,
    );
  }
  lines.push("");
  return lines.join("\n");
}

function commandAudit(args) {
  const compareReport = args["compare-report"];
  const shadow = args.shadow;
  const baseline = args.baseline;
  const rawDir = args["raw-dir"];
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!compareReport || !shadow || !baseline || !rawDir) {
    throw new Error("audit requires --compare-report, --shadow, --baseline, and --raw-dir");
  }
  const audit = buildMediaAudit({
    compareReport: readJson(compareReport),
    shadowPosts: extractPosts(readJson(shadow)),
    baselinePosts: extractPosts(readJson(baseline)),
    rawRecords: loadRawRecords(rawDir),
  });
  mkdirSync(outDir, { recursive: true });
  const stamp = timestamp();
  const jsonPath = join(outDir, `media_audit_${stamp}.json`);
  const mdPath = join(outDir, `media_audit_${stamp}.md`);
  writeJson(jsonPath, audit);
  writeFileSync(mdPath, renderAuditMarkdown(audit, { compareReport, shadow, baseline, rawDir }), "utf8");
  console.log(JSON.stringify({ json_path: jsonPath, markdown_path: mdPath, ...audit.summary, ...audit.decision }, null, 2));
}

function commandSample(args) {
  const auditPath = args.audit;
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!auditPath) throw new Error("sample requires --audit");
  const perLabel = Number(args["per-label"] || 5);
  const audit = readJson(auditPath);
  const sample = {
    generated_at: new Date().toISOString(),
    audit_path: auditPath,
    per_label: perLabel,
    items: selectSpotcheckSamples(audit, perLabel),
  };
  mkdirSync(outDir, { recursive: true });
  const stamp = timestamp();
  const jsonPath = join(outDir, `media_spotcheck_sample_${stamp}.json`);
  const mdPath = join(outDir, `media_spotcheck_${stamp}.md`);
  writeJson(jsonPath, sample);
  writeFileSync(mdPath, renderSpotcheckMarkdown(sample), "utf8");
  console.log(JSON.stringify({ json_path: jsonPath, markdown_path: mdPath, sample_count: sample.items.length }, null, 2));
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  if (command === "audit") return commandAudit(args);
  if (command === "sample") return commandSample(args);
  throw new Error(`unknown command: ${command || "(missing)"}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
