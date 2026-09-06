/**
 * 메인 화면에서 벤치마킹을 실제로 쓸 수 있는지 검증. 창을 띄우지 않는다.
 *
 * 종전 결함: 토글이 Settings 안에만 있어 메인 화면에서 안 보였고, 켜도
 * 남의 글이 한 덩어리로 섞일 뿐 계정별로 볼 수단이 없었다.
 *
 *   M1 메인 화면에 「벤치마킹」 버튼이 보인다
 *   M2 누르면 남의 계정 글만 남는다 (내 저장글 0건)
 *   M3 계정 칩 줄이 나오고 켜진 계정 + 건수가 보인다
 *   M4 계정 칩을 누르면 그 계정 글만 남는다
 *   M5 카드 배지를 누르면 그 계정만 보기로 좁혀진다
 *   M6 MY 와 상호 배타다 (둘 다 켜서 0건이 되지 않는다)
 *   M7 끄면 원래 화면으로 돌아온다
 *   M8 켠 계정이 없으면 안내 문구가 나온다
 *
 * W1(_docs/20260906_03) 로 아래가 붙었다. 겹친 글이 벤치마킹 뷰에서만
 * 사라지던 결함의 회귀 가드다.
 *
 *   M9  겹침이 전부인 계정도 칩에 나온다 (장피엠 5)
 *   M10 칩 숫자 합계 == API 기대값
 *   M11 렌더 카드 수 == API 기대값
 *   M12 별표·메모 건수가 실행 전후 같다
 *
 * Usage: node scripts/verify_benchmark_mainview.mjs [--shot-dir <dir>]
 * 계획: _docs/20260906_01 (P9), _docs/20260906_03 (W1)
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
const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260906_03', 'mainview'));
const METADATA_PATH = path.join('web_viewer', 'sns_user_metadata.json');

/** 별표·메모 항목 수. W1 이 사용자 상태를 안 건드리는지 보는 값이다. */
function readUserStateCounts() {
  try {
    const raw = JSON.parse(fs.readFileSync(METADATA_PATH, 'utf8').replace(/^﻿/, ''));
    const entries = Object.values(raw?.posts || raw || {});
    let starred = 0;
    let memo = 0;
    entries.forEach((entry) => {
      if (!entry || typeof entry !== 'object') return;
      if (entry.starred || entry.favorite || entry.is_starred) starred += 1;
      if (typeof entry.memo === 'string' && entry.memo.trim()) memo += 1;
    });
    return { starred, memo };
  } catch {
    return null;
  }
}

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
const stateBefore = readUserStateCounts();
const browser = await launchHeadlessChromium();
try {
  fs.mkdirSync(shotDir, { recursive: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  const snapshot = () => page.evaluate(() => {
    const cards = [...document.querySelectorAll('.glass-card')];
    return {
      cards: cards.length,
      benchmarkBadges: document.querySelectorAll('[data-benchmark-badge]').length,
      chips: [...document.querySelectorAll('.benchmark-chip')].map((c) => c.textContent.trim()),
      activeChip: document.querySelector('.benchmark-chip.active')?.textContent.trim() || null,
      hint: document.querySelector('.benchmark-chip-hint')?.textContent.trim() || null,
      btnActive: document.getElementById('benchmarkBtn')?.classList.contains('active') ?? null,
      myActive: document.getElementById('myPostsBtn')?.classList.contains('active') ?? null,
    };
  });

  // M1 버튼이 메인 화면에 보인다
  const btn = await page.evaluate(() => {
    const el = document.getElementById('benchmarkBtn');
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return { label: el.textContent.trim(), w: Math.round(rect.width), visible: rect.width > 0 && rect.height > 0 };
  });
  record('M1 메인 화면에 「벤치마킹」 버튼이 보인다',
    Boolean(btn && btn.visible), btn ? `"${btn.label}" ${btn.w}px` : '버튼 없음');
  await page.screenshot({ path: path.join(shotDir, 'M1_default.png') });

  // M8 먼저: 켠 계정이 있는 상태인지 확인
  const before = await snapshot();

  // M2 버튼을 누르면 남의 계정 글만
  await page.click('#benchmarkBtn');
  await page.waitForTimeout(700);
  const onlyState = await page.evaluate(async () => {
    // 화면에 렌더된 카드가 전부 벤치마킹 글인지 본다.
    const cards = [...document.querySelectorAll('.glass-card')];
    const withBadge = cards.filter((c) => c.querySelector('[data-benchmark-badge]')).length;
    return { cards: cards.length, withBadge };
  });
  record('M2 누르면 남의 계정 글만 남는다',
    onlyState.cards > 0 && onlyState.cards === onlyState.withBadge,
    `카드 ${onlyState.cards}개 중 벤치마킹 ${onlyState.withBadge}개`);

  const onState = await snapshot();
  record('M3 계정 칩 줄이 나온다',
    onState.chips.length > 1, `${onState.chips.join(' | ')}`);
  await page.screenshot({ path: path.join(shotDir, 'M3_benchmark_on.png') });

  // M4 계정 칩 누르기
  if (onState.chips.length > 1) {
    const picked = await page.evaluate(() => {
      const chips = [...document.querySelectorAll('.benchmark-chip')];
      const target = chips[1]; // [0] 은 「전체」
      const label = target.textContent.trim();
      target.click();
      return label;
    });
    await page.waitForTimeout(600);
    const filtered = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.glass-card')];
      const labels = new Set(
        cards.map((c) => c.querySelector('[data-benchmark-badge]')?.textContent.trim())
      );
      return { cards: cards.length, distinctBadges: [...labels].filter(Boolean) };
    });
    const expectedCount = Number(picked.split(' ').pop());
    record('M4 계정 칩을 누르면 그 계정 글만 남는다',
      filtered.cards === expectedCount && filtered.distinctBadges.length === 1,
      `"${picked}" → 카드 ${filtered.cards}개 · 배지 종류 ${filtered.distinctBadges.join(',')}`);
    await page.screenshot({ path: path.join(shotDir, 'M4_account_filtered.png') });

    // 해제
    await page.evaluate(() => document.querySelector('.benchmark-chip')?.click());
    await page.waitForTimeout(500);
  } else {
    record('M4 계정 칩을 누르면 그 계정 글만 남는다', false, '계정 칩이 없어 확인 불가');
  }

  // M5 카드 배지 클릭
  const badgeFlow = await page.evaluate(async () => {
    const badge = document.querySelector('[data-benchmark-badge]');
    if (!badge) return { skipped: true };
    const accountId = badge.dataset.benchmarkAccount;
    badge.click();
    await new Promise((r) => setTimeout(r, 600));
    const active = document.querySelector('.benchmark-chip.active')?.textContent.trim() || null;
    return { accountId, active };
  });
  record('M5 카드 배지를 누르면 그 계정만 보기로 좁혀진다',
    !badgeFlow.skipped && Boolean(badgeFlow.active) && badgeFlow.active !== '전체',
    badgeFlow.skipped ? '배지 없음' : `계정 ${badgeFlow.accountId} → 활성 칩 "${badgeFlow.active}"`);
  await page.screenshot({ path: path.join(shotDir, 'M5_badge_click.png') });

  // M6 MY 와 상호 배타
  await page.click('#myPostsBtn');
  await page.waitForTimeout(700);
  const myState = await snapshot();
  record('M6 MY 를 켜면 벤치마킹이 꺼진다 (0건 방지)',
    myState.myActive === true && myState.btnActive === false && myState.cards > 0,
    `MY=${myState.myActive} 벤치마킹=${myState.btnActive} 카드 ${myState.cards}개`);

  // M7 끄면 원래대로
  //
  // 배지 총수 0 을 기대하지 않는다 - W1 이후 겹친 글(내 저장글이면서 벤치마킹
  // 계정 소속)은 기본 화면에도 있고 배지를 단다. 벤치마킹 「전용」 글이
  // 0건인지를 본다. 계획: _docs/20260906_03 (W1)
  await page.click('#myPostsBtn');
  await page.waitForTimeout(700);
  const restored = await snapshot();
  const benchOnlyBadges = await page.evaluate(() =>
    document.querySelectorAll('[data-benchmark-also-saved="0"]').length);
  record('M7 끄면 원래 화면으로 돌아온다',
    restored.cards === before.cards && benchOnlyBadges === 0,
    `카드 ${before.cards} → ${restored.cards} · 벤치마킹 전용 배지 ${benchOnlyBadges}개`);

  // ── W1 회귀 가드 ────────────────────────────────────────────────
  // 기대값을 스크립트에 박지 않는다. 켠 계정이 바뀌면 숫자가 바뀌므로
  // API 가 준 계정 상태와 게시글에서 그때그때 계산한다.
  await page.click('#benchmarkBtn');
  await page.waitForTimeout(800);

  const expected = await page.evaluate(async () => {
    const [accRes, postRes] = await Promise.all([
      fetch('/api/get-benchmark-accounts'),
      fetch('/api/posts?limit=100000'),
    ]);
    const accounts = (await accRes.json()).accounts || [];
    const posts = (await postRes.json()).posts || [];
    const activeIds = new Set(accounts.filter((a) => a.status === 'active').map((a) => a.id));
    const perAccount = {};
    let total = 0;
    posts.forEach((post) => {
      const ids = (post.benchmark_accounts || []).filter((id) => activeIds.has(id));
      if (!ids.length) return;
      total += 1;
      ids.forEach((id) => { perAccount[id] = (perAccount[id] || 0) + 1; });
    });
    const nameOf = {};
    accounts.forEach((a) => { nameOf[a.id] = a.name || a.id; });
    return { perAccount, total, nameOf, jangpmActive: activeIds.has('jangpm') };
  });

  const shown = await page.evaluate(() => {
    const chips = [...document.querySelectorAll('.benchmark-chip')]
      .map((c) => c.textContent.trim())
      .filter((t) => !t.startsWith('전체'));
    const sum = chips.reduce((acc, t) => acc + (Number(t.split(' ').pop()) || 0), 0);
    return { chips, sum, cards: document.querySelectorAll('.glass-card').length };
  });

  // M9 겹침이 전부인 계정도 칩에 나온다
  if (expected.jangpmActive) {
    const want = expected.perAccount.jangpm || 0;
    const chip = shown.chips.find((t) => t.startsWith(expected.nameOf.jangpm));
    const got = chip ? Number(chip.split(' ').pop()) : null;
    record('M9 겹침이 전부인 계정도 칩에 나온다',
      Boolean(chip) && got === want && want > 0,
      `기대 ${expected.nameOf.jangpm} ${want} · 화면 ${chip || '칩 없음'}`);
  } else {
    record('M9 겹침이 전부인 계정도 칩에 나온다', false, 'jangpm 이 꺼져 있어 확인 불가');
  }

  // M10 칩 숫자 합계 == 기대값
  const expectedChipSum = Object.values(expected.perAccount).reduce((a, b) => a + b, 0);
  record('M10 칩 숫자 합계가 기대값과 같다',
    shown.sum === expectedChipSum,
    `기대 ${expectedChipSum} · 화면 ${shown.sum}`);

  // M11 렌더 카드 수 == 기대값
  record('M11 렌더 카드 수가 기대값과 같다',
    shown.cards === expected.total,
    `기대 ${expected.total} · 화면 ${shown.cards}`);
  await page.screenshot({ path: path.join(shotDir, 'M11_overlap_restored.png') });

  // M12 사용자 상태(별표·메모)가 안 바뀌었다
  const stateAfter = readUserStateCounts();
  record('M12 별표·메모 건수가 실행 전후 같다',
    Boolean(stateBefore) && Boolean(stateAfter)
      && stateBefore.starred === stateAfter.starred && stateBefore.memo === stateAfter.memo,
    stateBefore && stateAfter
      ? `별표 ${stateBefore.starred}→${stateAfter.starred} · 메모 ${stateBefore.memo}→${stateAfter.memo}`
      : '메타데이터를 읽지 못함');

  // M8 켠 계정이 없을 때 안내
  await page.evaluate(async () => {
    const res = await fetch('/api/get-benchmark-accounts');
    const data = await res.json();
    data.accounts.forEach((a) => { if (a.status === 'active') a.status = 'off'; });
    await fetch('/api/save-benchmark-accounts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.glass-card', { timeout: 60000 });
  await page.click('#benchmarkBtn');
  await page.waitForTimeout(700);
  const emptyState = await snapshot();
  record('M8 켠 계정이 없으면 안내 문구가 나온다',
    Boolean(emptyState.hint), emptyState.hint || '문구 없음');
  await page.screenshot({ path: path.join(shotDir, 'M8_no_active_account.png') });

  console.log(`\nshots: ${shotDir}`);
  await context.close();
} finally {
  await browser.close();
  fs.writeFileSync(ACCOUNTS_PATH, originalAccounts, 'utf8');
}

const failed = checks.filter((c) => !c.ok);
console.log(`${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
