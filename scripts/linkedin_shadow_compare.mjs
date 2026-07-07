#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
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

export function getPostId(post) {
  return String(post?.platform_id || post?.code || "").trim();
}

function linkedinOnly(posts) {
  return posts.filter((post) => {
    const platform = String(post?.sns_platform || "").toLowerCase();
    return platform === "linkedin" || String(post?.url || "").includes("linkedin.com/");
  });
}

function byId(posts) {
  const map = new Map();
  for (const post of posts) {
    const id = getPostId(post);
    if (id && !map.has(id)) map.set(id, post);
  }
  return map;
}

function canonicalId(post) {
  return String(
    post?.diagnostics?.canonical_activity_id ||
      post?.canonical_activity_id ||
      post?.diagnostics?.saved_activity_id ||
      post?.platform_id ||
      post?.code ||
      "",
  ).trim();
}

function explicitCanonicalId(post) {
  return String(post?.diagnostics?.canonical_activity_id || post?.canonical_activity_id || "").trim();
}

function mediaCount(post) {
  return Array.isArray(post?.media) ? post.media.length : 0;
}

function significantTextMismatch(a, b) {
  const left = String(a?.full_text || "");
  const right = String(b?.full_text || "");
  if (!left && !right) return false;
  const diff = Math.abs(left.length - right.length);
  const maxLen = Math.max(left.length, right.length, 1);
  return diff > 50 && diff / maxLen > 0.1;
}

export function comparePostSets({ shadowPosts, linkedinFullPosts, totalPosts = [] }) {
  const shadowMap = byId(linkedinOnly(shadowPosts));
  const linkedinMap = byId(linkedinOnly(linkedinFullPosts));
  const totalMap = byId(linkedinOnly(totalPosts));
  const baselineMap = new Map([...totalMap, ...linkedinMap]);

  const shadowIds = new Set(shadowMap.keys());
  const baselineIds = new Set(baselineMap.keys());
  const commonIds = [...shadowIds].filter((id) => baselineIds.has(id)).sort();
  const missingFromShadow = [...baselineIds].filter((id) => !shadowIds.has(id)).sort();
  const shadowOnly = [...shadowIds].filter((id) => !baselineIds.has(id)).sort();

  const textLengthMismatch = [];
  const urlMismatch = [];
  const mediaCountMismatch = [];
  const displayNameMismatch = [];

  for (const id of commonIds) {
    const shadow = shadowMap.get(id);
    const baseline = baselineMap.get(id);
    if (significantTextMismatch(shadow, baseline)) {
      textLengthMismatch.push({
        platform_id: id,
        shadow_length: String(shadow.full_text || "").length,
        baseline_length: String(baseline.full_text || "").length,
      });
    }
    if (String(shadow.url || "") && String(baseline.url || "") && shadow.url !== baseline.url) {
      urlMismatch.push({ platform_id: id, shadow_url: shadow.url, baseline_url: baseline.url });
    }
    if (mediaCount(shadow) !== mediaCount(baseline)) {
      mediaCountMismatch.push({
        platform_id: id,
        shadow_media_count: mediaCount(shadow),
        baseline_media_count: mediaCount(baseline),
      });
    }
    if (
      String(shadow.display_name || "").trim() &&
      String(baseline.display_name || "").trim() &&
      shadow.display_name !== baseline.display_name
    ) {
      displayNameMismatch.push({
        platform_id: id,
        shadow_display_name: shadow.display_name,
        baseline_display_name: baseline.display_name,
      });
    }
  }

  return {
    counts: {
      shadow: shadowMap.size,
      linkedin_full: linkedinMap.size,
      total_linkedin: totalMap.size,
      baseline_unique: baselineMap.size,
      common_ids: commonIds.length,
      missing_from_shadow_candidates: missingFromShadow.length,
      shadow_only_candidates: shadowOnly.length,
    },
    common_ids: commonIds,
    missing_from_shadow_candidates: missingFromShadow,
    shadow_only_candidates: shadowOnly,
    text_length_mismatch: textLengthMismatch,
    url_mismatch: urlMismatch,
    media_count_mismatch: mediaCountMismatch,
    display_name_mismatch: displayNameMismatch,
    go_no_go_recommendation: recommend({
      shadowCount: shadowMap.size,
      textLengthMismatch,
      urlMismatch,
      missingFromShadow,
    }),
  };
}

export function compareCanonicalPostSets({ shadowPosts, baselinePosts }) {
  const shadowLinkedin = linkedinOnly(shadowPosts);
  const baselineLinkedin = linkedinOnly(baselinePosts);
  const shadowById = byId(shadowLinkedin);
  const shadowCanonicalIds = new Set(shadowLinkedin.map(canonicalId).filter(Boolean));

  const baselineOnlyWrapper = [];
  const realOpencliMissing = [];
  const confirmedSavedInOpencli = [];
  const needsRawEvidence = [];

  for (const post of baselineLinkedin) {
    const id = getPostId(post);
    const explicitCanon = explicitCanonicalId(post);
    const canon = explicitCanon || id;
    if (id && shadowById.has(id)) {
      confirmedSavedInOpencli.push({ platform_id: id, canonical_activity_id: canon || id });
      continue;
    }
    if (explicitCanon && explicitCanon !== id && shadowCanonicalIds.has(explicitCanon)) {
      baselineOnlyWrapper.push({
        platform_id: id,
        canonical_activity_id: explicitCanon,
        reason: "canonical_activity_present_in_shadow",
      });
      continue;
    }
    if (!explicitCanon) {
      needsRawEvidence.push({
        platform_id: id,
        canonical_activity_id: id,
        reason: "needs_raw_evidence",
      });
      continue;
    }
    realOpencliMissing.push({
      platform_id: id,
      canonical_activity_id: explicitCanon,
      reason: "canonical_activity_absent_in_shadow",
    });
  }

  const baselineIds = new Set(baselineLinkedin.map(getPostId).filter(Boolean));
  const shadowOnlyConfirmedSaved = shadowLinkedin
    .filter((post) => !baselineIds.has(getPostId(post)))
    .map((post) => ({
      platform_id: getPostId(post),
      canonical_activity_id: canonicalId(post),
      save_state_verified: Boolean(post?.diagnostics?.save_state_verified),
      cluster_reference_verified: Boolean(post?.diagnostics?.cluster_reference_verified),
    }));

  return {
    counts: {
      confirmed_saved_in_opencli: confirmedSavedInOpencli.length,
      baseline_only_wrapper: baselineOnlyWrapper.length,
      needs_raw_evidence: needsRawEvidence.length,
      real_opencli_missing: realOpencliMissing.length,
      shadow_only_confirmed_saved: shadowOnlyConfirmedSaved.length,
    },
    confirmed_saved_in_opencli: confirmedSavedInOpencli,
    baseline_only_unreachable: [],
    baseline_only_wrapper: baselineOnlyWrapper,
    needs_raw_evidence: needsRawEvidence,
    shadow_only_confirmed_saved: shadowOnlyConfirmedSaved,
    real_opencli_missing: realOpencliMissing,
    shadow_diagnostics: shadowLinkedin.map((post) => ({
      platform_id: getPostId(post),
      saved_activity_id: post?.diagnostics?.saved_activity_id || null,
      entity_activity_id: post?.diagnostics?.entity_activity_id || getPostId(post),
      embedded_activity_ids: post?.diagnostics?.embedded_activity_ids || [],
      canonical_activity_id: canonicalId(post),
      save_state_verified: Boolean(post?.diagnostics?.save_state_verified),
      cluster_reference_verified: Boolean(post?.diagnostics?.cluster_reference_verified),
    })),
  };
}

function recommend({ shadowCount, textLengthMismatch, urlMismatch, missingFromShadow }) {
  if (shadowCount === 0) return "no_go";
  if (urlMismatch.length > 0 || textLengthMismatch.length > 0) return "trial_fallback";
  if (missingFromShadow.length > 0) return "trial_fallback";
  return "go";
}

function renderMarkdown(report, context = {}) {
  return `# LinkedIn OpenCLI Shadow 비교 리포트

## 입력

- Shadow: ${context.shadow || "-"}
- LinkedIn full: ${context.linkedinFull || "-"}
- Total full: ${context.totalFull || "-"}

## 요약

| 항목 | 값 |
|---|---:|
| shadow 고유 ID | ${report.counts.shadow} |
| LinkedIn full 고유 ID | ${report.counts.linkedin_full} |
| total LinkedIn 고유 ID | ${report.counts.total_linkedin} |
| 기준 고유 ID | ${report.counts.baseline_unique} |
| 공통 ID | ${report.counts.common_ids} |
| shadow 누락 후보 | ${report.counts.missing_from_shadow_candidates} |
| shadow-only 후보 | ${report.counts.shadow_only_candidates} |
| 본문 길이 차이 | ${report.text_length_mismatch.length} |
| URL 차이 | ${report.url_mismatch.length} |
| media 수 차이 | ${report.media_count_mismatch.length} |

## 판정

${report.go_no_go_recommendation}

## 누락 후보

${report.missing_from_shadow_candidates.slice(0, 100).map((id) => `- ${id}`).join("\n") || "없음"}

## Shadow-only 후보

${report.shadow_only_candidates.slice(0, 100).map((id) => `- ${id}`).join("\n") || "없음"}
`;
}

function commandBaseline(args) {
  const linkedinFull = args["linkedin-full"];
  const totalFull = args["total-full"];
  const outDir = args.out || "output_linkedin/opencli_shadow/baseline";
  const linkedinPosts = linkedinFull && existsSync(linkedinFull) ? extractPosts(readJson(linkedinFull)) : [];
  const totalPosts = totalFull && existsSync(totalFull) ? extractPosts(readJson(totalFull)) : [];
  const payload = {
    generated_at: new Date().toISOString(),
    linkedin_full_path: linkedinFull || "",
    total_full_path: totalFull || "",
    linkedin_full_count: linkedinOnly(linkedinPosts).length,
    total_linkedin_count: linkedinOnly(totalPosts).length,
    unique_platform_ids: new Set([
      ...linkedinOnly(linkedinPosts).map(getPostId).filter(Boolean),
      ...linkedinOnly(totalPosts).map(getPostId).filter(Boolean),
    ]).size,
  };
  mkdirSync(outDir, { recursive: true });
  const outPath = join(outDir, `baseline_inventory_${timestamp()}.json`);
  writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ output_path: outPath, ...payload }, null, 2));
}

function commandCompare(args) {
  const shadowPath = args.shadow;
  const linkedinFull = args["linkedin-full"];
  const totalFull = args["total-full"];
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!shadowPath || !linkedinFull) {
    throw new Error("compare requires --shadow and --linkedin-full");
  }
  const report = comparePostSets({
    shadowPosts: extractPosts(readJson(shadowPath)),
    linkedinFullPosts: extractPosts(readJson(linkedinFull)),
    totalPosts: totalFull && existsSync(totalFull) ? extractPosts(readJson(totalFull)) : [],
  });
  mkdirSync(outDir, { recursive: true });
  const stamp = timestamp();
  const jsonPath = join(outDir, `linkedin_opencli_shadow_compare_${stamp}.json`);
  const mdPath = join(outDir, `linkedin_opencli_shadow_compare_${stamp}.md`);
  writeFileSync(jsonPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  writeFileSync(mdPath, renderMarkdown(report, { shadow: shadowPath, linkedinFull, totalFull }), "utf8");
  console.log(JSON.stringify({ json_path: jsonPath, markdown_path: mdPath, ...report.counts }, null, 2));
}

function commandLabelMissing(args) {
  const reportPath = args.report;
  if (!reportPath) throw new Error("label-missing requires --report");
  const report = readJson(reportPath);
  const sampleSize = Number(args["sample-size"] || 20);
  const labels = report.missing_from_shadow_candidates.slice(0, sampleSize).map((id) => ({
    platform_id: id,
    label: "needs_manual_check",
  }));
  console.log(JSON.stringify({ sampled: labels.length, labels }, null, 2));
}

function commandSample(args) {
  const reportPath = args.report;
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!reportPath) throw new Error("sample requires --report");
  const report = readJson(reportPath);
  const payload = {
    common: report.common_ids.slice(0, Number(args.common || 10)),
    missing: report.missing_from_shadow_candidates.slice(0, Number(args.missing || 10)),
    shadow_only: report.shadow_only_candidates.slice(0, Number(args["shadow-only"] || 10)),
  };
  mkdirSync(outDir, { recursive: true });
  const outPath = join(outDir, `manual_spotcheck_sample_${timestamp()}.json`);
  writeJson(outPath, payload);
  console.log(JSON.stringify({ output_path: outPath, ...payload }, null, 2));
}

function commandSpotcheckTemplate(args) {
  const samplePath = args.sample;
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!samplePath) throw new Error("spotcheck-template requires --sample");
  const sample = readJson(samplePath);
  const lines = ["# LinkedIn Shadow 수동 샘플 검증", ""];
  for (const group of ["common", "missing", "shadow_only"]) {
    lines.push(`## ${group}`, "");
    lines.push("| platform_id | check_result | note |");
    lines.push("|---|---|---|");
    for (const id of sample[group] || []) {
      lines.push(`| ${id} |  |  |`);
    }
    lines.push("");
  }
  mkdirSync(outDir, { recursive: true });
  const outPath = join(outDir, `manual_spotcheck_${timestamp()}.md`);
  writeFileSync(outPath, `${lines.join("\n")}\n`, "utf8");
  console.log(JSON.stringify({ output_path: outPath }, null, 2));
}

function commandCompareShadowRuns(args) {
  const a = extractPosts(readJson(args.a));
  const b = extractPosts(readJson(args.b));
  const aMap = byId(a);
  const bMap = byId(b);
  const report = {
    run_a_only: [...aMap.keys()].filter((id) => !bMap.has(id)).sort(),
    run_b_only: [...bMap.keys()].filter((id) => !aMap.has(id)).sort(),
    common_ids: [...aMap.keys()].filter((id) => bMap.has(id)).sort(),
  };
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  mkdirSync(outDir, { recursive: true });
  const outPath = join(outDir, `compare_shadow_runs_${timestamp()}.json`);
  writeJson(outPath, report);
  console.log(JSON.stringify({ output_path: outPath, ...report }, null, 2));
}

function commandCanonicalCompare(args) {
  const shadowPath = args.shadow;
  const linkedinFull = args["linkedin-full"];
  const totalFull = args["total-full"];
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  if (!shadowPath || !linkedinFull) {
    throw new Error("canonical-compare requires --shadow and --linkedin-full");
  }
  const linkedinPosts = extractPosts(readJson(linkedinFull));
  const totalPosts = totalFull && existsSync(totalFull) ? extractPosts(readJson(totalFull)) : [];
  const baselineMap = byId([...linkedinOnly(totalPosts), ...linkedinOnly(linkedinPosts)]);
  const report = compareCanonicalPostSets({
    shadowPosts: extractPosts(readJson(shadowPath)),
    baselinePosts: [...baselineMap.values()],
  });
  mkdirSync(outDir, { recursive: true });
  const stamp = timestamp();
  const jsonPath = join(outDir, `canonical_compare_${stamp}.json`);
  const mdPath = join(outDir, `canonical_compare_${stamp}.md`);
  writeJson(jsonPath, report);
  const body = `# LinkedIn OpenCLI Canonical 비교 리포트

## 요약

| 항목 | 값 |
|---|---:|
| confirmed_saved_in_opencli | ${report.counts.confirmed_saved_in_opencli} |
| baseline_only_wrapper | ${report.counts.baseline_only_wrapper} |
| needs_raw_evidence | ${report.counts.needs_raw_evidence} |
| shadow_only_confirmed_saved | ${report.counts.shadow_only_confirmed_saved} |
| real_opencli_missing | ${report.counts.real_opencli_missing} |

## baseline_only_wrapper

${report.baseline_only_wrapper.map((item) => `- ${item.platform_id} -> ${item.canonical_activity_id}`).join("\n") || "없음"}

## needs_raw_evidence

${report.needs_raw_evidence.slice(0, 100).map((item) => `- ${item.platform_id} (${item.reason})`).join("\n") || "없음"}

## real_opencli_missing

${report.real_opencli_missing.slice(0, 100).map((item) => `- ${item.platform_id} (${item.reason})`).join("\n") || "없음"}
`;
  writeFileSync(mdPath, body, "utf8");
  console.log(JSON.stringify({ json_path: jsonPath, markdown_path: mdPath, ...report.counts }, null, 2));
}

function commandDecision(args) {
  const compareReport = readJson(args["compare-report"]);
  const repeatReport = args["repeat-report"] && existsSync(args["repeat-report"])
    ? readJson(args["repeat-report"])
    : null;
  const outDir = args.out || "output_linkedin/opencli_shadow/reports";
  const decision = compareReport.go_no_go_recommendation || "no_go";
  const body = `# LinkedIn OpenCLI Shadow Go / No-Go

## Decision

${decision}

## 근거

- shadow 고유 ID: ${compareReport.counts?.shadow ?? 0}
- 누락 후보: ${compareReport.counts?.missing_from_shadow_candidates ?? 0}
- shadow-only 후보: ${compareReport.counts?.shadow_only_candidates ?? 0}
- 반복 실행 차이: ${repeatReport ? `${repeatReport.run_a_only.length + repeatReport.run_b_only.length}` : "미실행"}
`;
  mkdirSync(outDir, { recursive: true });
  const outPath = join(outDir, `go_no_go_${timestamp()}.md`);
  writeFileSync(outPath, body, "utf8");
  console.log(JSON.stringify({ output_path: outPath, decision }, null, 2));
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  if (command === "baseline") return commandBaseline(args);
  if (command === "compare") return commandCompare(args);
  if (command === "label-missing") return commandLabelMissing(args);
  if (command === "sample") return commandSample(args);
  if (command === "spotcheck-template") return commandSpotcheckTemplate(args);
  if (command === "compare-shadow-runs") return commandCompareShadowRuns(args);
  if (command === "canonical-compare") return commandCanonicalCompare(args);
  if (command === "decision") return commandDecision(args);
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
