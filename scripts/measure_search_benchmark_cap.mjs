/**
 * 검색 상한 안에 들어오는 「내 저장글」 수를 변경 전후로 잰다.
 *
 * 「저장」 버튼이 생기면서 검색의 기본이 「벤치마킹 포함」으로 바뀌었다.
 * 서버는 상한으로 자르기 **전에** 거르므로, 포함으로 바뀌면 흔한 검색어에서
 * 내 저장글이 상한 밖으로 밀릴 수 있다. 그 양을 수치로 남긴다.
 *
 * 🔴 같은 상한에서 「포함 vs 제외」를 비교하면 안 된다. 벤치마킹이 일치 결과의
 *    일정 비율을 차지하므로 상한을 아무리 올려도 그 비교는 늘 음수다
 *    (실측 2026-09-09: 상한 500 에서 -24.8% · 상한 800 에서 -16.0%).
 *    사용자가 겪는 변화는 「변경 전 동작」 대 「변경 후 동작」이다.
 *
 *   before   = 상한 500 · 벤치마킹 제외 (변경 전)
 *   after    = 상한 800 · 벤치마킹 포함 (변경 후)
 *   same_cap = 상한 500 · 벤치마킹 포함 (상한을 안 올렸다면)
 *
 * 판정: after 가 before 보다 5% 이상 줄면 상한을 더 올릴지 다시 본다.
 *
 * Usage: node scripts/measure_search_benchmark_cap.mjs [--queries AI,claude] [--limit 800] [--out <file>]
 * 계획: _docs/20260909_01 (W3-4, V4, 위험 7)
 */
import fs from 'node:fs';
import path from 'node:path';

import { getJson } from './_json_http.mjs';

const BASE_URL = process.env.SNS_VIEWER_URL || 'http://localhost:5000';
const BASELINE_LIMIT = 500;
const THRESHOLD_PCT = -5;

const argv = process.argv;
const queriesArg = argv.indexOf('--queries');
const queries = queriesArg !== -1 && argv[queriesArg + 1]
  ? argv[queriesArg + 1].split(',').map((q) => q.trim()).filter(Boolean)
  : ['AI', 'claude'];

const limitArg = argv.indexOf('--limit');
const LIMIT = limitArg !== -1 && argv[limitArg + 1] ? Number(argv[limitArg + 1]) : 800;

const outArg = argv.indexOf('--out');
const outPath = outArg !== -1 && argv[outArg + 1]
  ? argv[outArg + 1]
  : path.join('_docs', 'evidence', '20260909_01', 'search_cap_metrics.txt');

async function savedCountInCap(query, includeBenchmark, limit) {
  const params = new URLSearchParams({
    q: query,
    platform: 'all',
    limit: String(limit),
    include_benchmark: includeBenchmark ? 'true' : 'false',
  });
  const res = await getJson(`${BASE_URL}/api/search?${params}`);
  if (res.status !== 200) throw new Error(`search failed: ${res.status}`);
  const data = res.json || {};
  const posts = data.posts || [];
  return {
    // 상한 안에 들어온 「내 저장글」 수. 이 값이 사용자가 실제로 보는 양이다.
    saved: posts.filter((p) => p.is_saved !== false && p.is_own_post !== true).length,
    returned: posts.length,
    totalMatched: data.total_matched,
  };
}

const rows = [];
let needsMoreHeadroom = false;

for (const query of queries) {
  const before = await savedCountInCap(query, false, BASELINE_LIMIT);
  const after = await savedCountInCap(query, true, LIMIT);
  const sameCap = await savedCountInCap(query, true, BASELINE_LIMIT);
  const deltaPct = before.saved === 0
    ? 0
    : ((after.saved - before.saved) / before.saved) * 100;
  if (deltaPct <= THRESHOLD_PCT) needsMoreHeadroom = true;
  rows.push({
    query,
    before: before.saved,
    after: after.saved,
    sameCap: sameCap.saved,
    deltaPct: Number(deltaPct.toFixed(2)),
    beforeMatched: before.totalMatched,
    afterMatched: after.totalMatched,
  });
}

const stamp = new Date().toISOString();
const lines = [
  '# 검색 상한 안에 들어오는 「내 저장글」 수 — 변경 전후 비교',
  `# 측정 ${stamp} · 판정 기준 ${THRESHOLD_PCT}%`,
  `# before   = 상한 ${BASELINE_LIMIT} · 벤치마킹 제외 (변경 전 동작)`,
  `# after    = 상한 ${LIMIT} · 벤치마킹 포함 (변경 후 동작)`,
  `# same_cap = 상한 ${BASELINE_LIMIT} · 벤치마킹 포함 (상한을 안 올렸다면)`,
  '# query\tbefore\tafter\tsame_cap\tdelta_pct\tlimit_raised',
  ...rows.map((r) => `${r.query}\t${r.before}\t${r.after}\t${r.sameCap}\t${r.deltaPct}\t${LIMIT > BASELINE_LIMIT ? 'yes' : 'no'}`),
  `# 전체 일치 건수: ${rows.map((r) => `${r.query} ${r.beforeMatched}→${r.afterMatched}`).join(' · ')}`,
  `# 판정: ${needsMoreHeadroom
    ? `변경 후가 변경 전보다 ${THRESHOLD_PCT}% 이상 줄었다 → 상한을 더 올릴지 다시 본다`
    : '변경 전보다 줄지 않았다 → 상한을 더 올리지 않는다'}`,
];

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, lines.join('\n') + '\n', 'utf8');

console.log(lines.join('\n'));
console.log(`\n기록: ${outPath}`);

if (!fs.existsSync(outPath)) {
  console.error('측정 파일을 남기지 못했다');
  process.exit(1);
}
process.exit(0);
