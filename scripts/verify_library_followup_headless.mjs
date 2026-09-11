/**
 * 자료수집 뷰어 후속개선 headless 검증. 창을 띄우지 않는다.
 *
 * 사용자가 제보한 순서 그대로 본다.
 *   L  〈파일〉 칩 → 공냥이 자료 카드 「읽기」·이름 옆 아이콘 → 팝업 폭·여백·칩 간격 (1920·1280·900)
 *   P  자료 카드 미리보기가 줄바꿈을 살리고 `---` 가 없다, 주제·형태 칩이 없다
 *   T  자료 카드 태그 — 정리 스크립트 dry-run 변경 0, 평균·최대 태그 수, 임시 키 0
 *   F  파일 카드 이름 「공냥이」 클릭 → 자동 ALL + 공냥이 글 전체 → 채널 칩 교집합 → ALL
 *      스레드 카드 이름 클릭도 같은 결과, 제작자 필터 + 「저장」 은 교집합
 *   U  벤치마킹 계정이자 제작자인 사람의 SNS 카드 아이콘이 제작자 카드(자료 수 포함)를 연다
 *
 * 판정은 사람 눈이 아니라 종료코드다. 기대값은 /api/posts·태그·사용자메타로 계산하고,
 * 하나라도 어긋나면 exit 1. 캡처는 `_docs/evidence/20260911_02_*.png`(git 제외).
 *
 * 운영 5000번 서버를 쓴다. 이 스크립트가 쓰는 운영 파일은 없다 - 다만 새 브라우저 프로필은
 * 로드 때 자동 태그를 적용해 태그 파일을 저장한다(뷰어 기존 동작).
 *
 * Usage: node scripts/verify_library_followup_headless.mjs
 * 계획: _docs/20260911_02 (W6 T6-a)
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = (process.env.SNS_VIEWER_URL || 'http://localhost:5000').replace(/\/$/, '');
const EVIDENCE_DIR = path.join(process.cwd(), '_docs', 'evidence');
const TARGET_CREATOR = '공냥이';
const LIB_MAX = 880;
const CREATOR_MAX = 576;

fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs',
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const shot = (page, name) => page.screenshot({
  path: path.join(EVIDENCE_DIR, `20260911_02_${name}.png`), fullPage: false,
});

const pageErrors = [];
async function openViewer(browser, width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  page.on('pageerror', (error) => pageErrors.push(`${width}px ${error}`));
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle', timeout: 120000 });
  await page.waitForSelector('.glass-card', { timeout: 120000 });
  return { context, page };
}

// 무한 스크롤을 끝까지 내려 카드 수가 멈출 때까지 기다린다.
async function loadAll(page) {
  return page.evaluate(async () => {
    let last = -1;
    for (let i = 0; i < 60; i += 1) {
      window.scrollBy(0, 6000);
      await new Promise((r) => setTimeout(r, 150));
      const count = document.querySelectorAll('.glass-card').length;
      if (count === last && i > 3) break;
      last = count;
    }
    window.scrollTo(0, 0);
    const cards = [...document.querySelectorAll('.glass-card')];
    const by = {};
    cards.forEach((c) => { by[c.dataset.platform] = (by[c.dataset.platform] || 0) + 1; });
    return {
      total: cards.length,
      by,
      active: [...document.querySelectorAll('.filter-chip.active')].map((b) => b.dataset.filter || b.id),
      badges: [...document.querySelectorAll('.author-filter-badge')].map((b) => b.innerText.replace(/\s+/g, ' ').trim()),
    };
  });
}

async function clickChip(page, filter) {
  await page.click(`.filter-chip[data-filter="${filter}"]`);
  await page.waitForTimeout(900);
}

// 기대값 계산에 쓰는 데이터. 브라우저 fetch 로 받는다(node 내장 fetch 는 큰 gzip 응답에서 죽는다).
async function loadData(page) {
  return page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const meta = await (await fetch('/api/get-user-metadata')).json();
    const tags = await (await fetch('/api/get-tags')).json();
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    return { posts, meta, tags, accounts };
  });
}

const isLibrary = (p) => p.sns_platform === 'web' || p.sns_platform === 'file';

const browser = await launchHeadlessChromium();
try {
  // ── L: 팝업 폭·여백·칩 간격 (3개 폭)
  for (const [width, height] of [[1920, 1080], [1280, 800], [900, 900]]) {
    const { context, page } = await openViewer(browser, width, height);
    await clickChip(page, 'file');
    const card = page.locator('.glass-card[data-platform="file"]', { hasText: TARGET_CREATOR }).first();
    const pad = width >= 768 ? 64 : 32;
    const expectLib = Math.min(LIB_MAX, width - pad);
    const expectCreator = Math.min(CREATOR_MAX, width - pad);

    await card.locator('[data-library-read]').click();
    await page.waitForSelector('#libraryNoteModal.show');
    // 부제·본문은 상세 응답을 받은 뒤 채워진다.
    await page.waitForFunction(() => (document.getElementById('libraryNoteSubtitle')?.textContent || '').trim().length > 0,
      null, { timeout: 30000 });
    await page.waitForTimeout(300);
    const lib = await page.evaluate(() => {
      const panel = document.querySelector('#libraryNoteModal > div');
      const cs = getComputedStyle(document.getElementById('libraryNoteBody'));
      return { w: Math.round(panel.getBoundingClientRect().width), top: cs.paddingTop, bottom: cs.paddingBottom,
        subtitle: document.getElementById('libraryNoteSubtitle')?.textContent?.trim() || '' };
    });
    record(
      `L1 ${width}px 읽기 팝업 폭 = ${expectLib}px, 본문 위아래 여백 20px`,
      Math.abs(lib.w - expectLib) <= 1 && lib.top === '20px' && lib.bottom === '20px',
      `폭 ${lib.w} · 여백 ${lib.top}/${lib.bottom}`,
    );
    if (width === 1920) {
      record('L1b 읽기 팝업 부제에 자료 형태가 있다', /package/.test(lib.subtitle), lib.subtitle);
      await shot(page, 'l_read_modal_1920');
    }
    await page.click('#closeLibraryNoteModal');
    await page.waitForTimeout(450);

    await card.locator('.creator-btn[data-creator-id]').click();
    await page.waitForSelector('#creatorCardModal.show');
    await page.waitForSelector('[data-creator-all]');
    await page.waitForTimeout(400);
    const cc = await page.evaluate(() => {
      const panel = document.querySelector('#creatorCardModal > div');
      const body = document.getElementById('creatorCardBody');
      const cs = getComputedStyle(body);
      const statRow = body.querySelector('.creator-stat')?.parentElement;
      const chanRow = body.querySelector('.creator-chan')?.parentElement;
      return { w: Math.round(panel.getBoundingClientRect().width), top: cs.paddingTop, bottom: cs.paddingBottom,
        statGap: statRow ? getComputedStyle(statRow).columnGap : '', chanGap: chanRow ? getComputedStyle(chanRow).columnGap : '' };
    });
    record(
      `L2 ${width}px 프로필 카드 폭 = ${expectCreator}px, 여백 20px, 칩 간격 6px`,
      Math.abs(cc.w - expectCreator) <= 1 && cc.top === '20px' && cc.bottom === '20px'
        && cc.statGap === '6px' && cc.chanGap === '6px',
      `폭 ${cc.w} · 여백 ${cc.top}/${cc.bottom} · 칩 간격 ${cc.statGap}/${cc.chanGap}`,
    );
    if (width === 1920) await shot(page, 'l_creator_card_1920');
    await context.close();
  }

  const { context, page } = await openViewer(browser, 1920, 1080);
  const data = await loadData(page);
  const hidden = new Set(Object.entries(data.meta || {}).filter(([, v]) => v && v.hidden).map(([k]) => k));
  const visible = (p) => !hidden.has(p.post_key);
  const creatorPosts = data.posts.filter((p) => p.creator_id === TARGET_CREATOR && visible(p));

  // ── P: 미리보기·칩
  await clickChip(page, 'file');
  const preview = await page.evaluate((name) => {
    const card = [...document.querySelectorAll('.glass-card[data-platform="file"]')]
      .find((c) => (c.querySelector('.author-link')?.textContent || '').includes(name));
    const p = card?.querySelector('.library-preview');
    return p ? { text: p.innerText, ws: getComputedStyle(p).whiteSpace } : null;
  }, TARGET_CREATOR);
  const lines = (preview?.text || '').split('\n').map((l) => l.trim());
  record(
    'P1 공냥이 자료 카드 미리보기가 줄바꿈을 살리고 `---` 가 없다',
    !!preview && preview.ws === 'pre-line' && lines.length > 1 && !lines.includes('---')
      && lines.includes('포함 자료 목록'),
    preview ? `white-space ${preview.ws} · ${lines.length}줄 · ${JSON.stringify(lines.slice(0, 4))}` : '카드 없음',
  );
  await shot(page, 'p_file_card_preview');

  const chipAudit = { cards: 0, chips: 0, dash: 0 };
  for (const filter of ['file', 'web']) {
    await clickChip(page, filter);
    await loadAll(page);
    const part = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.glass-card[data-platform="web"], .glass-card[data-platform="file"]')];
      return {
        cards: cards.length,
        chips: cards.reduce((n, c) => n + c.querySelectorAll('.library-chip').length, 0),
        dash: cards.filter((c) => (c.querySelector('.library-preview')?.innerText || '').split('\n').some((l) => /^([-*_])\1{2,}$/.test(l.trim()))).length,
      };
    });
    chipAudit.cards += part.cards;
    chipAudit.chips += part.chips;
    chipAudit.dash += part.dash;
  }
  const expectLibraryCards = data.posts.filter((p) => isLibrary(p) && visible(p)).length;
  record(
    'P2 자료 카드 전량에 주제·형태 칩 0개, 가로선 줄 0개',
    chipAudit.cards === expectLibraryCards && chipAudit.chips === 0 && chipAudit.dash === 0,
    `카드 ${chipAudit.cards}(기대 ${expectLibraryCards}) · 칩 ${chipAudit.chips} · 가로선 ${chipAudit.dash}`,
  );

  // ── T: 태그
  const dry = JSON.parse(execFileSync('python', ['scripts/migrate_library_auto_tags.py'], { encoding: 'utf-8' }).trim().split('\n').pop());
  record(
    'T1 태그 정리 dry-run 변경 0 (자료 키·임시 키·SNS 키)',
    dry.changed_keys === 0 && dry.junk_keys === 0 && dry.sns_changed_keys === 0,
    JSON.stringify(dry),
  );
  const snsUrls = new Set(data.posts.filter((p) => !isLibrary(p)).map((p) => p.canonical_url || p.url));
  const libCounts = data.posts.filter(isLibrary).map((p) => p.canonical_url || p.url)
    .filter((u) => !snsUrls.has(u) && (data.tags[u] || []).length).map((u) => data.tags[u].length);
  const avg = libCounts.reduce((a, b) => a + b, 0) / (libCounts.length || 1);
  const max = Math.max(0, ...libCounts);
  record('T2 자료 카드 태그 평균 ≤ 4.0, 최대 ≤ 10', avg <= 4.0 && max <= 10, `평균 ${avg.toFixed(2)} · 최대 ${max} · 키 ${libCounts.length}`);
  const junk = await page.evaluate(() => {
    const local = JSON.parse(localStorage.getItem('sns_tags') || '{}');
    return Object.keys(local).filter((k) => k.includes('sns-library-verify-')).length;
  });
  const serverJunk = Object.entries(data.tags).filter(([k, v]) => k.includes('sns-library-verify-') && (v || []).length).length;
  record('T3 임시 검증 볼트 태그 키 0 (서버 파일 비어 있지 않은 키 · 브라우저 사본)', junk === 0 && serverJunk === 0, `서버 ${serverJunk} · 브라우저 ${junk}`);
  const gongFile = data.posts.find((p) => p.creator_id === TARGET_CREATOR && p.sns_platform === 'file');
  // 바로 앞 P2 가 〈웹〉 칩으로 끝난다 - 파일 카드가 보이게 되돌린다.
  await clickChip(page, 'file');
  const cardTags = await page.evaluate((name) => {
    const card = [...document.querySelectorAll('.glass-card[data-platform="file"]')]
      .find((c) => (c.querySelector('.author-link')?.textContent || '').includes(name));
    return [...(card?.querySelectorAll('.tag-chip > span:first-child') || [])].map((s) => s.textContent.trim());
  }, TARGET_CREATOR);
  await clickChip(page, 'all');
  const expectTags = data.tags[gongFile?.canonical_url || gongFile?.url] || [];
  record(
    'T4 공냥이 자료 카드 태그 = 태그 파일 값',
    JSON.stringify([...cardTags].sort()) === JSON.stringify([...expectTags].sort()) && cardTags.length > 0,
    `카드 ${JSON.stringify(cardTags)} · 파일 ${JSON.stringify(expectTags)}`,
  );

  // ── F: 이름 클릭 = 제작자 필터
  await clickChip(page, 'file');
  await page.locator('.glass-card[data-platform="file"]', { hasText: TARGET_CREATOR }).first().locator('.author-link').click();
  await page.waitForTimeout(900);
  const f1 = await loadAll(page);
  record(
    `F1 파일 카드 이름 클릭 → 자동 ALL, ${TARGET_CREATOR} 글 전체`,
    f1.total === creatorPosts.length && f1.active.includes('all') && f1.badges.some((b) => b.startsWith('account_circle')),
    `${f1.total}건(기대 ${creatorPosts.length}) ${JSON.stringify(f1.by)} · 활성 ${f1.active} · 배지 ${f1.badges}`,
  );
  await shot(page, 'f_name_click_all');
  await clickChip(page, 'file');
  const f2 = await loadAll(page);
  const expectFile = creatorPosts.filter((p) => p.sns_platform === 'file').length;
  await clickChip(page, 'all');
  const f3 = await loadAll(page);
  record(
    'F2 파일 칩 → 교집합, ALL → 다시 전체',
    f2.total === expectFile && f3.total === creatorPosts.length,
    `파일 ${f2.total}(기대 ${expectFile}) · ALL ${f3.total}`,
  );

  await page.click('#savedPostsBtn');
  await page.waitForTimeout(900);
  const f4 = await loadAll(page);
  const expectSaved = creatorPosts.filter((p) => p.is_saved !== false && p.is_own_post !== true).length;
  await page.click('#savedPostsBtn');
  await page.waitForTimeout(900);
  const f4b = await loadAll(page);
  record(
    'F3 제작자 필터 + 「저장」 = 교집합, 끄면 다시 전체',
    f4.total === expectSaved && f4b.total === creatorPosts.length,
    `저장 ${f4.total}(기대 ${expectSaved}) · 끔 ${f4b.total}`,
  );

  // 같은 이름을 다시 누르면 해제된다.
  await page.locator('.glass-card', { hasText: TARGET_CREATOR }).first().locator('.author-link').click();
  await page.waitForTimeout(900);
  const offBadges = await page.evaluate(() => document.querySelectorAll('.author-filter-badge').length);
  record('F4 같은 이름을 다시 누르면 제작자 필터가 풀린다', offBadges === 0, `배지 ${offBadges}`);

  const threadsUser = creatorPosts.find((p) => p.sns_platform === 'threads')?.username || '';
  await page.fill('#searchInput', threadsUser);
  await page.waitForTimeout(1800);
  await page.locator('.glass-card[data-platform="threads"]', { hasText: TARGET_CREATOR }).first().locator('.author-link').click();
  await page.waitForTimeout(900);
  await page.fill('#searchInput', '');
  await page.waitForTimeout(1800);
  const f5 = await loadAll(page);
  record(
    'F5 스레드 카드 이름 클릭도 공냥이 글 전체(자료 포함)',
    f5.total === creatorPosts.length && (f5.by.file || 0) + (f5.by.web || 0) > 0,
    `${f5.total}건 ${JSON.stringify(f5.by)}`,
  );
  await page.click('.author-filter-badge');
  await page.waitForTimeout(700);

  // ── U: 벤치마킹 계정이자 제작자 → 제작자 카드
  const libraryByCreator = new Map();
  data.posts.filter(isLibrary).forEach((p) => libraryByCreator.set(p.creator_id, (libraryByCreator.get(p.creator_id) || 0) + 1));
  const candidates = data.accounts
    .filter((a) => a.status === 'active')
    .map((a) => {
      const own = data.posts.filter((p) => (p.benchmark_accounts || [])[0] === a.id && p.creator_id);
      const creatorId = own[0]?.creator_id || '';
      return { account: a, creatorId, lib: libraryByCreator.get(creatorId) || 0 };
    })
    .filter((c) => c.creatorId && c.lib > 0)
    .sort((a, b) => b.lib - a.lib);
  const target = candidates[0];
  if (!target) {
    record('U1 벤치마킹 계정이자 자료가 있는 제작자가 있다', false, '후보 없음');
  } else {
    await page.click('#benchmarkBtn');
    await page.waitForTimeout(900);
    await page.evaluate((name) => {
      [...document.querySelectorAll('#benchmarkChipsRow .benchmark-chip')]
        .find((c) => (c.textContent || '').startsWith(`${name} `))?.click();
    }, target.account.name);
    await page.waitForTimeout(900);
    const icon = await page.evaluate(() => {
      const btn = document.querySelector('.glass-card .creator-btn');
      return { creatorId: btn?.dataset.creatorId || '', account: btn?.dataset.creatorAccount || '' };
    });
    await page.click('.glass-card .creator-btn');
    await page.waitForSelector('[data-creator-all]', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(500);
    const stats = await page.evaluate(() => [...document.querySelectorAll('#creatorCardBody .creator-stat')].map((e) => e.textContent.trim()));
    record(
      `U1 ${target.account.name} SNS 카드 아이콘이 제작자 카드를 열고 자료 수가 보인다`,
      icon.creatorId === target.creatorId && !icon.account && stats.includes(`자료 ${target.lib}`),
      `아이콘 ${JSON.stringify(icon)} · 칩 ${JSON.stringify(stats)} · 기대 자료 ${target.lib}`,
    );
    await shot(page, 'u_benchmark_creator_card');
  }

  await context.close();
  record('R 페이지 스크립트 오류 없음', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
} finally {
  await browser.close();
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
console.log(`증거: ${EVIDENCE_DIR}\\20260911_02_*.png`);
if (failed.length) {
  console.log(`실패: ${failed.map((c) => c.name).join(' / ')}`);
  process.exit(1);
}
