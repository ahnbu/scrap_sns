/**
 * 벤치마킹 LinkedIn 인증 만료가 「업데이트」 결과창까지 도달하는지 화면에서 판정한다.
 * 창을 띄우지 않는다.
 *
 * 종전 결함: `linkedin_scrap_by_user.py` 가 세션 만료 시 맨 `input()` 으로 죽었고,
 * 설령 인증 신호를 냈더라도 `total_scrap` 이 그것을 `bench_linkedin` 이라는 슬롯
 * 이름으로 올려 서버가 통째로 버렸다. 그래서 사용자는 벤치마킹 수집이 멈춘 것을
 * 화면에서 알 방법이 없었다.
 *
 *   V1 서버가 `bench_linkedin` 인증 신호를 `linkedin` 으로 알아본다
 *   V2 벤치마킹 실패가 저장글 결과를 덮어쓰지 않는다 (회귀 방지)
 *   V3 그 신호를 받은 「업데이트」 결과 모달에 LinkedIn 재로그인 안내가 뜬다
 *
 * V3 의 판정 대상은 상단 `#authRequiredPanel` 이 아니라 **결과 모달**이다.
 * 상단 패널은 `?verify_auth_panel=` 쿼리로만 뜨는 검증 전용 경로이고
 * (`getAuthPanelVerifyPlatforms`), 실제 수집 결과의 인증 안내는
 * `buildScrapResultViewModel` 의 `authLabels`·`authPrompt` 가 모달에 렌더한다.
 *
 * 서버가 정규화해 보낸 모양 그대로를 「업데이트」 응답으로 넣어 판정한다. 실제
 * 수집을 돌리지 않는 이유는 그것이 사용자의 LinkedIn 세션을 실제로 만료시켜야만
 * 재현되기 때문이다 - 그 경로는
 * `_docs/evidence/20260908_02/bench_auth_required.log`(종료코드 86)가 증거다.
 *
 * 판정은 사람 눈이 아니라 종료코드다 - 실패 0건이면 0, 아니면 1.
 *
 * Usage: node scripts/verify_benchmark_auth_panel_headless.mjs [--shot-dir <dir>]
 * 계획: _docs/20260908_02 (완료 기준 4)
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startBenchmarkVerifyServer } from './_bench_verify_server.mjs';

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}

const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260908_02'));

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

// --- V1·V2 서버 정규화 -----------------------------------------------------
// 서버 함수를 파이썬 프로세스로 직접 부른다. HTTP 를 태우면 실제 수집이 필요하다.
const pyProbe = `
import io, json, sys
sys.path.insert(0, ".")
import scrap_sns_server as s
auth_only = s._normalize_scrap_summary({
    "auth_required": ["bench_linkedin"],
    "platform_results": {},
})
mixed = s._normalize_scrap_summary({
    "auth_required": [],
    "platform_results": {
        "linkedin": {"status": "ok", "returncode": 0},
        "bench_linkedin": {"status": "failed", "returncode": 1},
    },
})
print("PROBE " + json.dumps({"auth_only": auth_only, "mixed": mixed}, ensure_ascii=False))
`;

const probeRaw = execFileSync('python', ['-c', pyProbe], {
  encoding: 'utf8',
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
});
const probeLine = probeRaw.split(/\r?\n/).find((l) => l.startsWith('PROBE '));
const probe = JSON.parse(probeLine.slice('PROBE '.length));

record(
  'V1 서버가 bench_linkedin 인증 신호를 linkedin 으로 알아본다',
  JSON.stringify(probe.auth_only.auth_required) === JSON.stringify(['linkedin']),
  `auth_required=${JSON.stringify(probe.auth_only.auth_required)}`,
);

record(
  'V2 벤치마킹 실패가 저장글 결과를 덮어쓰지 않는다',
  probe.mixed.platform_results?.linkedin?.status === 'ok'
    && probe.mixed.auth_required.length === 0,
  `linkedin.status=${probe.mixed.platform_results?.linkedin?.status}`
    + ` auth_required=${JSON.stringify(probe.mixed.auth_required)}`,
);

// --- V3 화면 ---------------------------------------------------------------
const verifyServer = await startBenchmarkVerifyServer();
const BASE_URL = verifyServer.baseUrl;

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs',
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const browser = await launchHeadlessChromium();
try {
  fs.mkdirSync(shotDir, { recursive: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // 서버가 정규화해 내보낸 모양 그대로를 「업데이트」 응답으로 흘려 넣는다.
  const normalized = probe.auth_only;
  await page.evaluate((payload) => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (url.includes('/api/run-scrap')) {
        // executeScrap 은 `status === 'success'` 일 때만 결과 모달을 연다.
        return new Response(JSON.stringify({ status: 'success', ...payload }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return original(input, init);
    };
  }, normalized);

  const runBtn = await page.$('#runScrapBtn, [data-role="run-scrap"], button:has-text("업데이트")');
  if (!runBtn) throw new Error('「업데이트」 버튼을 찾지 못했다');
  await runBtn.click();

  await page.waitForSelector('#scrapResultModal:not(.hidden)', { timeout: 30000 })
    .catch(() => null);

  const modal = await page.evaluate(() => {
    const el = document.querySelector('#scrapResultModal');
    if (!el) return { present: false };
    return {
      present: true,
      hidden: el.classList.contains('hidden'),
      text: (el.innerText || '').trim(),
    };
  });

  const mentionsLinkedIn = /linkedin/i.test(modal.text || '');
  const mentionsAuth = /인증|로그인/.test(modal.text || '');

  record(
    'V3 결과 모달에 LinkedIn 재로그인 안내가 뜬다',
    Boolean(modal.present && !modal.hidden && mentionsLinkedIn && mentionsAuth),
    modal.present
      ? `hidden=${modal.hidden} linkedin=${mentionsLinkedIn} auth=${mentionsAuth}`
      : '모달 없음',
  );

  await page.screenshot({
    path: path.join(shotDir, 'v3_auth_modal.png'),
    fullPage: false,
  });
} finally {
  await browser.close();
  await verifyServer.stop();
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} PASS`);
process.exit(failed.length ? 1 : 0);
