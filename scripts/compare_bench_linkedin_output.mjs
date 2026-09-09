/**
 * 프로세스 통합 전후로 수집 결과가 같은지 대조한다.
 *
 * 재구조화(전역 8개 → 생성자 인자, 프로세스 5개 → 1개)가 동작을 바꾸지 않았는지
 * 보는 유일한 기계 판정이다. 사람이 파일을 열어 비교하지 않는다.
 *
 * 판정: 통합 전 수집분의 `code` 집합이 통합 후 집합에 **포함**되면 통과.
 *   「완전 동일」이 아닌 이유: LinkedIn 활동 목록은 시점에 따라 새 글이 는다.
 *   새로 늘어난 code 는 차이로 보지 않고 목록에만 남긴다.
 *
 * Usage:
 *   node scripts/compare_bench_linkedin_output.mjs --baseline <before.json> --current <after.json>
 * 계획: _docs/20260909_01 (W6-5)
 */
import fs from 'node:fs';

const argv = process.argv;
function arg(name) {
  const i = argv.indexOf(name);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : null;
}

const baselinePath = arg('--baseline');
const currentPath = arg('--current');

if (!baselinePath || !currentPath) {
  console.error('Usage: node scripts/compare_bench_linkedin_output.mjs --baseline <file> --current <file>');
  process.exit(2);
}

function readCodes(file) {
  if (!fs.existsSync(file)) {
    console.error(`파일이 없다: ${file}`);
    process.exit(2);
  }
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  const posts = Array.isArray(raw) ? raw : (raw.posts || []);
  return {
    codes: new Set(posts.map((p) => String(p.code || p.platform_id || '')).filter(Boolean)),
    count: posts.length,
  };
}

const before = readCodes(baselinePath);
const after = readCodes(currentPath);

const missing = [...before.codes].filter((code) => !after.codes.has(code));
const added = [...after.codes].filter((code) => !before.codes.has(code));

console.log(`통합 전: ${before.count}건 (${baselinePath})`);
console.log(`통합 후: ${after.count}건 (${currentPath})`);
console.log(`사라진 code: ${missing.length}건${missing.length ? ` — ${missing.slice(0, 10).join(', ')}` : ''}`);
console.log(`새로 늘어난 code: ${added.length}건${added.length ? ` — ${added.slice(0, 10).join(', ')}` : ''}`);

if (missing.length > 0) {
  console.error('\n통합 전 수집분이 통합 후에 없다 — 동작이 바뀌었다');
  process.exit(1);
}
console.log('\n통과: 통합 전 수집분이 전부 남아 있다');
process.exit(0);
