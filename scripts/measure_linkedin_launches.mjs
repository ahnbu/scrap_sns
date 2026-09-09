/**
 * LinkedIn 브라우저 기동 횟수를 로그로 잰다.
 *
 * 창 정책 정본이 기동마다 `LAUNCH: mode=... window=... engine=...` 한 줄을 찍는다
 * (`~/.claude/skills/_shared/browser_launch.py`). 그 줄 수가 곧 기동 횟수다.
 * 사람이 창을 세지 않아도 종료코드로 판정된다.
 *
 * 종전: 저장글 1 + 벤치마킹 계정 5 = 6회 (계정마다 자식 프로세스)
 * 이후: 저장글 1 + 벤치마킹 1 = 2회 (벤치마킹이 브라우저 하나를 공유)
 *
 * 마지막 실행 구간만 센다 - 로그는 append 라 과거 실행분이 함께 쌓여 있다.
 * 구간 경계는 `_write_phase_log_header()` 가 찍는 `🚀 ... 시작:` 줄이다.
 *
 * Usage: node scripts/measure_linkedin_launches.mjs [--expect 2]
 * 계획: _docs/20260909_01 (W6-1)
 */
import fs from 'node:fs';
import path from 'node:path';

const argv = process.argv;
const expectArg = argv.indexOf('--expect');
const EXPECTED = expectArg !== -1 && argv[expectArg + 1] ? Number(argv[expectArg + 1]) : 2;

const LOGS = [
  { slot: '저장글 수집 (LinkedIn)', file: path.join('logs', 'linkedin.log') },
  { slot: '벤치마킹 수집 (BenchLinkedIn)', file: path.join('logs', 'benchlinkedin.log') },
];

function countLastRunLaunches(file) {
  if (!fs.existsSync(file)) return { missing: true, launches: 0, startedAt: null };
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);

  // 마지막 실행 구간의 시작점을 찾는다.
  let start = 0;
  let startedAt = null;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (lines[i].includes('시작:')) {
      start = i;
      startedAt = lines[i].trim();
      break;
    }
  }

  const launches = lines.slice(start).filter((line) => line.startsWith('LAUNCH:'));
  return { missing: false, launches: launches.length, startedAt, samples: launches.slice(0, 3) };
}

let total = 0;
const report = [];
for (const { slot, file } of LOGS) {
  const result = countLastRunLaunches(file);
  total += result.launches;
  report.push({ slot, file, ...result });
  console.log(
    `${slot}: ${result.missing ? '로그 없음' : `${result.launches}회`}` +
    (result.startedAt ? `  (${result.startedAt})` : '')
  );
  (result.samples || []).forEach((line) => console.log(`    ${line}`));
}

console.log(`\n합계 ${total}회 (기대 ${EXPECTED}회)`);

if (report.every((r) => r.missing)) {
  console.error('로그가 없어 판정할 수 없다. 「업데이트」를 한 번 돌린 뒤 다시 실행한다.');
  process.exit(2);
}

if (total !== EXPECTED) {
  console.error(`기동 횟수가 기대와 다르다: ${total} ≠ ${EXPECTED}`);
  process.exit(1);
}
console.log('통과');
process.exit(0);
