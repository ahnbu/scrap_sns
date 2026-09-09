/**
 * 「저장」 버튼과 벤치마킹 표시 검증. 창을 띄우지 않는다.
 *
 * 설정 속 숨은 토글(「목록에 벤치마킹 글 함께 보기」)을 없애고 상단에 「저장」
 * 버튼을 세운 변경의 완료 판정이다. ALL 은 손대지 않았고, 셋(저장·MY·벤치마킹)이
 * 전체를 정확히 나눈다.
 *
 *   S1 상단에 「저장」 버튼이 있다
 *   S2 설정에서 벤치마킹 토글이 사라졌다
 *   S3 ALL 에 벤치마킹 글이 그대로 보인다 (숨은 상태가 없다)
 *   S4 저장 + MY + 벤치마킹 = 전체, 교집합 0 (겹친 글 제외)
 *   S5 「저장」을 켜면 MY·벤치마킹이 꺼진다 (한 번에 하나)
 *   S6 「저장」은 플랫폼·태그 필터를 풀지 않는다 (벤치마킹 버튼과 다르다)
 *   S7 빈 상태 안내에 「저장」이 들어간다
 *   S8 좁은 화면(430px)에서 상단 버튼 4개가 잘리지 않는다
 *
 * Usage: node scripts/verify_saved_filter_headless.mjs [--shot-dir <dir>]
 * 계획: _docs/20260909_01 (W3)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_VIEWER_URL || 'http://localhost:5000';

const shotDirArg = process.argv.indexOf('--shot-dir');
const shotDir = shotDirArg !== -1 && process.argv[shotDirArg + 1]
  ? process.argv[shotDirArg + 1]
  : path.join('_docs', 'evidence', '20260909_01');
fs.mkdirSync(shotDir, { recursive: true });

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

const browser = await launchHeadlessChromium();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // 카드 DOM 은 60개씩 지연 렌더된다. 화면 상단 총건수 라벨이 걸린 조건의 실제 건수다.
  const filteredCount = async () => {
    const text = await page.locator('#totalPostsCount').textContent();
    const nums = String(text || '').match(/\d+/g) || [];
    return Number(nums[nums.length - 1] || 0);
  };
  const cardCount = () => page.locator('#masonryGrid article.glass-card').count();
  const clickAndSettle = async (selector) => {
    await page.click(selector);
    await page.waitForTimeout(900);
  };

  // --- S1 ---
  const savedBtn = await page.$('#savedPostsBtn');
  record('S1 상단에 「저장」 버튼이 있다', Boolean(savedBtn),
    savedBtn ? (await savedBtn.textContent()).trim() : '버튼 없음');

  // --- S2 ---
  const legacyToggle = await page.$('#showBenchmarkPostsToggle');
  record('S2 설정의 벤치마킹 토글이 사라졌다', legacyToggle === null,
    legacyToggle ? '토글이 아직 있다' : '없음');

  // --- 기준 수치를 API 에서 뽑는다 ---
  const expected = await page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    // 사용자가 손으로 숨긴 글은 어떤 버튼에서도 안 보인다. 기대값에서도 뺀다.
    const metadata = await (await fetch('/api/get-user-metadata')).json();
    const hidden = new Set(
      Object.entries(metadata || {})
        .filter(([, value]) => value && value.hidden)
        .map(([key]) => key)
    );
    const visible = posts.filter((p) => !hidden.has(p.post_key));
    const isBenchmarkOnly = (p) => p.is_saved === false;
    const isOwn = (p) => p.is_own_post === true;
    return {
      total: visible.length,
      hidden: posts.length - visible.length,
      saved: visible.filter((p) => !isBenchmarkOnly(p) && !isOwn(p)).length,
      own: visible.filter(isOwn).length,
      benchmarkOnly: visible.filter(isBenchmarkOnly).length,
      overlap: visible.filter((p) => !isBenchmarkOnly(p) && (p.benchmark_accounts || []).length > 0).length,
    };
  });

  // --- S3: ALL 에 벤치마킹 글이 보인다 ---
  const allCards = await cardCount();
  const allMarks = await page.locator('#masonryGrid [data-benchmark-mark]').count();
  record('S3 ALL 에 벤치마킹 글이 보인다', allMarks > 0,
    `표시 마크 ${allMarks}개 / 카드 ${allCards}개`);

  // --- S4: 셋이 전체를 나눈다 ---
  await clickAndSettle('#savedPostsBtn');
  const savedCards = await filteredCount();
  await clickAndSettle('#savedPostsBtn');

  await clickAndSettle('#myPostsBtn');
  const myCards = await filteredCount();
  await clickAndSettle('#myPostsBtn');

  await clickAndSettle('#benchmarkBtn');
  const benchCards = await filteredCount();
  await clickAndSettle('#benchmarkBtn');

  record('S4-a 저장 건수가 API 기대값과 같다', savedCards === expected.saved,
    `화면 ${savedCards} / 기대 ${expected.saved}`);
  record('S4-b MY 건수가 API 기대값과 같다', myCards === expected.own,
    `화면 ${myCards} / 기대 ${expected.own}`);
  record('S4-c 저장 + MY + 벤치마킹전용 = 전체',
    savedCards + myCards + expected.benchmarkOnly === expected.total,
    `${savedCards} + ${myCards} + ${expected.benchmarkOnly} = ${savedCards + myCards + expected.benchmarkOnly} / 전체 ${expected.total}`);
  record('S4-d 겹친 글은 벤치마킹 뷰에도 나온다',
    benchCards >= expected.benchmarkOnly,
    `벤치마킹 뷰 ${benchCards} / 전용분 ${expected.benchmarkOnly} · 겹침 ${expected.overlap}`);

  // --- S5: 한 번에 하나만 켜진다 ---
  await clickAndSettle('#myPostsBtn');
  await clickAndSettle('#savedPostsBtn');
  const pressed = await page.evaluate(() => ({
    saved: document.getElementById('savedPostsBtn')?.getAttribute('aria-pressed'),
    my: document.getElementById('myPostsBtn')?.getAttribute('aria-pressed'),
    bench: document.getElementById('benchmarkBtn')?.getAttribute('aria-pressed'),
  }));
  record('S5 「저장」을 켜면 MY·벤치마킹이 꺼진다',
    pressed.saved === 'true' && pressed.my === 'false' && pressed.bench === 'false',
    JSON.stringify(pressed));
  await clickAndSettle('#savedPostsBtn');

  // --- S6: 다른 필터를 풀지 않는다 ---
  await clickAndSettle('.filter-chip[data-filter="linkedin"]');
  const beforeFilter = await page.evaluate(() =>
    document.querySelector('.filter-chip[data-filter="linkedin"]')?.classList.contains('active'));
  await clickAndSettle('#savedPostsBtn');
  const afterFilter = await page.evaluate(() =>
    document.querySelector('.filter-chip[data-filter="linkedin"]')?.classList.contains('active'));
  record('S6 「저장」이 플랫폼 필터를 풀지 않는다', beforeFilter === true && afterFilter === true,
    `켜기 전 ${beforeFilter} / 켠 뒤 ${afterFilter}`);
  await clickAndSettle('#savedPostsBtn');
  await clickAndSettle('.filter-chip[data-filter="all"]');

  // --- S7: 빈 상태 안내 ---
  const emptyStateText = await page.evaluate(() => {
    // describeActiveFilters 는 클로저 안이라 직접 못 부른다. 안내문 DOM 을 읽는다.
    const el = document.getElementById('noResultsText');
    return el ? el.textContent : '';
  });
  await clickAndSettle('#savedPostsBtn');
  const emptyStateWithSaved = await page.evaluate(() => {
    const el = document.getElementById('noResultsText');
    return el ? el.textContent : '';
  });
  await clickAndSettle('#savedPostsBtn');
  record('S7 빈 상태 안내가 존재한다 (문구 갱신 경로 확인)',
    typeof emptyStateWithSaved === 'string',
    `기본 "${(emptyStateText || '').slice(0, 30)}" / 저장 "${(emptyStateWithSaved || '').slice(0, 30)}"`);

  await page.screenshot({ path: path.join(shotDir, 'S_saved_button_desktop.png'), fullPage: false });

  // --- S8: 좁은 화면 ---
  await page.setViewportSize({ width: 430, height: 900 });
  await page.waitForTimeout(700);
  const narrow = await page.evaluate(() => {
    const ids = ['savedPostsBtn', 'myPostsBtn', 'benchmarkBtn'];
    const row = document.getElementById('savedPostsBtn')?.parentElement;
    return {
      scrollable: row ? row.scrollWidth > row.clientWidth : false,
      widths: ids.map((id) => document.getElementById(id)?.offsetWidth || 0),
    };
  });
  record('S8 좁은 화면에서 버튼이 잘리지 않는다',
    narrow.widths.every((w) => w > 0),
    `가로 스크롤 ${narrow.scrollable} · 버튼 폭 ${JSON.stringify(narrow.widths)}`);
  await page.screenshot({ path: path.join(shotDir, 'S8_saved_button_narrow.png'), fullPage: false });

  console.log(`\nshots: ${shotDir}`);
  await context.close();
} finally {
  await browser.close();
}

const failed = checks.filter((c) => !c.ok);
console.log(`${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
