/**
 * 주소 입력 시 채널 자동 확인 headless 검증. 창을 띄우지 않는다.
 *
 *   V1 올바른 핸들 → 채널명·구독자수가 화면에 뜬다
 *   V2 오타 핸들 → 오류 문구가 뜨고 목록 항목 수가 늘지 않는다
 *   V3 확인을 안 거친 유튜브 주소는 저장되지 않는다 (R7 · SPEC D10)
 *
 * 전부 통과하면 exit 0, 하나라도 실패하면 exit 1.
 * 실행 후 상태를 원래대로 되돌린다.
 *
 * Usage: node scripts/verify_benchmark_handle_check.mjs
 * 계획: _docs/20260906_01 (P4)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startBenchmarkVerifyServer } from './_bench_verify_server.mjs';

// 검증 전용 서버를 띄운다. 운영 5000번과 운영 계정 파일을 건드리지 않는다.
// 계획: _docs/20260906_03 (W2)
const verifyServer = await startBenchmarkVerifyServer();
const BASE_URL = verifyServer.baseUrl;
const ACCOUNTS_PATH = verifyServer.accountsPath;

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const originalAccounts = fs.readFileSync(ACCOUNTS_PATH, 'utf8');
const browser = await launchHeadlessChromium();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // 서버 경로부터 확인한다 - 화면이 못 쓰는 이유가 API 인지 UI 인지 갈라야 한다.
  const api = await page.evaluate(async () => {
    const call = async (handle) => {
      const res = await fetch(`/api/verify-channel?platform=youtube&handle=${encodeURIComponent(handle)}`);
      return res.json();
    };
    return {
      good: await call('@builderjoshkim'),
      bad: await call('@builderjosh_nope_xyz_0906'),
    };
  });
  record('V1 올바른 핸들이 채널명·구독자수·channel_id 를 돌려준다',
    api.good.ok === true && Boolean(api.good.title) && Boolean(api.good.channel_id),
    `${api.good.title} · 구독 ${api.good.subscriber_count} · ${api.good.channel_id}`);
  record('V2 오타 핸들은 not_found 를 돌려준다',
    api.bad.ok === false && api.bad.reason === 'not_found',
    `reason=${api.bad.reason}`);

  // 화면에서 계정을 하나 만들고, 확인을 거치지 않은 주소가 저장되지 않는지 본다.
  const guard = await page.evaluate(async () => {
    const before = await (await fetch('/api/get-benchmark-accounts')).json();
    const beforeCount = (before.accounts || []).length;

    document.getElementById('settingsBtn')?.click();
    await new Promise((r) => setTimeout(r, 400));
    [...document.querySelectorAll('.tab-btn')]
      .find((b) => b.dataset.target === 'tabBenchmark')?.click();
    await new Promise((r) => setTimeout(r, 300));

    const originalPrompt = window.prompt;
    window.prompt = () => '검증용 임시 계정';
    document.getElementById('addBenchmarkBtn')?.click();
    await new Promise((r) => setTimeout(r, 900));
    window.prompt = originalPrompt;

    const row = [...document.querySelectorAll('.bm-account-item')]
      .find((el) => el.textContent.includes('검증용 임시 계정'));
    if (!row) return { error: '임시 계정 행을 못 찾음' };

    const input = row.querySelector('[data-bm-channel="youtube"]');
    if (!input) return { error: '주소 입력칸이 안 펼쳐짐' };
    input.value = '@builderjosh_nope_xyz_0906';
    row.querySelector('[data-bm-action="save"]')?.click();
    await new Promise((r) => setTimeout(r, 700));

    const message = row.querySelector('[data-bm-verify-result]')?.textContent || '';
    const after = await (await fetch('/api/get-benchmark-accounts')).json();
    const saved = (after.accounts || []).find((a) => a.name === '검증용 임시 계정');
    return {
      message,
      savedYoutube: saved?.channels?.youtube ?? null,
      grew: (after.accounts || []).length - beforeCount,
    };
  });

  if (guard.error) {
    record('V3 확인을 안 거친 유튜브 주소는 저장되지 않는다', false, guard.error);
  } else {
    record('V3 확인을 안 거친 유튜브 주소는 저장되지 않는다',
      guard.savedYoutube === null || guard.savedYoutube === undefined,
      `문구="${guard.message}" · 저장된 주소=${guard.savedYoutube}`);
  }
} finally {
  await browser.close();
  fs.writeFileSync(ACCOUNTS_PATH, originalAccounts, 'utf8');
  await verifyServer.stop();
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
