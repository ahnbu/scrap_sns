/**
 * Headless viewer check: the count shown at the top of the viewer must match the
 * post count in the newest output_total file.
 *
 * Runs with no visible window so it never steals focus, and exits 0/1 so a
 * completion gate can judge it without anyone looking at a screenshot.
 *
 * Usage:
 *   node scripts/verify_viewer_total_count_headless.mjs [--shot <png path>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const TOTAL_DIR = 'output_total';

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

function readPostCount(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  const data = JSON.parse(text);
  const posts = Array.isArray(data) ? data : data.posts || [];
  return posts.length;
}

async function main() {
  const totalPath = latestTotalFile();
  if (!totalPath) {
    console.error('❌ output_total 파일을 찾을 수 없습니다.');
    return 1;
  }

  const expected = readPostCount(totalPath);
  console.log(`기준 파일: ${totalPath} (${expected}건)`);

  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (wscript sns_hub.vbs).');
      return 1;
    }

    // The viewer renders one card per post; the header also prints a total.
    await page.waitForTimeout(2500);

    const bodyText = await page.evaluate(() => document.body.innerText || '');
    const numbers = [...bodyText.matchAll(/([\d,]{2,})\s*건/g)].map(m =>
      Number(m[1].replace(/,/g, ''))
    );

    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.log(`스크린샷: ${shotPath}`);
    }

    if (!numbers.length) {
      console.error('❌ 뷰어 화면에서 "N건" 형태의 총건수를 찾지 못했습니다.');
      return 1;
    }

    console.log(`뷰어에서 읽은 건수 후보: ${numbers.join(', ')}`);

    if (numbers.includes(expected)) {
      console.log(`✅ 뷰어 총건수와 ${path.basename(totalPath)} 게시글 수 일치 (${expected}건)`);
      return 0;
    }

    console.error(`❌ 불일치: 파일 ${expected}건, 뷰어 후보 ${numbers.join(', ')}`);
    return 1;
  } finally {
    await browser.close();
  }
}

process.exit(await main());
