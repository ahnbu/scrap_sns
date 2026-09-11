/**
 * 볼트 자료 카드·「요약」 배지·전 카드 제작자 프로필 headless 검증. 창을 띄우지 않는다.
 *
 * 사용자가 하는 순서 그대로 본다(계획 §6 화면).
 *   〈웹〉 칩 → 자료 카드 「읽기」 → 모달 본문 → 〈파일〉 칩 → 겹침 카드 「요약」 배지
 *   → 이름 옆 아이콘 → 제작자 카드
 *
 * 판정은 사람 눈이 아니라 종료코드다 - 각 검사가 데이터로 계산한 기대값과 대조하고,
 * 하나라도 어긋나면 exit 1 이다. 캡처는 `_docs/evidence/`(git 제외)에 증거로만 남긴다.
 *
 * 운영 5000번 서버로 목록·검색·모달을 본다. 볼트 편집 반영과 악성 노트 렌더는
 * 표본 볼트를 띄운 전용 서버(scripts/_library_verify_server.mjs)로 본다 - 운영
 * 볼트를 고쳤다 되돌리지 않는다.
 *
 * 운영 데이터에 쓰는 검사는 하나다: 자료 카드 별표·메모가 재시작 후에도 남는지
 * (W2 완료 기준). 끝나면 같은 화면 조작으로 지우고, 실패해도 finally 가 API 로 지운다.
 * 마지막 검사가 사용자 메타 건수가 W0 기준선과 같은지 본다.
 *
 * Usage: node scripts/verify_library_cards_headless.mjs [--waves=w2,w3,w4]
 * 계획: _docs/20260911_01 (W2·W3·W4 검증)
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startLibraryVerifyServer } from './_library_verify_server.mjs';

const BASE_URL = (process.env.SNS_VIEWER_URL || 'http://localhost:5000').replace(/\/$/, '');
const EVIDENCE_DIR = path.join(process.cwd(), '_docs', 'evidence');
const INDEX_PATH = path.join('web_viewer', 'sns_library_index.json');
const BASELINE_PATH = path.join(EVIDENCE_DIR, '20260911_baseline.log');
const wavesArg = process.argv.find((arg) => arg.startsWith('--waves='));
const WAVES = new Set((wavesArg ? wavesArg.split('=')[1] : 'w2,w3,w4').split(','));

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

const shots = [];
const shot = async (page, name) => {
  const file = path.join(EVIDENCE_DIR, `20260911_library_${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  shots.push(path.basename(file));
};

// 서버 _normalize_search_text / _matches_search_query 와 같은 규칙.
function normalizeSearchText(value) {
  return String(value || '').normalize('NFKC').toLowerCase()
    .replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
}
function matchesQuery(searchable, query) {
  const q = normalizeSearchText(query);
  if (!q) return false;
  if (searchable.includes(q)) return true;
  const terms = q.split(' ').filter(Boolean);
  return terms.length > 0 && terms.every((term) => searchable.includes(term));
}

function readBaseline() {
  const text = fs.readFileSync(BASELINE_PATH, 'utf8');
  const num = (key) => Number((text.match(new RegExp(`^${key}=(\\d+)`, 'm')) || [])[1]);
  const meta = text.match(/^user_metadata_entries=(\d+) \(favorite=(\d+) hidden=(\d+) note=(\d+)\)/m) || [];
  return {
    totalPosts: num('total_posts'),
    benchmarkMarked: num('benchmark_marked_posts'),
    metaEntries: Number(meta[1]),
    favorites: Number(meta[2]),
    hidden: Number(meta[3]),
    notes: Number(meta[4]),
  };
}

// 인덱스 본문의 표·제목·목록 수. 렌더러와 독립으로 센다(코드 펜스·인용 기호 처리만 공유).
function countMarkdownStructure(markdown) {
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n').map((line) => line.replace(/^(\s*>\s?)+/, ''));
  let headings = 0; let tables = 0; let items = 0; let inFence = null;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const fence = line.match(/^\s*(```+|~~~+)/);
    if (inFence) { if (line.trim().startsWith(inFence)) inFence = null; continue; }
    if (fence) { inFence = fence[1]; continue; }
    if (/^#{1,6}\s+/.test(line)) { headings += 1; continue; }
    if (/^\s*\|/.test(line) && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1] || '')) {
      tables += 1;
      i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) i += 1;
      i -= 1;
      continue;
    }
    if (/^(\s*)([-*+]|\d+[.)])\s+/.test(line) && !/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) items += 1;
  }
  return { headings, tables, items };
}

// 목록은 60장씩 스크롤로 붙는다. 상단 라벨의 표시 건수에 닿을 때까지 내린다 -
// "몇 번 내려서 안 늘면 끝"만 보면 느린 배치에서 일부만 센다(2,100/3,070 실측).
async function loadAllCards(page) {
  const target = await page.evaluate(() => {
    const text = document.getElementById('totalPostsCount')?.textContent || '';
    return Number((text.match(/^(\d+)\s*건/) || [])[1] || 0);
  });
  let previous = -1;
  let stable = 0;
  for (let i = 0; i < 400 && stable < 8; i += 1) {
    const count = await page.evaluate(async () => {
      window.scrollTo(0, document.body.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 150));
      return document.querySelectorAll('.glass-card').length;
    });
    if (target && count >= target) break;
    stable = count === previous ? stable + 1 : 0;
    previous = count;
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return page.evaluate(() => [...document.querySelectorAll('.glass-card')].map((card) => ({
    platform: card.dataset.platform || '',
    seq: Number(card.dataset.seq || 0),
  })));
}

async function clickChip(page, filter) {
  await page.evaluate((name) => document.querySelector(`.filter-chip[data-filter="${name}"]`)?.click(), filter);
  await page.waitForTimeout(600);
}

// 사용자 입력과 같은 input 이벤트를 낸다. page.fill 은 요소 동작 가능 대기를 해서
// 큰 모달을 닫은 직후 30초 대기 초과로 멈춘 적이 있다(2026-09-11 실측).
async function typeInto(page, selector, value) {
  await page.evaluate(({ sel, text }) => {
    const input = document.querySelector(sel);
    if (!input) throw new Error(`입력칸 없음: ${sel}`);
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }, { sel: selector, text: value });
}

async function setSearch(page, query) {
  const waiter = query
    ? page.waitForResponse((res) => res.url().includes('/api/search'), { timeout: 30000 })
    : null;
  await typeInto(page, '#searchInput', query);
  if (waiter) await waiter;
  await page.waitForTimeout(700);
}

async function modalState(page, modalId) {
  return page.evaluate((id) => {
    const modal = document.getElementById(id);
    if (!modal) return { open: false };
    const style = getComputedStyle(modal);
    return {
      open: !modal.classList.contains('hidden')
        && Number(style.opacity) > 0.9
        && style.pointerEvents !== 'none'
        && style.visibility !== 'hidden',
      opacity: style.opacity,
      pointerEvents: style.pointerEvents,
    };
  }, modalId);
}

async function waitLibraryModal(page) {
  await page.waitForFunction(() => {
    const modal = document.getElementById('libraryNoteModal');
    const body = document.getElementById('libraryNoteBody');
    return modal && modal.classList.contains('show') && body && body.textContent.trim().length > 0;
  }, null, { timeout: 30000 });
  await page.waitForTimeout(400);
}

async function closeLibraryModal(page) {
  await page.evaluate(() => document.getElementById('closeLibraryNoteModal')?.click());
  await page.waitForTimeout(400);
}

function restartProductionServer() {
  execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/restart_viewer_server.ps1'], {
    stdio: 'pipe',
    windowsHide: true,
  });
}

const baseline = readBaseline();
const browser = await launchHeadlessChromium();
let cleanupKey = '';
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  const index = JSON.parse(fs.readFileSync(INDEX_PATH, 'utf8'));
  const visibleNotes = index.posts.filter((post) => !post.library_overlap_of);
  const overlapNotes = index.posts.filter((post) => post.library_overlap_of);
  const apiPosts = await page.evaluate(async () => (await (await fetch('/api/posts')).json()).posts);
  const userMeta = await page.evaluate(async () => (await fetch('/api/get-user-metadata')).json());
  const hiddenKeys = new Set(Object.entries(userMeta).filter(([, v]) => v?.hidden).map(([k]) => k));
  const isLibrary = (post) => post.sns_platform === 'web' || post.sns_platform === 'file';
  const snsPosts = apiPosts.filter((post) => !isLibrary(post));
  const libraryPosts = apiPosts.filter(isLibrary);
  const shownNotes = (platform) => visibleNotes.filter(
    (post) => post.sns_platform === platform && !hiddenKeys.has(`${platform}:${post.platform_id}`),
  );

  if (WAVES.has('w2')) {
    // ── W2-1 건수: /api/posts = 통합본 + (자료 − 겹침)
    record(
      'W2-1 /api/posts 건수 = 통합본 + 목록 자료',
      snsPosts.length === baseline.totalPosts && libraryPosts.length === visibleNotes.length
        && apiPosts.length === baseline.totalPosts + (index.note_count - index.overlap_count),
      `api ${apiPosts.length} = 통합본 ${snsPosts.length}(기준 ${baseline.totalPosts}) + 자료 ${libraryPosts.length} (노트 ${index.note_count} − 겹침 ${index.overlap_count})`,
    );
    // 상단 라벨은 기본 필터(내 글 숨김·숨김글·꺼진 벤치마킹 계정 제외) 뒤의 표시 건수다
    // (기존 동작, updateTotalPostsLabel). 같은 규칙으로 기대값을 계산한다.
    const accounts = await page.evaluate(async () => (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || []);
    const activeIds = new Set(accounts.filter((a) => a.status === 'active').map((a) => a.id));
    const defaultVisible = apiPosts.filter((post) => !hiddenKeys.has(post.post_key)
      && post.is_own_post !== true
      && (post.is_saved !== false || (post.benchmark_accounts || []).some((id) => activeIds.has(id))));
    const expectedLabel = `${defaultVisible.length} 건 · 자료 ${defaultVisible.filter(isLibrary).length}`;
    const label = await page.evaluate(() => document.getElementById('totalPostsCount')?.textContent?.trim() || '');
    record(
      'W2-2 상단 총건수에 자료 건수가 구분돼 보인다',
      label === expectedLabel && defaultVisible.filter(isLibrary).length === libraryPosts.length,
      `화면 "${label}" · 기대 "${expectedLabel}"`,
    );

    // ── W2-3 〈웹〉 칩
    await clickChip(page, 'web');
    const webCards = await loadAllCards(page);
    const expectedWeb = shownNotes('web').length;
    record(
      'W2-3 〈웹〉 칩 카드 수 = 인덱스 웹 자료 수(겹침 제외)',
      webCards.length === expectedWeb && webCards.every((card) => card.platform === 'web'),
      `카드 ${webCards.length} · 기대 ${expectedWeb}`,
    );
    await shot(page, 'w2_web_chip');

    // ── W2-4 「읽기」 → 모달 본문이 실제로 보인다
    const firstWeb = await page.evaluate(() => {
      const card = document.querySelector('.glass-card[data-platform="web"]');
      const title = card?.querySelector('.library-title')?.textContent?.trim() || '';
      card?.querySelector('[data-library-read]')?.click();
      return { title, seq: Number(card?.dataset.seq || 0) };
    });
    await waitLibraryModal(page);
    const readState = await modalState(page, 'libraryNoteModal');
    const readInfo = await page.evaluate(() => ({
      title: document.getElementById('libraryNoteTitle')?.textContent?.trim() || '',
      bodyLength: document.getElementById('libraryNoteBody')?.textContent?.length || 0,
      obsidian: !!document.querySelector('#libraryNoteLinks [data-library-link="obsidian"]'),
    }));
    record(
      'W2-4 「읽기」 모달이 계산된 스타일로 보이고 본문이 렌더된다',
      readState.open && readInfo.title === firstWeb.title && readInfo.bodyLength > 50 && readInfo.obsidian,
      `opacity ${readState.opacity} · 제목 일치 ${readInfo.title === firstWeb.title} · 본문 ${readInfo.bodyLength}자`,
    );
    await shot(page, 'w2_read_modal');
    await closeLibraryModal(page);

    // ── W2-5 〈웹〉 칩 + 흔한 검색어: 상한 절단 없이 자료가 다 나온다(F25)
    const QUERY = 'claude';
    await setSearch(page, QUERY);
    const searchCards = await loadAllCards(page);
    const expectedSearch = shownNotes('web').filter((post) => {
      const note = String(userMeta[`web:${post.platform_id}`]?.note || '');
      const searchable = normalizeSearchText([
        post.full_text, post.display_name, post.username, note,
        post.library_title, post.library_topic, (post.library_tags || []).join(' '),
      ].filter(Boolean).join(' '));
      return matchesQuery(searchable, QUERY);
    }).length;
    record(
      `W2-5 〈웹〉+"${QUERY}" 검색 결과 = 인덱스에서 걸리는 웹 자료 수`,
      searchCards.length === expectedSearch && searchCards.every((card) => card.platform === 'web') && expectedSearch > 0,
      `카드 ${searchCards.length} · 기대 ${expectedSearch}`,
    );
    await shot(page, 'w2_web_search');
    await setSearch(page, '');

    // ── W2-6 〈파일〉 칩
    await clickChip(page, 'file');
    const fileCards = await loadAllCards(page);
    const expectedFile = shownNotes('file').length;
    record(
      'W2-6 〈파일〉 칩 카드 수 = 인덱스 파일 자료 수',
      fileCards.length === expectedFile && fileCards.every((card) => card.platform === 'file'),
      `카드 ${fileCards.length} · 기대 ${expectedFile}`,
    );
    await shot(page, 'w2_file_chip');

    // ── W2-7 겹침 자료 이중 노출 0
    // 검색은 URL 을 색인하지 않으므로(서버 _searchable) source_url 문자열 검색 대신,
    // 데이터로 전수 확인하고 화면은 원문 글 본문으로 한 건 확인한다.
    const libraryIds = new Set(libraryPosts.map((post) => `${post.sns_platform}:${post.platform_id}`));
    const linkedSeqs = new Map();
    snsPosts.forEach((post) => (post.library_notes || []).forEach((note) => {
      linkedSeqs.set(note.sequence_id, (linkedSeqs.get(note.sequence_id) || 0) + 1);
    }));
    const doubled = overlapNotes.filter((note) => libraryIds.has(`${note.sns_platform}:${note.platform_id}`));
    const unlinked = overlapNotes.filter((note) => linkedSeqs.get(note.sequence_id) !== 1);
    const sample = snsPosts.find((post) => (post.library_notes || []).length
      && normalizeSearchText(post.full_text_preview).length > 40 && !hiddenKeys.has(post.post_key));
    await clickChip(page, 'all');
    const sampleQuery = normalizeSearchText(sample.full_text_preview).slice(0, 30);
    await setSearch(page, sampleQuery);
    const sampleCards = await loadAllCards(page);
    const noteSeqs = new Set(sample.library_notes.map((note) => note.sequence_id));
    record(
      'W2-7 겹침 자료가 카드로 이중 노출되지 않는다',
      doubled.length === 0 && unlinked.length === 0
        && sampleCards.filter((card) => card.seq === sample.sequence_id).length === 1
        && sampleCards.filter((card) => noteSeqs.has(card.seq)).length === 0,
      `겹침 ${overlapNotes.length} · 이중 ${doubled.length} · 연결 누락 ${unlinked.length} · 표본 "${sampleQuery}" 원문 카드 ${sampleCards.filter((c) => c.seq === sample.sequence_id).length}`,
    );
    await setSearch(page, '');

    // ── W2-8 자료 카드 별표·메모가 재시작 후에도 남는다
    await clickChip(page, 'file');
    const target = await page.evaluate(() => {
      const card = document.querySelector('.glass-card[data-platform="file"]');
      return { key: card?.querySelector('.note-open-btn')?.dataset.postKey || '' };
    });
    cleanupKey = target.key;
    const NOTE = 'library-verify-메모';
    await page.evaluate((key) => {
      const card = document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.closest('.glass-card');
      card?.querySelector('.favorite-btn')?.click();
    }, target.key);
    await page.waitForTimeout(800);
    await page.evaluate((key) => document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.click(), target.key);
    await page.waitForTimeout(300);
    await page.evaluate(({ key, note }) => {
      const card = document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.closest('.glass-card');
      const input = card?.querySelector('.note-input');
      if (input) input.value = note;
      card?.querySelector('.note-save-btn')?.click();
    }, { key: target.key, note: NOTE });
    await page.waitForTimeout(900);
    restartProductionServer();
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForSelector('.glass-card', { timeout: 90000 });
    await clickChip(page, 'file');
    await loadAllCards(page);
    const persisted = await page.evaluate(({ key }) => {
      const card = document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.closest('.glass-card');
      return {
        found: !!card,
        star: !!card?.querySelector('.favorite-btn .text-yellow-400'),
        note: card?.querySelector('.note-text')?.textContent?.trim() || '',
      };
    }, { key: target.key });
    const savedMeta = await page.evaluate(async (key) => (await (await fetch('/api/get-user-metadata')).json())[key] || null, target.key);
    record(
      'W2-8 자료 카드 별표·메모가 서버 재시작 후에도 유지된다',
      target.key.startsWith('file:') && persisted.found && persisted.star && persisted.note === NOTE
        && savedMeta?.favorite === true && savedMeta?.note === NOTE,
      `${target.key} · 별표 ${persisted.star} · 메모 "${persisted.note}"`,
    );
    await shot(page, 'w2_star_note_after_restart');
    // 화면 조작으로 되돌린다: 별표 해제 + 메모 비우기(빈 메모는 저장 시 항목이 지워진다).
    await page.evaluate((key) => {
      const card = document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.closest('.glass-card');
      card?.querySelector('.favorite-btn')?.click();
    }, target.key);
    await page.waitForTimeout(800);
    await page.evaluate((key) => document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.click(), target.key);
    await page.waitForTimeout(300);
    await page.evaluate((key) => {
      const card = document.querySelector(`.note-open-btn[data-post-key="${CSS.escape(key)}"]`)?.closest('.glass-card');
      const input = card?.querySelector('.note-input');
      if (input) input.value = '';
      card?.querySelector('.note-save-btn')?.click();
    }, target.key);
    await page.waitForTimeout(900);
    const afterCleanup = await page.evaluate(async (key) => (await (await fetch('/api/get-user-metadata')).json())[key] || null, target.key);
    if (!afterCleanup) cleanupKey = '';

    // ── W2-9 표본 20건: 원문 마크다운의 표·제목·목록 수 = 화면 요소 수
    const byLength = [...visibleNotes].sort((a, b) => b.full_text.length - a.full_text.length);
    const byPath = [...visibleNotes].sort((a, b) => a.library_path.localeCompare(b.library_path));
    const samples = [...new Map([...byLength.slice(0, 10), ...byPath].map((p) => [p.sequence_id, p])).values()].slice(0, 20);
    const mismatches = [];
    for (const note of samples) {
      const expected = countMarkdownStructure(note.full_text);
      const actual = await page.evaluate((text) => {
        const div = document.createElement('div');
        div.innerHTML = renderLibraryMarkdown(text);
        return {
          headings: div.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
          tables: div.querySelectorAll('table').length,
          items: div.querySelectorAll('li').length,
          scripts: div.querySelectorAll('script,[onerror],[onload],a[href^="javascript"]').length,
        };
      }, note.full_text);
      if (actual.headings !== expected.headings || actual.tables !== expected.tables
        || actual.items !== expected.items || actual.scripts !== 0) {
        mismatches.push(`${note.library_path} 기대 ${JSON.stringify(expected)} 화면 ${JSON.stringify(actual)}`);
      }
    }
    record(
      'W2-9 표본 20건 표·제목·목록 수가 화면 요소와 같다',
      samples.length === 20 && mismatches.length === 0,
      mismatches.length ? mismatches.slice(0, 3).join(' | ') : `${samples.length}건 일치`,
    );

    // 가장 긴 노트를 실제 모달로 열어 렌더 시간을 잰다(계획 §7 리스크).
    const longest = byLength[0];
    await clickChip(page, longest.sns_platform);
    await setSearch(page, normalizeSearchText(longest.library_title).slice(0, 24));
    await page.evaluate((seq) => document.querySelector(`.glass-card[data-seq="${seq}"] [data-library-read]`)?.click(), longest.sequence_id);
    await waitLibraryModal(page);
    const renderMs = await page.evaluate(() => Number(document.getElementById('libraryNoteModal')?.dataset.renderMs || -1));
    record(
      'W2-10 가장 긴 노트 모달 렌더 시간(측정)',
      renderMs >= 0 && renderMs < 5000,
      `${longest.library_path} ${longest.full_text.length.toLocaleString()}자 · ${renderMs}ms`,
    );
    await shot(page, 'w2_longest_modal');
    await closeLibraryModal(page);
    await setSearch(page, '');

    // ── W2-11 CLI 에서도 자료가 조회된다
    const cli = (platform) => JSON.parse(execFileSync('node', ['utils/query-sns.mjs', 'by-platform', platform, '--limit', '1'], { encoding: 'utf8' }));
    const cliWeb = cli('web');
    const cliFile = cli('file');
    record(
      'W2-11 query-sns.mjs 로 자료가 조회된다',
      cliWeb.total_matches === visibleNotes.filter((p) => p.sns_platform === 'web').length
        && cliFile.total_matches === visibleNotes.filter((p) => p.sns_platform === 'file').length
        && !!cliWeb.posts[0]?.library_title,
      `web ${cliWeb.total_matches} · file ${cliFile.total_matches}`,
    );
  }

  if (WAVES.has('w3')) {
    // ── W3 겹침 「요약」 배지. 전체 목록(기본 필터)에서 카드마다 배지 수가 그 글의
    //    연결 요약본 수와 같아야 한다 - 연결 없는 카드에는 배지 요소가 0개다.
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForSelector('.glass-card', { timeout: 90000 });
    const bySeq = new Map(apiPosts.map((post) => [post.sequence_id, post]));
    await loadAllCards(page);
    const badgeRows = await page.evaluate(() => [...document.querySelectorAll('.glass-card')].map((card) => ({
      seq: Number(card.dataset.seq || 0),
      badges: card.querySelectorAll('.library-summary-badge').length,
    })));
    const wrong = badgeRows.filter((row) => row.badges !== ((bySeq.get(row.seq)?.library_notes || []).length));
    const totalBadges = badgeRows.reduce((sum, row) => sum + row.badges, 0);
    const expectedBadges = badgeRows.reduce((sum, row) => sum + ((bySeq.get(row.seq)?.library_notes || []).length), 0);
    const noLinkCards = badgeRows.filter((row) => !(bySeq.get(row.seq)?.library_notes || []).length);
    record(
      'W3-1 배지 수 = 화면 카드에 연결된 겹침 요약본 수',
      wrong.length === 0 && totalBadges === expectedBadges && totalBadges > 0,
      `배지 ${totalBadges} · 기대 ${expectedBadges} (겹침 전체 ${overlapNotes.length}, 기본 필터로 가려진 원문 카드 몫 제외) · 어긋난 카드 ${wrong.length}`,
    );
    record(
      'W3-2 연결 없는 카드에는 배지 요소가 0개다',
      noLinkCards.every((row) => row.badges === 0),
      `연결 없는 카드 ${noLinkCards.length}장`,
    );

    const badgeTarget = badgeRows.find((row) => row.badges > 0);
    const noteInfo = (bySeq.get(badgeTarget.seq)?.library_notes || [])[0];
    await page.evaluate((seq) => {
      const card = document.querySelector(`.glass-card[data-seq="${seq}"]`);
      card?.scrollIntoView({ block: 'center' });
      card?.querySelector('.library-summary-badge')?.click();
    }, badgeTarget.seq);
    await waitLibraryModal(page);
    const summaryState = await modalState(page, 'libraryNoteModal');
    const summaryTitle = await page.evaluate(() => document.getElementById('libraryNoteTitle')?.textContent?.trim() || '');
    record(
      'W3-3 「요약」 배지를 누르면 요약본 모달이 실제로 보인다(계산된 스타일)',
      summaryState.open && summaryTitle === noteInfo.title,
      `opacity ${summaryState.opacity} · pointer-events ${summaryState.pointerEvents} · "${summaryTitle}"`,
    );
    await shot(page, 'w3_summary_badge_modal');
    await closeLibraryModal(page);
  }

  if (WAVES.has('w4')) {
    // ── W4 모든 카드의 제작자 프로필
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForSelector('.glass-card', { timeout: 90000 });
    const w4Posts = await page.evaluate(async () => (await (await fetch('/api/posts')).json()).posts);
    await loadAllCards(page);
    const iconInfo = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.glass-card')];
      return {
        cards: cards.length,
        withIcon: cards.filter((card) => card.querySelector('.creator-btn')).length,
        kinds: {
          account: document.querySelectorAll('.glass-card [data-creator-account]').length,
          creator: document.querySelectorAll('.glass-card [data-creator-id]').length,
          author: document.querySelectorAll('.glass-card [data-author-card]').length,
        },
      };
    });
    record(
      'W4-1 이름 옆 아이콘 수 = 목록 카드 수(전량)',
      iconInfo.cards > 0 && iconInfo.withIcon === iconInfo.cards,
      `카드 ${iconInfo.cards} · 아이콘 ${iconInfo.withIcon} ${JSON.stringify(iconInfo.kinds)}`,
    );

    const openCardFor = async (post, selector) => {
      await setSearch(page, normalizeSearchText(post.full_text_preview).slice(0, 30));
      await page.evaluate(({ seq, sel }) => {
        const card = document.querySelector(`.glass-card[data-seq="${seq}"]`);
        card?.scrollIntoView({ block: 'center' });
        card?.querySelector(sel)?.click();
      }, { seq: post.sequence_id, sel: selector });
      await page.waitForFunction(() => {
        const body = document.getElementById('creatorCardBody');
        return document.getElementById('creatorCardModal')?.classList.contains('show')
          && body && !body.textContent.includes('불러오는 중');
      }, null, { timeout: 30000 });
      await page.waitForTimeout(400);
    };
    const closeCreator = async () => {
      await page.evaluate(() => document.getElementById('closeCreatorCardModal')?.click());
      await page.waitForTimeout(400);
    };
    const visibleByDefault = (post) => !hiddenKeys.has(post.post_key) && post.is_own_post !== true && post.is_saved !== false;

    // W4-2 볼트 프로필이 있는 스레드 작성자 카드에 프로필 본문이 보인다.
    let threadsTarget = null;
    for (const post of w4Posts) {
      if (post.sns_platform !== 'threads' || !post.creator_id || (post.benchmark_accounts || []).length) continue;
      if (!visibleByDefault(post) || normalizeSearchText(post.full_text_preview).length < 40) continue;
      const profile = await page.evaluate(async (id) => (await fetch(`/api/creator-profile?creator_id=${encodeURIComponent(id)}`)).json(), post.creator_id);
      if (profile.found && String(profile.profile_text || '').trim()) {
        threadsTarget = { post, profile };
        break;
      }
    }
    await openCardFor(threadsTarget.post, '[data-creator-id]');
    const creatorView = await page.evaluate(() => ({
      title: document.getElementById('creatorCardTitle')?.textContent?.trim() || '',
      profileText: document.querySelector('#creatorCardBody .creator-profile-text')?.textContent?.trim() || '',
      stats: [...document.querySelectorAll('#creatorCardBody .creator-stat')].map((e) => e.textContent.trim()),
      hasAll: !!document.querySelector('#creatorCardBody [data-creator-all]'),
    }));
    const creatorModal = await modalState(page, 'creatorCardModal');
    record(
      'W4-2 볼트 프로필이 있는 스레드 작성자 카드에 프로필 본문이 보인다',
      creatorModal.open && creatorView.profileText.length > 10 && creatorView.title === threadsTarget.profile.name
        && creatorView.stats.some((s) => s.startsWith('Threads')) && creatorView.hasAll,
      `${creatorView.title} · ${creatorView.stats.join(',')} · 프로필 ${creatorView.profileText.length}자`,
    );
    await shot(page, 'w4_creator_card');
    // 「이 사람 글 전체 보기」 → 그 제작자 글만(SNS + 자료)
    await page.evaluate(() => document.querySelector('#creatorCardBody [data-creator-all]')?.click());
    await page.waitForTimeout(800);
    await setSearch(page, '');
    const creatorCards = await loadAllCards(page);
    const expectedCreatorPosts = w4Posts.filter((p) => p.creator_id === threadsTarget.post.creator_id && !hiddenKeys.has(p.post_key)).length;
    record(
      'W4-2b 「이 사람 글 전체 보기」가 그 제작자 글(SNS+자료)만 보인다',
      creatorCards.length === expectedCreatorPosts,
      `카드 ${creatorCards.length} · 기대 ${expectedCreatorPosts}`,
    );
    await page.evaluate(() => document.querySelector('[data-creator-filter-badge]')?.click());
    await page.waitForTimeout(600);

    // W4-3 연결 없는 링크드인 저자 카드 — 한 줄 소개가 보이고 빈 섹션이 없다.
    const linkedinTarget = w4Posts.find((post) => post.sns_platform === 'linkedin' && !post.creator_id
      && !(post.benchmark_accounts || []).length && String(post.profile_slogan || '').trim()
      && visibleByDefault(post) && normalizeSearchText(post.full_text_preview).length > 40);
    await openCardFor(linkedinTarget, '[data-author-card]');
    const authorView = await page.evaluate(() => {
      const sections = [...document.querySelectorAll('#creatorCardBody .creator-sec')];
      return {
        slogan: document.querySelector('#creatorCardBody .author-slogan')?.textContent?.trim() || '',
        empty: sections.filter((sec) => {
          const title = sec.querySelector('.creator-sec-title')?.textContent || '';
          return sec.textContent.replace(title, '').trim().length === 0;
        }).length,
        sections: sections.length,
      };
    });
    record(
      'W4-3 연결 없는 링크드인 저자 카드에 한 줄 소개가 보이고 빈 섹션이 없다',
      authorView.slogan === String(linkedinTarget.profile_slogan).trim() && authorView.empty === 0 && authorView.sections >= 2,
      `섹션 ${authorView.sections} · 빈 섹션 ${authorView.empty} · 소개 "${authorView.slogan.slice(0, 40)}"`,
    );
    await shot(page, 'w4_author_card');
    await closeCreator();
    await setSearch(page, '');

    // W4-5 creator_id 경로 이탈 값은 거부된다.
    const traversal = await page.evaluate(async () => Promise.all(
      ['../x', '..\\x', 'a/b', '..'].map(async (probe) => (await fetch(`/api/creator-profile?creator_id=${encodeURIComponent(probe)}`)).status),
    ));
    record('W4-5 creator_id 에 ../ 등 경로 이탈 값을 넣으면 거부된다', traversal.every((status) => status === 400), traversal.join(','));

    // W4-4 연결을 저장하면 두 플랫폼 글 수가 한 카드에 합쳐지고 재시작 후에도 유지된다.
    // 운영 연결 파일을 쓰지 않도록 전용 서버 + 임시 연결 파일로 본다.
    const linksDir = fs.mkdtempSync(path.join(process.env.TEMP || '.', 'sns-links-verify-'));
    const linksPath = path.join(linksDir, 'sns_creator_links.json');
    const authorOf = (post) => `${post.sns_platform}|${post.username}`;
    const counts = new Map();
    w4Posts.forEach((post) => {
      if (post.creator_id || !post.username || post.sns_platform === 'web' || post.sns_platform === 'file') return;
      counts.set(authorOf(post), (counts.get(authorOf(post)) || 0) + 1);
    });
    const threadsAuthor = w4Posts.find((post) => post.sns_platform === 'threads' && !post.creator_id
      && visibleByDefault(post) && normalizeSearchText(post.full_text_preview).length > 40 && counts.get(authorOf(post)) >= 2);
    const xAuthor = w4Posts.find((post) => post.sns_platform === 'x' && !post.creator_id && post.username
      && (post.display_name || '').length >= 2);
    let linkServer = await startLibraryVerifyServer({ linksPath });
    try {
      const page3 = await context.newPage();
      page3.on('dialog', (dialog) => dialog.accept());
      await page3.goto(linkServer.baseUrl, { waitUntil: 'networkidle', timeout: 90000 });
      await page3.waitForSelector('.glass-card', { timeout: 90000 });
      await setSearch(page3, normalizeSearchText(threadsAuthor.full_text_preview).slice(0, 30));
      await page3.evaluate((seq) => document.querySelector(`.glass-card[data-seq="${seq}"] [data-author-card]`)?.click(), threadsAuthor.sequence_id);
      await page3.waitForFunction(() => document.getElementById('creatorCardModal')?.classList.contains('show'), null, { timeout: 30000 });
      await page3.evaluate(() => document.querySelector('#creatorCardBody [data-link-open]')?.click());
      await typeInto(page3, '#creatorCardBody .creator-link-input', xAuthor.display_name || xAuthor.username);
      await page3.waitForTimeout(400);
      await page3.evaluate((key) => {
        [...document.querySelectorAll('#creatorCardBody .creator-link-result')]
          .find((btn) => btn.dataset.linkPlatform === 'x' && btn.dataset.linkKey === key)?.click();
      }, xAuthor.username);
      await page3.waitForFunction(() => {
        const title = document.getElementById('creatorCardModal')?.dataset.creatorId || '';
        return title.startsWith('link_') && !document.getElementById('creatorCardBody')?.textContent.includes('불러오는 중');
      }, null, { timeout: 60000 });
      await page3.waitForTimeout(500);
      const merged = await page3.evaluate(() => [...document.querySelectorAll('#creatorCardBody .creator-stat')].map((e) => e.textContent.trim()));
      await shot(page3, 'w4_linked_creator_card');
      await page3.close();
      await linkServer.stop();

      linkServer = await startLibraryVerifyServer({ linksPath });
      // node 내장 fetch 는 gzip 대용량 응답에서 undici 단언으로 죽는다 - 브라우저로 받는다.
      const page4 = await context.newPage();
      await page4.goto(`${linkServer.baseUrl}api/status`, { timeout: 60000 });
      const afterRestart = await page4.evaluate(async () => (await fetch('/api/posts')).json());
      await page4.close();
      const linkedId = `link_threads_${String(threadsAuthor.username).toLowerCase()}`;
      const linkedPosts = afterRestart.posts.filter((post) => post.creator_id === linkedId);
      const threadsCount = linkedPosts.filter((p) => p.sns_platform === 'threads').length;
      const xCount = linkedPosts.filter((p) => p.sns_platform === 'x').length;
      record(
        'W4-4 연결 저장 → 두 플랫폼 글 수가 한 카드에 합쳐지고 재시작 후에도 유지된다',
        merged.includes(`Threads ${counts.get(authorOf(threadsAuthor))}`) && merged.some((s) => s.startsWith('X '))
          && threadsCount === counts.get(authorOf(threadsAuthor)) && xCount === counts.get(authorOf(xAuthor)),
        `카드 ${merged.join(',')} · 재시작 후 ${linkedId}: threads ${threadsCount} · x ${xCount}`,
      );
    } finally {
      await linkServer.stop();
      fs.rmSync(linksDir, { recursive: true, force: true });
    }
  }

  // ── 회귀: 벤치마킹 표식·사용자 메타가 W0 기준선과 같다
  const finalPosts = await page.evaluate(async () => (await (await fetch('/api/posts')).json()).posts);
  const finalMeta = await page.evaluate(async () => (await fetch('/api/get-user-metadata')).json());
  const values = Object.values(finalMeta);
  const metaNow = {
    entries: values.length,
    favorites: values.filter((v) => v?.favorite).length,
    hidden: values.filter((v) => v?.hidden).length,
    notes: values.filter((v) => String(v?.note || '').trim()).length,
  };
  const benchmarkNow = finalPosts.filter((post) => (post.benchmark_accounts || []).length).length;
  record(
    'R 회귀: 벤치마킹 표식·사용자 메타 건수가 W0 기준선과 같다',
    benchmarkNow === baseline.benchmarkMarked && metaNow.entries === baseline.metaEntries
      && metaNow.favorites === baseline.favorites && metaNow.hidden === baseline.hidden && metaNow.notes === baseline.notes,
    `표식 ${benchmarkNow}/${baseline.benchmarkMarked} · 메타 ${JSON.stringify(metaNow)}`,
  );
  record('R 페이지 스크립트 오류 없음', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

  // ── 표본 볼트 전용 서버: 볼트 편집 반영 + 악성 노트 렌더
  if (WAVES.has('w2')) {
    const verify = await startLibraryVerifyServer();
    try {
      const page2 = await context.newPage();
      page2.on('dialog', (dialog) => dialog.accept());
      await page2.goto(verify.baseUrl, { waitUntil: 'networkidle', timeout: 90000 });
      await page2.waitForSelector('.glass-card', { timeout: 90000 });
      await clickChip(page2, 'file');
      await loadAllCards(page2);
      const opened = await page2.evaluate(() => {
        const card = [...document.querySelectorAll('.glass-card[data-platform="file"]')]
          .find((c) => c.querySelector('.library-title')?.textContent?.includes('악성 표본'));
        card?.querySelector('[data-library-read]')?.click();
        return !!card;
      });
      await waitLibraryModal(page2);
      const safety = await page2.evaluate(() => {
        const body = document.getElementById('libraryNoteBody');
        return {
          xss: window.__libraryXss === undefined ? 'none' : String(window.__libraryXss),
          scripts: body.querySelectorAll('script').length,
          handlers: [...body.querySelectorAll('*')].filter((el) => [...el.attributes].some((a) => a.name.startsWith('on'))).length,
          jsLinks: body.querySelectorAll('a[href^="javascript"],img[src^="javascript"]').length,
          tables: body.querySelectorAll('table').length,
          th: body.querySelectorAll('th').length,
          td: body.querySelectorAll('td').length,
          wikilink: body.querySelector('.library-wikilink')?.textContent || '',
          safeLink: !!body.querySelector('a[href="https://example.com/a?b=1&c=2"]'),
          scriptText: body.textContent.includes('<script>'),
        };
      });
      const modalOpen = await modalState(page2, 'libraryNoteModal');
      record(
        'W2-12 악성 노트: 스크립트·이벤트·javascript: 가 실행되지 않고 표는 표로 그려진다',
        opened && modalOpen.open && safety.xss === 'none' && safety.scripts === 0 && safety.handlers === 0
          && safety.jsLinks === 0 && safety.tables === 1 && safety.th === 2 && safety.td === 4
          && safety.wikilink === '표시 이름' && safety.safeLink && safety.scriptText,
        JSON.stringify(safety),
      );
      await shot(page2, 'w2_malicious_note');
      await closeLibraryModal(page2);

      // 볼트 노트 제목 한 글자를 고치면 60초 안에 목록과 ETag 가 바뀐다.
      const before = await page2.evaluate(async () => {
        const res = await fetch('/api/posts', { cache: 'no-store' });
        const posts = (await res.json()).posts;
        return { etag: res.headers.get('ETag'), title: posts.find((p) => p.platform_id === '20260102_파일자료_라마바')?.library_title };
      });
      const notePath = path.join(verify.vaultPath, 'AI일반', '20260102_파일자료_라마바.md');
      fs.writeFileSync(notePath, fs.readFileSync(notePath, 'utf8').replace('title: 파일 자료 표본', 'title: 파일 자료 표본!'), 'utf8');
      const started = Date.now();
      let after = before;
      while (Date.now() - started < 60000) {
        await page2.waitForTimeout(3000);
        after = await page2.evaluate(async () => {
          const res = await fetch('/api/posts', { cache: 'no-store' });
          const posts = (await res.json()).posts;
          return { etag: res.headers.get('ETag'), title: posts.find((p) => p.platform_id === '20260102_파일자료_라마바')?.library_title };
        });
        if (after.title !== before.title) break;
      }
      const elapsed = Math.round((Date.now() - started) / 1000);
      record(
        'W2-13 볼트 노트 제목을 고치면 60초 안에 /api/posts 와 ETag 가 바뀐다',
        after.title === '파일 자료 표본!' && after.etag !== before.etag && elapsed <= 60,
        `${elapsed}초 · "${before.title}" → "${after.title}"`,
      );
      await page2.close();
    } finally {
      await verify.stop();
    }
  }

  console.log(`\n증거: ${shots.join(', ')}`);
  console.log(`      ${EVIDENCE_DIR}`);
} finally {
  if (cleanupKey) {
    // 화면 조작 되돌리기가 실패했을 때만 API 로 지운다.
    try {
      const meta = await (await fetch(`${BASE_URL}/api/get-user-metadata`)).json();
      delete meta[cleanupKey];
      await fetch(`${BASE_URL}/api/save-user-metadata`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta),
      });
      console.log(`정리: ${cleanupKey} 를 API 로 지웠다`);
    } catch (error) {
      console.log(`⚠️ 정리 실패 — ${cleanupKey} 가 사용자 메타에 남았을 수 있다: ${error}`);
    }
  }
  await browser.close();
}

const failed = checks.filter((check) => !check.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
if (failed.length) {
  console.log(`실패: ${failed.map((check) => check.name).join(' / ')}`);
  process.exit(1);
}
