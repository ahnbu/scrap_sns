/**
 * Headless viewer check: X 카드에 표시되는 게시일시가 KST 기준인지 확인한다.
 *
 * 창을 띄우지 않으므로 사용자 포커스를 뺏지 않고, 0/1 로 종료해 완료 게이트가
 * 스크린샷을 사람이 보지 않고도 판정할 수 있다. --shot 캡처는 보조 증거이고
 * 판정은 종료코드가 한다.
 *
 * 검증 방식은 두 겹이다.
 *   1. 뷰어가 표시한 시각이 최신 output_total 의 값과 같은가 (화면 ↔ 저장 데이터)
 *   2. 그 값이 트윗 Snowflake ID 에서 복원한 KST 와 같은가 (저장 데이터 ↔ 정답)
 * 2번이 있어야 "둘 다 똑같이 틀린" 상태를 통과시키지 않는다.
 *
 * Usage:
 *   node scripts/verify_twitter_created_at_kst_headless.mjs [--shot <png path>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const TOTAL_DIR = 'output_total';
const X_SNOWFLAKE_EPOCH_MS = 1288834974657n;
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

const shotIndex = process.argv.indexOf('--shot');
const shotPath = shotIndex !== -1 ? process.argv[shotIndex + 1] : null;

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude',
  'skills',
  '_shared',
  'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

function latestTotalFile() {
  const files = fs
    .readdirSync(TOTAL_DIR)
    .filter(name => /^total_full_\d+\.json$/.test(name))
    .sort()
    .reverse();
  return files.length ? path.join(TOTAL_DIR, files[0]) : null;
}

function readPosts(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  const data = JSON.parse(text);
  return Array.isArray(data) ? data : data.posts || [];
}

/** 트윗 Snowflake ID → KST 'YYYY-MM-DD HH:mm:ss'. 복원 불가면 null. */
function kstFromId(platformId) {
  const text = String(platformId ?? '').trim();
  if (!/^\d+$/.test(text)) return null;
  const ms = (BigInt(text) >> 22n) + X_SNOWFLAKE_EPOCH_MS;
  if (ms <= X_SNOWFLAKE_EPOCH_MS) return null;
  return new Date(Number(ms) + KST_OFFSET_MS).toISOString().slice(0, 19).replace('T', ' ');
}

async function main() {
  const totalPath = latestTotalFile();
  if (!totalPath) {
    console.error('❌ output_total 파일을 찾을 수 없습니다.');
    return 1;
  }

  const xPosts = readPosts(totalPath).filter(p => (p.sns_platform || p.platform) === 'x');
  if (!xPosts.length) {
    console.error(`❌ ${totalPath} 에 X 레코드가 없습니다.`);
    return 1;
  }
  console.log(`기준 파일: ${totalPath} (X ${xPosts.length}건)`);

  // 1겹: 저장 데이터가 Snowflake 정답과 맞는가
  const dataMismatch = [];
  for (const post of xPosts) {
    const expected = kstFromId(post.platform_id);
    if (expected === null) continue;
    if (post.created_at !== expected) {
      dataMismatch.push(`${post.platform_id}: 저장=${post.created_at} 기대=${expected}`);
    }
  }
  if (dataMismatch.length) {
    console.error(`❌ 저장 데이터가 Snowflake 기준과 불일치: ${dataMismatch.length}건`);
    dataMismatch.slice(0, 5).forEach(line => console.error(`   ${line}`));
    return 1;
  }
  console.log(`✅ 저장 데이터 ↔ Snowflake 복원값 일치 (X ${xPosts.length}건)`);

  // 2겹: 뷰어 화면이 그 값을 그대로 보여주는가
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

    // 초기 화면은 전 플랫폼 최신순이라 X 카드가 한 장도 없을 수 있다.
    // 상단 플랫폼 칩에서 X 를 눌러 대상만 띄운다 (index.html data-filter="x").
    const xChip = page.locator('.filter-chip[data-filter="x"]');
    if ((await xChip.count()) === 0) {
      console.error('❌ 뷰어에서 X 플랫폼 칩(.filter-chip[data-filter="x"])을 찾지 못했습니다.');
      return 1;
    }
    await xChip.first().click();
    await page.waitForTimeout(2000);

    const bodyText = await page.evaluate(() => document.body.innerText || '');

    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.log(`스크린샷: ${shotPath}`);
    }

    // 뷰어는 날짜를 한국 로케일(`2026. 4. 24.`)로 그리고, 카드 정렬은 created_at
    // 내림차순이 아니다. 그래서 "특정 표본이 보이는가"로 묻지 않는다.
    // 화면에 뜬 날짜를 전부 걷어 저장 데이터의 KST 날짜 집합과 대조한다 —
    // 보정되지 않은 카드가 하나라도 남아 있으면 집합 밖 날짜로 드러난다.
    const screenDates = [...bodyText.matchAll(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\./g)].map(
      m => `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}`
    );

    if (!screenDates.length) {
      console.error('❌ X 필터 화면에서 날짜를 하나도 읽지 못했습니다 (카드가 렌더링되지 않음).');
      return 1;
    }

    const kstDates = new Set(xPosts.map(p => String(p.created_at).slice(0, 10)));
    const unexpected = [...new Set(screenDates)].filter(d => !kstDates.has(d));

    console.log(`뷰어 X 화면에서 읽은 날짜: ${screenDates.length}개 (고유 ${new Set(screenDates).size}개)`);

    if (unexpected.length) {
      console.error(`❌ 저장 데이터에 없는 날짜가 화면에 있습니다: ${unexpected.join(', ')}`);
      console.error('   보정 전 값이 남아 있거나 서버 캐시가 갱신되지 않았을 수 있습니다.');
      return 1;
    }

    console.log(
      `✅ 뷰어 X 카드 날짜가 전부 ${path.basename(totalPath)} 의 KST 값 집합에 속함 ` +
        `(화면 ${screenDates.length}개 대조)`
    );
    return 0;
  } finally {
    await browser.close();
  }
}

process.exit(await main());
