/**
 * 내 글(MY)이 뷰어 화면에 제대로 뜨는지 창 없이 검증한다.
 *
 * 계획: _docs/20260909_02_내글수집기-Buffer전환대응과-Threads댓글수-부풀림-수행계획.md (T9, §5-8)
 *
 * 이 검증이 잡는 것 둘:
 *   1) LinkedIn 식별자 이관(T3)이 빠지면 같은 글이 두 벌 뜬다. 37 → 74.
 *      회귀 가드는 감소만 막아서 조용히 통과한다.
 *   2) Threads 합본 보존(T5)이 깨지면 본문이 16,480자 → 9,352자로 준다(43%).
 *      건수는 그대로라 화면에서 눈으로 알 수 없다.
 *
 * 창을 띄우지 않는다. 판정은 종료코드 0/1 이고 캡처는 증거의 보조다.
 *
 * 사용:
 *   node scripts/verify_own_posts_headless.mjs [--shot <png path>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const TOTAL_DIR = 'output_total';

/** 합본 본문 길이 하한. 2026-09-09 실측값이고, T5 가 깨지면 9,352자로 떨어진다. */
const MERGED_BODY_MIN_CHARS = 16480;
/** 합본 글 수 하한. 같은 실측 기준. */
const MERGED_POST_MIN = 22;

const shotIndex = process.argv.indexOf('--shot');
const shotPath =
  shotIndex !== -1
    ? process.argv[shotIndex + 1]
    : path.join('_docs', 'evidence', '20260909_02', 'my_posts_no_duplicates.png');

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude',
  'skills',
  '_shared',
  'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const failed = [];
function record(ok, label, detail = '') {
  console.log(`${ok ? '✅' : '❌'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failed.push(label);
}

function latestTotalFile() {
  const files = fs
    .readdirSync(TOTAL_DIR)
    .filter(name => /^total_full_\d+\.json$/.test(name))
    .sort()
    .reverse();
  return files.length ? path.join(TOTAL_DIR, files[0]) : null;
}

function readTotal(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  const data = JSON.parse(text);
  return Array.isArray(data) ? data : data.posts || [];
}

async function main() {
  const totalPath = latestTotalFile();
  if (!totalPath) {
    console.error('❌ output_total 파일을 찾을 수 없습니다.');
    return 1;
  }

  const posts = readTotal(totalPath);
  const ownPosts = posts.filter(p => p && p.is_own_post);
  const mergedPosts = ownPosts.filter(p => p.is_merged_thread);
  console.log(`기준 파일: ${totalPath}`);
  console.log(`  전체 ${posts.length}건 / 내 글 ${ownPosts.length}건 / 합본 ${mergedPosts.length}건`);

  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (npm run restart).');
      return 1;
    }
    await page.waitForTimeout(2500);

    // --- 단언 C: 뷰어가 최신 통합본을 통째로 실었다 -------------------------
    //
    // 🔴 상단 라벨과 파일 총건수를 맞추지 않는다. 그 라벨은 총계가 아니라
    //    **지금 화면에 걸린 수**다(web_viewer/script.js:342-364, 계획 20260827_05 T5).
    //    비활성 벤치마킹 계정 글과 숨김 글이 빠지므로 파일보다 작은 것이 정상이다
    //    (실측 2026-09-09: 파일 2,882 vs 라벨 2,804).
    //    「데이터가 다 실렸는가」는 뷰어가 실제로 읽는 API 로 잰다.
    const apiCount = await page.evaluate(async () => {
      const res = await fetch('/api/posts');
      if (!res.ok) return -1;
      const data = await res.json();
      return (Array.isArray(data) ? data : data.posts || []).length;
    });
    record(
      apiCount === posts.length,
      'C. 뷰어 API 건수 == 통합본 게시글 수',
      `API ${apiCount}, 파일 ${posts.length}`
    );

    const headerText = await page.evaluate(() => document.body.innerText || '');
    const headerNumbers = [...headerText.matchAll(/([\d,]{2,})\s*건/g)].map(m =>
      Number(m[1].replace(/,/g, ''))
    );
    console.log(`   (참고) 상단 표시 건수: ${headerNumbers.join(', ') || '없음'} — 필터 반영값이라 파일 총건수와 다를 수 있음`);

    // --- MY 필터를 켠다 -----------------------------------------------------
    const myButton = await page.$('#myPostsBtn');
    if (!myButton) {
      record(false, 'MY 버튼을 찾지 못함 (#myPostsBtn)');
      return 1;
    }
    await myButton.click();
    await page.waitForTimeout(1200);

    // 무한 스크롤이라 카드가 60건씩 붙는다. 전부 렌더될 때까지 내린다.
    let previous = -1;
    for (let i = 0; i < 20; i += 1) {
      const count = await page.evaluate(() => document.querySelectorAll('article[data-platform-id]').length);
      if (count === previous) break;
      previous = count;
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(600);
    }

    const renderedIds = await page.evaluate(() =>
      [...document.querySelectorAll('article[data-platform-id]')].map(el => el.dataset.platformId)
    );

    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.log(`스크린샷: ${shotPath}`);
    }

    // --- 단언 A: 렌더된 카드 식별자에 중복이 없다 ---------------------------
    const seen = new Map();
    for (const id of renderedIds) seen.set(id, (seen.get(id) || 0) + 1);
    const duplicates = [...seen.entries()].filter(([, n]) => n > 1);
    record(
      duplicates.length === 0,
      'A. MY 카드 식별자 중복 0건',
      duplicates.length
        ? `중복 ${duplicates.length}종: ${duplicates.slice(0, 5).map(([id, n]) => `${id}x${n}`).join(', ')}`
        : `카드 ${renderedIds.length}장`
    );

    // --- 단언 B: MY 카드 수 == 통합본 is_own_post 건수 ----------------------
    record(
      renderedIds.length === ownPosts.length,
      'B. MY 카드 수 == 통합본 내 글 수',
      `화면 ${renderedIds.length}, 파일 ${ownPosts.length}`
    );

    // --- 단언 D: 합본 본문이 줄지 않았다 ------------------------------------
    // 카드 본문은 200자로 잘려 렌더되므로 뷰어 자신의 상세 API 로 전문을 받는다.
    const mergedSeqIds = mergedPosts.map(p => p.sequence_id).filter(Boolean);
    const bodyTotal = await page.evaluate(async ids => {
      let total = 0;
      for (const id of ids) {
        try {
          const res = await fetch(`/api/post/${id}`);
          if (!res.ok) continue;
          const data = await res.json();
          const post = data.post || data;
          total += String(post.full_text || '').length;
        } catch (error) {
          /* 한 건 실패로 합계 판정을 멈추지 않는다 - 미달로 드러난다 */
        }
      }
      return total;
    }, mergedSeqIds);

    record(
      mergedPosts.length >= MERGED_POST_MIN,
      'D-1. 합본 글 수 유지',
      `${mergedPosts.length}건 (하한 ${MERGED_POST_MIN})`
    );
    record(
      bodyTotal >= MERGED_BODY_MIN_CHARS,
      'D-2. 합본 본문 길이 유지',
      `${bodyTotal.toLocaleString()}자 (하한 ${MERGED_BODY_MIN_CHARS.toLocaleString()})`
    );

    return failed.length ? 1 : 0;
  } finally {
    await browser.close();
  }
}

const code = await main();
if (failed.length) console.error(`\n실패 ${failed.length}건: ${failed.join(' / ')}`);
else if (code === 0) console.log('\n전부 통과');
process.exit(code);
