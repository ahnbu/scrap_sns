/**
 * Settings 「벤치마킹」 탭 headless 검증. 창을 띄우지 않는다.
 *
 * 사용자가 하는 순서 그대로 수행하고 각 항목을 assert 한다.
 * 전부 통과하면 exit 0, 하나라도 실패하면 실패 항목명을 찍고 exit 1.
 *
 *   V1 탭이 있고 눌러서 열린다
 *   V2 「수집 대상」/「후보」가 구분돼 보이고 후보는 접혀 있다
 *   V3 계정을 켜면 저장되고, 새로고침해도 유지된다
 *   V4 끄기 경고 문구의 N 이 실제 숫자다
 *   V5 「뺌」이 후보 목록에서 사라진다
 *   V6 「제외한 계정」에서 되돌릴 수 있다
 *   V7 콘솔 에러가 없다
 *
 * 실행 후 상태를 원래대로 되돌린다 - 검증이 데이터를 바꿔놓으면 안 된다.
 *
 * Usage: node scripts/verify_benchmark_settings_headless.mjs [--shot-dir <dir>]
 * 계획: _docs/20260906_01 (P3)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const ACCOUNTS_PATH = path.join('web_viewer', 'benchmark_accounts.json');

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}

const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260906_01'));
const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

// 원본 보존 — 검증이 끝나면 되돌린다.
const originalAccounts = fs.readFileSync(ACCOUNTS_PATH, 'utf8');

const browser = await launchHeadlessChromium();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  const openBenchmarkTab = async () => {
    await page.evaluate(() => {
      document.getElementById('settingsBtn')?.click();
    });
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('.tab-btn')]
        .find((b) => b.dataset.target === 'tabBenchmark');
      btn?.click();
    });
    await page.waitForTimeout(400);
  };

  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });
  await openBenchmarkTab();

  // V1 탭 존재·열림
  const tabState = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('.tab-btn')]
      .find((b) => b.dataset.target === 'tabBenchmark');
    const pane = document.getElementById('tabBenchmark');
    return {
      label: btn?.textContent.trim() || null,
      visible: pane ? !pane.classList.contains('hidden') : false,
    };
  });
  record('V1 벤치마킹 탭이 열린다', Boolean(tabState.label) && tabState.visible,
    `라벨="${tabState.label}"`);

  // V2 섹션 구분 + 후보 접힘
  const sections = await page.evaluate(() => {
    const titles = [...document.querySelectorAll('#benchmarkAccountList .bm-section-title')]
      .map((el) => el.textContent.trim());
    return {
      titles,
      rows: document.querySelectorAll('#benchmarkAccountList .bm-account-item').length,
    };
  });
  const hasTarget = sections.titles.some((t) => t.startsWith('수집 대상'));
  const candidateTitle = sections.titles.find((t) => t.startsWith('후보')) || '';
  record('V2 대상/후보가 구분되고 후보는 접혀 있다',
    hasTarget && candidateTitle.includes('▸'),
    `${sections.titles.join(' | ')} · 펼쳐진 행 ${sections.rows}개`);

  // V3 켜기 → 저장 → 새로고침 후 유지
  const target = await page.evaluate(() => {
    const row = document.querySelector('#benchmarkAccountList .bm-account-item');
    if (!row) return null;
    const box = row.querySelector('[data-bm-action="toggle"]');
    return { id: row.dataset.bmId, wasChecked: box?.checked ?? null };
  });
  if (!target) {
    record('V3 계정 켜기가 저장된다', false, '계정 행이 하나도 없다');
  } else {
    // 켜져 있으면 confirm 이 뜨므로 항상 수락한다.
    page.on('dialog', (dialog) => dialog.accept());
    await page.evaluate((id) => {
      const row = document.querySelector(`[data-bm-id="${id}"]`);
      row?.querySelector('[data-bm-action="toggle"]')?.click();
    }, target.id);
    await page.waitForTimeout(900);

    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForSelector('.glass-card', { timeout: 60000 });
    await openBenchmarkTab();

    const persisted = await page.evaluate(async (id) => {
      const res = await fetch('/api/get-benchmark-accounts');
      const data = await res.json();
      return (data.accounts || []).find((a) => a.id === id)?.status ?? null;
    }, target.id);
    const expected = target.wasChecked ? 'off' : 'active';
    record('V3 계정 켜기/끄기가 저장되고 새로고침 후에도 유지된다',
      persisted === expected, `기대 ${expected} · 실제 ${persisted}`);
  }

  // V4 끄기 경고 숫자가 실제 숫자와 같다
  const warning = await page.evaluate(async () => {
    const res = await fetch('/api/get-benchmark-accounts');
    const accounts = (await res.json()).accounts || [];
    const active = accounts.find((a) => a.status === 'active');
    if (!active) return { skipped: true };

    const postsRes = await fetch('/api/posts');
    const posts = (await postsRes.json()).posts || [];
    const expected = posts.filter(
      (p) => p.is_saved === false && (p.benchmark_accounts || []).includes(active.id)
    ).length;

    let captured = null;
    const originalConfirm = window.confirm;
    window.confirm = (message) => { captured = message; return false; };
    const row = document.querySelector(`[data-bm-id="${active.id}"]`);
    row?.querySelector('[data-bm-action="toggle"]')?.click();
    window.confirm = originalConfirm;

    const match = captured && captured.match(/(\d+)건이 안 보이게/);
    return { expected, shown: match ? Number(match[1]) : null, captured };
  });
  if (warning.skipped) {
    record('V4 끄기 경고에 실제 숫자가 들어간다', false, '켜진 계정이 없어 확인 불가');
  } else {
    record('V4 끄기 경고에 실제 숫자가 들어간다',
      warning.shown === warning.expected,
      `기대 ${warning.expected} · 문구 ${warning.shown}`);
  }

  // V5·V6 뺌 → 후보에서 사라짐 → 되돌리기
  const excludeFlow = await page.evaluate(async () => {
    const listOf = () => [...document.querySelectorAll('#benchmarkAccountList .bm-account-item')]
      .map((el) => el.dataset.bmId);

    // 후보 섹션을 펼쳐 대상 하나를 고른다.
    const heading = [...document.querySelectorAll('[data-bm-section]')][0];
    heading?.click();
    await new Promise((resolve) => setTimeout(resolve, 300));

    const before = listOf();
    const victim = before[before.length - 1];
    if (!victim) return { skipped: true };

    const originalConfirm = window.confirm;
    window.confirm = () => true;
    document.querySelector(`[data-bm-id="${victim}"] [data-bm-action="exclude"]`)?.click();
    await new Promise((resolve) => setTimeout(resolve, 900));
    const afterExclude = listOf();

    // 「제외한 계정」을 켜고 되돌린다.
    document.getElementById('toggleExcludedBtn')?.click();
    await new Promise((resolve) => setTimeout(resolve, 300));
    document.querySelector(`[data-bm-id="${victim}"] [data-bm-action="restore"]`)?.click();
    await new Promise((resolve) => setTimeout(resolve, 900));
    window.confirm = originalConfirm;

    const res = await fetch('/api/get-benchmark-accounts');
    const restored = ((await res.json()).accounts || []).find((a) => a.id === victim)?.status;
    return {
      victim,
      disappeared: !afterExclude.includes(victim),
      restored,
    };
  });
  if (excludeFlow.skipped) {
    record('V5 「뺌」이 후보 목록에서 사라진다', false, '후보 행이 없어 확인 불가');
    record('V6 「제외한 계정」에서 되돌릴 수 있다', false, '확인 불가');
  } else {
    record('V5 「뺌」이 후보 목록에서 사라진다', excludeFlow.disappeared, excludeFlow.victim);
    record('V6 「제외한 계정」에서 되돌릴 수 있다',
      excludeFlow.restored === 'off', `복구 후 status=${excludeFlow.restored}`);
  }

  record('V7 콘솔 에러가 없다', consoleErrors.length === 0,
    consoleErrors.slice(0, 3).join(' | '));

  fs.mkdirSync(shotDir, { recursive: true });
  await page.screenshot({ path: path.join(shotDir, 'p3_benchmark_tab.png') });
  console.log(`shot: ${path.join(shotDir, 'p3_benchmark_tab.png')}`);
} finally {
  await browser.close();
  // 검증이 바꾼 상태를 되돌린다.
  fs.writeFileSync(ACCOUNTS_PATH, originalAccounts, 'utf8');
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
