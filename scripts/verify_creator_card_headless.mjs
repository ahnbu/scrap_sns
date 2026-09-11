/**
 * 벤치마킹 소급 표식·제작자 카드 headless 검증. 창을 띄우지 않는다.
 *
 * 사용자가 하는 순서 그대로 본다.
 *   V1 벤치마킹을 켜고 이승필 칩을 누르면 그 사람 글이 전부 나온다 (칩 숫자 = 목록 수)
 *   V2 카드 이름 옆 제작자 아이콘이 있고, 누르면 카드가 열린다
 *   V3 카드에 채널·글 건수·프로필·「자료수집에서 열기」가 있다
 *   V4 「이 사람 글 전체 보기」가 그 사람 글(SNS + 자료) 전체로 좁힌다
 *   V2b 제작자로 식별되지 않은 벤치마킹 계정은 여전히 옛 계정 카드를 연다
 *   V5 프로필 문서가 없는 계정에서도 카드가 깨지지 않는다
 *   V6 계정 목록의 결측 배지가 주소 없는 계정에만 뜬다
 *
 * 이승필은 벤치마킹 계정이자 제작자(creator_id)다. 2026-09-11 부터 제작자로 식별된
 * 사람은 벤치마킹 계정 글도 제작자 카드(`data-creator-id`)를 연다 - 아이콘마다 다른
 * 카드·다른 건수가 뜨던 것(빌더조쉬 49 vs 53)을 없앴다. 옛 계정 카드 경로는 V2b 가
 * 제작자 아닌 계정으로 계속 본다. 계획: _docs/20260911_02 (W5 T5-c·T5-d)
 *
 * 판정은 사람 눈이 아니라 종료코드다 - 각 검사가 기대값과 대조하고, 하나라도
 * 어긋나면 exit 1 이다. 캡처는 증거로만 남긴다.
 *
 * 운영 5000번 서버를 읽기 전용으로 쓴다. 계정 파일을 바꾸지 않으므로
 * verify_benchmark_viewer_headless.mjs 처럼 전용 서버를 띄우지 않는다.
 *
 * Usage: node scripts/verify_creator_card_headless.mjs
 * 계획: _docs/20260910_01 (W1~W3 검증), _docs/20260911_02 (W5)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_VIEWER_URL || 'http://localhost:5000';
const EVIDENCE_DIR = path.join(process.cwd(), '_docs', 'evidence');
const TARGET_ACCOUNT = 'seungpil';
// 이승필의 제작자 id(볼트 프로필 파일명). 벤치마킹 계정 seungpil 과 같은 사람이다.
const TARGET_CREATOR = '이승필_사용성연구소';

fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs',
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const shot = async (page, name) => {
  const file = path.join(EVIDENCE_DIR, `20260910_creator_${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
};

const browser = await launchHeadlessChromium();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // ── V1: 벤치마킹 → 계정 칩 → 목록 수가 칩 숫자와 같다
  await page.evaluate(() => document.getElementById('benchmarkBtn')?.click());
  await page.waitForTimeout(900);

  const chipInfo = await page.evaluate((accountId) => {
    const chips = [...document.querySelectorAll('#benchmarkChipsRow .benchmark-chip')];
    const chip = chips.find((c) => (c.textContent || '').includes('이승필'));
    if (chip) chip.click();
    return {
      chipText: chip ? (chip.textContent || '').trim() : '',
      chipCount: chip ? Number((chip.textContent || '').match(/(\d+)\s*$/)?.[1] || 0) : 0,
      accountId,
    };
  }, TARGET_ACCOUNT);
  await page.waitForTimeout(900);

  const listCount = await page.evaluate(async () => {
    for (let i = 0; i < 12; i += 1) {
      window.scrollBy(0, 4000);
      await new Promise((r) => setTimeout(r, 150));
    }
    const count = document.querySelectorAll('.glass-card').length;
    window.scrollTo(0, 0);
    return count;
  });

  // 데이터 쪽 기대값. 소급 표식이 붙었으면 30건이어야 한다(실측 2026-09-10).
  const dataCount = await page.evaluate(async (accountId) => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    return posts.filter((p) => (p.benchmark_accounts || []).includes(accountId)).length;
  }, TARGET_ACCOUNT);

  record(
    'V1 칩 숫자 = 목록 카드 수 = 데이터 건수',
    chipInfo.chipCount === listCount && listCount === dataCount && dataCount > 6,
    `칩 ${chipInfo.chipCount} · 목록 ${listCount} · 데이터 ${dataCount} (소급 전 6)`,
  );
  const v1Shot = await shot(page, 'v1_chip_filter');

  // ── V2: 이름 옆 제작자 아이콘 — 제작자로 식별된 사람이라 제작자 카드(data-creator-id)를 연다
  const iconInfo = await page.evaluate((creatorId) => ({
    creator: document.querySelectorAll(`.glass-card [data-creator-id="${creatorId}"]`).length,
    account: document.querySelectorAll('.glass-card [data-creator-account]').length,
  }), TARGET_CREATOR);
  record(
    'V2 이름 옆 아이콘이 제작자 카드를 연다(옛 계정 카드 아님)',
    iconInfo.creator > 0 && iconInfo.account === 0,
    JSON.stringify(iconInfo),
  );

  await page.evaluate((creatorId) => {
    document.querySelector(`[data-creator-id="${creatorId}"]`)?.click();
  }, TARGET_CREATOR);
  await page.waitForSelector('[data-creator-all]', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(600);

  // ── V3: 카드 내용
  const card = await page.evaluate(() => {
    const modal = document.getElementById('creatorCardModal');
    const body = document.getElementById('creatorCardBody');
    // `hidden` 만 보면 안 된다 - 마크업이 `opacity-0 pointer-events-none` 으로
    // 시작하므로 `.show` CSS 가 없으면 열려도 화면에 안 보인다(실제로 그랬다).
    const style = modal ? getComputedStyle(modal) : null;
    return {
      open: !!modal
        && !modal.classList.contains('hidden')
        && Number(style.opacity) > 0.9
        && style.pointerEvents !== 'none'
        && style.visibility !== 'hidden',
      opacity: style ? style.opacity : '',
      title: document.getElementById('creatorCardTitle')?.textContent?.trim() || '',
      subtitle: document.getElementById('creatorCardSubtitle')?.textContent?.trim() || '',
      channels: [...(body?.querySelectorAll('.creator-chan') || [])].map((e) => e.textContent.trim()),
      stats: [...(body?.querySelectorAll('.creator-stat') || [])].map((e) => e.textContent.trim()),
      hasProfileText: !!body?.querySelector('.creator-profile-text')?.textContent?.trim(),
      openHref: body?.querySelector('a.creator-open')?.getAttribute('href') || '',
      hasFilterBtn: !!body?.querySelector('[data-creator-all]'),
    };
  });
  record(
    'V3 카드가 실제로 보이고 이름이 맞다',
    card.open && card.title.includes('이승필'),
    `${card.title} · opacity ${card.opacity}`,
  );
  record('V3 채널 배지가 있다', card.channels.length > 0, card.channels.join(','));
  record('V3 플랫폼별 글 건수가 있다', card.stats.length > 0, card.stats.join(','));
  record('V3 프로필 본문이 있다', card.hasProfileText);
  record(
    'V3 자료수집 열기 링크가 obsidian:// 이다',
    card.openHref.startsWith('obsidian://open?path='),
    card.openHref.slice(0, 40),
  );
  const v3Shot = await shot(page, 'v3_creator_card');

  // ── V4: 「이 사람 글 전체 보기」 — 제작자 필터라 그 사람의 SNS + 자료 전체다
  // (사용자가 숨긴 글만 빠진다). 계획: _docs/20260911_02 (W5 T5-d)
  const creatorCount = await page.evaluate(async (creatorId) => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const meta = await (await fetch('/api/get-user-metadata')).json();
    return posts.filter((p) => p.creator_id === creatorId && !(meta[p.post_key] || {}).hidden).length;
  }, TARGET_CREATOR);
  await page.evaluate(() => document.querySelector('[data-creator-all]')?.click());
  await page.waitForTimeout(1000);
  const afterFilter = await page.evaluate(async () => {
    for (let i = 0; i < 12; i += 1) {
      window.scrollBy(0, 4000);
      await new Promise((r) => setTimeout(r, 150));
    }
    const count = document.querySelectorAll('.glass-card').length;
    window.scrollTo(0, 0);
    const modal = document.getElementById('creatorCardModal');
    return { count, modalClosed: !!modal && modal.classList.contains('hidden') };
  });
  record(
    'V4 「이 사람 글 전체 보기」가 그 사람 글(SNS + 자료) 전체로 좁힌다',
    afterFilter.count === creatorCount && creatorCount >= dataCount && afterFilter.modalClosed,
    `${afterFilter.count}건 · 기대 ${creatorCount}(벤치마킹 글 ${dataCount} 포함) · 모달 닫힘 ${afterFilter.modalClosed}`,
  );
  const v4Shot = await shot(page, 'v4_filter_applied');

  // ── V2b: 제작자로 식별되지 않은 벤치마킹 계정은 여전히 옛 계정 카드를 연다
  await page.evaluate(() => document.querySelector('.author-filter-badge')?.click());
  await page.waitForTimeout(800);
  const legacy = await page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    const counts = new Map();
    posts.forEach((p) => {
      const id = (p.benchmark_accounts || [])[0];
      if (!id || p.creator_id) return;
      counts.set(id, (counts.get(id) || 0) + 1);
    });
    const withCreator = new Set(posts.filter((p) => p.creator_id).map((p) => (p.benchmark_accounts || [])[0]));
    const pick = accounts
      .filter((a) => a.status === 'active' && counts.get(a.id) && !withCreator.has(a.id))
      .sort((a, b) => counts.get(b.id) - counts.get(a.id))[0];
    return pick ? { id: pick.id, name: pick.name } : null;
  });
  let legacyInfo = { id: '', title: '' };
  if (legacy) {
    await page.evaluate(() => document.getElementById('benchmarkBtn')?.click());
    await page.waitForTimeout(900);
    await page.evaluate((name) => {
      [...document.querySelectorAll('#benchmarkChipsRow .benchmark-chip')]
        .find((c) => (c.textContent || '').startsWith(`${name} `))?.click();
    }, legacy.name);
    await page.waitForTimeout(900);
    legacyInfo.id = await page.evaluate(() => document.querySelector('.glass-card .creator-btn')?.dataset.creatorAccount || '');
    await page.evaluate(() => document.querySelector('.glass-card .creator-btn')?.click());
    await page.waitForTimeout(1200);
    legacyInfo.title = await page.evaluate(() => document.getElementById('creatorCardTitle')?.textContent?.trim() || '');
    await page.evaluate(() => document.getElementById('closeCreatorCardModal')?.click());
    await page.waitForTimeout(500);
  }
  record(
    'V2b 제작자 아닌 벤치마킹 계정은 옛 계정 카드를 연다',
    !!legacy && legacyInfo.id === legacy.id && legacyInfo.title === legacy.name,
    legacy ? `${legacy.name}(${legacy.id}) · 아이콘 ${legacyInfo.id} · 제목 ${legacyInfo.title}` : '후보 없음',
  );

  // ── V5: 프로필 문서가 없는 계정
  const noProfile = await page.evaluate(async () => {
    const response = await fetch('/api/creator-profile?account_id=themodellers');
    return response.ok ? await response.json() : { error: response.status };
  });
  record(
    'V5 프로필 없는 계정은 found:false 로 200 을 준다',
    noProfile.found === false && !!noProfile.reason,
    JSON.stringify(noProfile),
  );

  // ── V6: 계정 목록 결측 배지
  // 배지 수를 계정 데이터로 계산한 기대값과 대조한다. "배지가 몇 개 보이나"만
  // 보면 규칙이 깨져도 0 == 0 으로 통과한다.
  const gaps = await page.evaluate(async () => {
    document.getElementById('settingsBtn')?.click();
    await new Promise((r) => setTimeout(r, 400));
    const tab = [...document.querySelectorAll('.tab-btn')]
      .find((b) => b.dataset.target === 'tabBenchmark');
    tab?.click();
    await new Promise((r) => setTimeout(r, 600));

    const rows = [...document.querySelectorAll('.bm-account-item')];
    const withGap = rows.filter((r) => r.querySelector('.bm-gap'));

    // 화면에 보이는 행(excluded 제외)에 대해 규칙을 데이터로 다시 적용한다.
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    const visibleIds = new Set(rows.map((r) => r.dataset.bmId));
    const collectable = new Set(['youtube', 'linkedin']);
    const platforms = ['youtube', 'threads', 'linkedin', 'x'];
    const expected = accounts.filter((a) => {
      if (!visibleIds.has(a.id) || a.status === 'excluded') return false;
      const registered = platforms.filter((p) => (a.channels || {})[p]);
      if (!registered.length) return true;
      return registered.some(
        (p) => collectable.has(p) && !((a.match_keys || {})[p] || []).length,
      );
    }).length;

    return {
      rows: rows.length,
      gaps: withGap.length,
      expected,
      samples: withGap.slice(0, 3).map((r) => ({
        name: r.querySelector('.bm-account-name')?.textContent?.trim() || '',
        reason: r.querySelector('.bm-gap')?.textContent?.trim() || '',
      })),
    };
  });
  record(
    'V6 결측 배지 수가 계정 데이터와 일치한다',
    gaps.rows > 0 && gaps.gaps === gaps.expected,
    `행 ${gaps.rows} · 배지 ${gaps.gaps} · 기대 ${gaps.expected} ${JSON.stringify(gaps.samples)}`,
  );
  const v6Shot = await shot(page, 'v6_account_gaps');

  console.log(`\n증거: ${[v1Shot, v3Shot, v4Shot, v6Shot].map((f) => path.basename(f)).join(', ')}`);
  console.log(`      ${EVIDENCE_DIR}`);
} finally {
  await browser.close();
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
if (failed.length) {
  console.log(`실패: ${failed.map((c) => c.name).join(' / ')}`);
  process.exit(1);
}
