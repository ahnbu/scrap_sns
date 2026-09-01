/**
 * Headless viewer check: LinkedIn 카드의 이미지가 실제로 로드되는지 본다.
 *
 * licdn 서명 URL 은 쿼리 `e=` 의 만료 epoch 가 지나면 어떤 헤더로도 403 이라,
 * 로컬 파일이 없으면 카드에 깨진 자리표시자만 남는다. 이 스크립트는 뷰어를
 * 창 없이 띄워 img 요소의 naturalWidth 를 세고 0/1 로 끝난다 - 사람이 화면을
 * 보지 않아도 완료검수가 판정할 수 있게 하기 위해서다.
 *
 * 판정
 *   - 저장 데이터 기준: media 를 가진 LinkedIn 글의 local_images 확보율
 *   - 화면 기준: 렌더된 LinkedIn 카드 img 중 naturalWidth > 0 비율
 *   둘 다 임계값(기본 90%) 이상이어야 통과한다.
 *
 * 사용법
 *   node scripts/verify_linkedin_images_headless.mjs [--shot <png path>] [--min-rate 0.9]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const TOTAL_DIR = 'output_total';

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : null;
}

const shotPath = argValue('--shot');
const minRate = Number(argValue('--min-rate') || '0.9');

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

function readLinkedinImageStats(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  const data = JSON.parse(text);
  const posts = Array.isArray(data) ? data : data.posts || [];

  let withMedia = 0;
  let withLocal = 0;
  for (const post of posts) {
    if (String(post.sns_platform || '').toLowerCase() !== 'linkedin') continue;
    const media = Array.isArray(post.media) ? post.media : [];
    if (!media.length) continue;
    withMedia += 1;
    if (Array.isArray(post.local_images) && post.local_images.length) withLocal += 1;
  }
  return { withMedia, withLocal };
}

async function main() {
  const totalPath = latestTotalFile();
  if (!totalPath) {
    console.error('❌ output_total 파일을 찾을 수 없습니다.');
    return 1;
  }

  const stats = readLinkedinImageStats(totalPath);
  if (!stats.withMedia) {
    console.error(`❌ ${totalPath} 에 media 를 가진 LinkedIn 글이 없습니다.`);
    return 1;
  }
  const dataRate = stats.withLocal / stats.withMedia;
  console.log(
    `저장 데이터: ${path.basename(totalPath)} LinkedIn media 보유 ${stats.withMedia}건 중 ` +
      `local_images 확보 ${stats.withLocal}건 (${(dataRate * 100).toFixed(1)}%)`
  );

  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (wscript sns_hub.vbs).');
      return 1;
    }

    await page.waitForTimeout(3000);

    // LinkedIn 플랫폼 필터를 켠다. 칩은 아이콘만 있고 텍스트가 없어서
    // data-filter 속성으로 찾는다(index.html:96-99).
    const filterClicked = await page.evaluate(() => {
      const target = document.querySelector('[data-filter="linkedin"]');
      if (!target) return false;
      target.click();
      return true;
    });
    if (!filterClicked) {
      console.error('❌ LinkedIn 필터 칩([data-filter="linkedin"])을 찾지 못했습니다.');
      return 1;
    }
    await page.waitForTimeout(3000);

    // 카드 이미지는 loading="lazy" 라서 뷰포트 밖이면 naturalWidth 가 0 이다.
    // 그대로 세면 "안 보이는 것"과 "깨진 것"을 구분하지 못한다. 검사 대상만
    // eager 로 바꿔 실제 로드 결과를 기다린 뒤 판정한다.
    const imageStats = await page.evaluate(async () => {
      const SAMPLE_LIMIT = 40;
      const images = [...document.querySelectorAll('img')]
        .filter(img => {
          const src = img.currentSrc || img.src || '';
          if (!src) return false;
          // 아바타/아이콘이 아니라 카드 본문 이미지만 센다.
          return /web_viewer\/images\/|licdn\.com|wsrv\.nl/.test(src);
        })
        .slice(0, SAMPLE_LIMIT);

      const settle = img =>
        new Promise(resolve => {
          if (img.complete) {
            resolve(img.naturalWidth > 0);
            return;
          }
          const done = ok => {
            img.removeEventListener('load', onLoad);
            img.removeEventListener('error', onError);
            resolve(ok);
          };
          const onLoad = () => done(true);
          const onError = () => done(false);
          img.addEventListener('load', onLoad);
          img.addEventListener('error', onError);
          setTimeout(() => done(img.naturalWidth > 0), 15000);
        });

      for (const img of images) {
        img.loading = 'eager';
        // src 를 다시 대입해 lazy 로 보류된 요청을 즉시 시작시킨다.
        if (!img.complete) img.src = img.src;
      }

      const results = await Promise.all(images.map(settle));
      const broken = images
        .filter((_, index) => !results[index])
        .slice(0, 5)
        .map(img => (img.currentSrc || img.src || '').slice(0, 120));

      return {
        total: images.length,
        loaded: results.filter(Boolean).length,
        broken,
      };
    });

    if (!imageStats.total) {
      console.error('❌ 화면에서 카드 이미지를 하나도 찾지 못했습니다.');
      if (shotPath) {
        fs.mkdirSync(path.dirname(shotPath), { recursive: true });
        await page.screenshot({ path: shotPath, fullPage: false });
        console.error(`스크린샷: ${shotPath}`);
      }
      return 1;
    }

    const screenRate = imageStats.loaded / imageStats.total;
    console.log(
      `화면: 카드 이미지 ${imageStats.total}개 중 ${imageStats.loaded}개 로드 ` +
        `(${(screenRate * 100).toFixed(1)}%)`
    );
    if (imageStats.broken.length) {
      console.log('깨진 이미지 예시:');
      for (const src of imageStats.broken) console.log(`  - ${src}`);
    }

    const ok = dataRate >= minRate && screenRate >= minRate;
    if (!ok && shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.error(`스크린샷: ${shotPath}`);
    }

    if (ok) {
      console.log(`✅ 저장 데이터·화면 모두 임계값 ${(minRate * 100).toFixed(0)}% 이상`);
      return 0;
    }

    console.error(
      `❌ 임계값 ${(minRate * 100).toFixed(0)}% 미달 — 데이터 ${(dataRate * 100).toFixed(1)}% / ` +
        `화면 ${(screenRate * 100).toFixed(1)}%`
    );
    return 1;
  } finally {
    await browser.close();
  }
}

process.exit(await main());
