/**
 * 벤치마킹 수집이 「업데이트」로 실제 갱신됐는지 화면에서 판정한다. 창을 띄우지 않는다.
 *
 * 종전 결함: 수집기 3개가 어디서도 호출되지 않아 2026-09-06 에 손으로 돌린
 * 파일이 매번 다시 병합되고 있었다. 화면에는 글이 보여서 멈춘 것이 드러나지
 * 않았고, 계정 카드의 「최근」 날짜도 갱신되지 않아 알아챌 단서가 없었다.
 *
 *   V1 기준일 뒤에 게시된 벤치마킹 글이 뷰어 API 로 조회된다 (수집이 살아 있다)
 *   V2 벤치마킹을 켜면 그 글이 화면에 있다 (배지 카드 1건 이상)
 *   V3 활성 계정 카드의 「최근」 날짜 == benchmark_accounts.json 의 last_saved_at
 *      이고, 기준일(2026-09-06)보다 뒤다
 *
 * V1 을 「상단 총건수 == total_count」로 잡지 않는다. 뷰어 상단 숫자는 저장글만
 * 세고(scrap_sns_server 가 is_saved=False 를 기본 제외한다) 통합본 total_count 와
 * 애초에 다른 값이다 - 그렇게 잡으면 정상 상태에서도 FAIL 이 난다.
 * 화면 카드 수와 API 기대값의 일치는 verify_benchmark_mainview.mjs(M10·M11)가
 * 이미 본다. 여기서 볼 것은 「갱신됐는가」다.
 *
 * 판정은 사람 눈이 아니라 종료코드다 - 실패 0건이면 0, 아니면 1.
 * 캡처는 보조 증거일 뿐 판정에 쓰지 않는다.
 *
 * Usage: node scripts/verify_benchmark_refresh_headless.mjs [--shot-dir <dir>] [--since YYYY-MM-DD]
 * 계획: _docs/20260908_01 (완료 기준 4)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startBenchmarkVerifyServer } from './_bench_verify_server.mjs';

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}

const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260908_01'));
// 이 날짜 이후로 갱신됐어야 한다. 수집이 멈춰 있던 마지막 날이다.
const SINCE = arg('--since', '2026-09-06');

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

/** 최신 `output_total/total_full_YYYYMMDD.json`. 파일명 날짜로 고른다. */
function latestTotalFile() {
  const dir = 'output_total';
  const files = fs
    .readdirSync(dir)
    .filter((name) => /^total_full_\d{8}\.json$/.test(name))
    .sort();
  return files.length ? path.join(dir, files[files.length - 1]) : null;
}

const verifyServer = await startBenchmarkVerifyServer();
const BASE_URL = verifyServer.baseUrl;
const ACCOUNTS_PATH = verifyServer.accountsPath;

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
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

  // --- V1 갱신된 벤치마킹 글이 뷰어까지 도달했다 ---------------------------
  const totalPath = latestTotalFile();
  const totalPosts = totalPath ? readJson(totalPath)?.posts || [] : [];
  const freshInFile = totalPosts.filter(
    (p) => (p?.benchmark_accounts || []).length && String(p?.date || '').slice(0, 10) > SINCE
  );
  const freshCodes = new Set(
    freshInFile.map((p) => String(p.code || p.platform_id)).filter(Boolean)
  );
  const seenInApi = await page.evaluate(async (codes) => {
    const res = await fetch('/api/posts?limit=100000');
    const posts = (await res.json()).posts || [];
    const want = new Set(codes);
    return posts.filter((p) => want.has(String(p.code || p.platform_id))).length;
  }, [...freshCodes]);
  record(
    'V1 기준일 뒤에 게시된 벤치마킹 글이 뷰어 API 로 조회된다',
    freshCodes.size > 0 && seenInApi > 0,
    `${path.basename(totalPath || '(없음)')} 에 ${freshCodes.size}건(${SINCE} 이후)`
      + ` · 뷰어 API 에서 ${seenInApi}건 확인`
  );

  // --- V2 벤치마킹 글이 화면에 있다 ----------------------------------------
  await page.click('#benchmarkBtn');
  await page.waitForTimeout(700);
  const onState = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.glass-card')];
    return {
      cards: cards.length,
      withBadge: cards.filter((c) => c.querySelector('[data-benchmark-mark]')).length,
    };
  });
  record(
    'V2 벤치마킹을 켜면 그 글이 화면에 있다',
    onState.withBadge > 0 && onState.cards === onState.withBadge,
    `카드 ${onState.cards}개 중 벤치마킹 ${onState.withBadge}개`
  );
  await page.screenshot({ path: path.join(shotDir, 'V2_benchmark_on.png') });
  await page.click('#benchmarkBtn');
  await page.waitForTimeout(400);

  // --- V3 계정 카드의 「최근」 날짜 -----------------------------------------
  const accounts = readJson(ACCOUNTS_PATH)?.accounts || [];
  const active = accounts.filter(
    (a) => a?.status === 'active' && a?.last_saved_at
  );
  const expectedByName = {};
  active.forEach((a) => {
    expectedByName[String(a.name || a.id)] = String(a.last_saved_at);
  });

  await page.click('#settingsBtn').catch(() => {});
  await page.waitForTimeout(600);
  // 탭 버튼은 `data-target="tabBenchmark"` 다(index.html:548).
  const openedBenchmarkTab = await page.evaluate(() => {
    const tab = document.getElementById('tabBtnBenchmark')
      || document.querySelector('[data-target="tabBenchmark"]');
    if (!tab) return false;
    tab.click();
    return true;
  });
  await page.waitForTimeout(900);

  const shownDates = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.bm-account-item')];
    return rows.map((row) => ({
      name: row.querySelector('.bm-account-name')?.textContent?.trim() || '',
      sub: row.querySelector('.bm-account-sub')?.textContent?.trim() || '',
    }));
  });
  await page.screenshot({ path: path.join(shotDir, 'V3_benchmark_tab.png') });

  const mismatched = [];
  let compared = 0;
  shownDates.forEach((row) => {
    const expected = expectedByName[row.name];
    if (!expected) return;
    compared += 1;
    if (!row.sub.includes(expected)) {
      mismatched.push(`${row.name}: 화면 "${row.sub}" ≠ ${expected}`);
    }
  });
  const newest = active
    .map((a) => String(a.last_saved_at))
    .sort()
    .pop() || '';

  record(
    'V3 계정 카드의 「최근」 날짜가 파일과 일치하고 갱신돼 있다',
    openedBenchmarkTab && compared > 0 && mismatched.length === 0 && newest > SINCE,
    `대조 ${compared}건 · 불일치 ${mismatched.length}건 · 최신 ${newest || '(없음)'} (기준 ${SINCE})`
      + (mismatched.length ? ` — ${mismatched.slice(0, 3).join(' | ')}` : '')
  );
} finally {
  await browser.close();
  await verifyServer.stop();
}

const failed = checks.filter((c) => !c.ok);
console.log(
  failed.length
    ? `\n❌ ${failed.length}건 실패: ${failed.map((c) => c.name).join(', ')}`
    : `\n✅ ${checks.length}건 모두 통과`
);
process.exit(failed.length ? 1 : 0);
