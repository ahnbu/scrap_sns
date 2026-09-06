/**
 * 뷰어 화면 증거 캡처. 창을 띄우지 않는다.
 *
 * 총건수 배지와 카드 렌더 여부를 함께 찍어, "화면이 비지 않았다"를 눈이 아니라
 * 종료코드로도 판정할 수 있게 한다.
 *
 * Usage:
 *   node scripts/capture_viewer_evidence.mjs --out <png> [--expect-total 2685] [--w 1440] [--h 900]
 *
 * exit 0 = 카드가 1개 이상 렌더됐고(--expect-total 을 줬으면) 총건수가 일치
 * exit 1 = 그 밖
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}

const outPath = arg('--out');
const expectTotal = arg('--expect-total');
const width = Number(arg('--w', 1440));
const height = Number(arg('--h', 900));

if (!outPath) {
  console.error('--out <png> 가 필요하다');
  process.exit(2);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const browser = await launchHeadlessChromium();
let ok = true;
try {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  const state = await page.evaluate(() => {
    const text = document.body.innerText;
    const match = text.match(/([\d,]+)\s*건/);
    return {
      cards: document.querySelectorAll('.glass-card').length,
      totalLabel: match ? match[1].replace(/,/g, '') : null,
    };
  });

  console.log(`cards=${state.cards} totalLabel=${state.totalLabel}`);

  if (!state.cards) {
    console.error('FAIL: 카드가 0개다 — 화면이 비었다');
    ok = false;
  }
  if (expectTotal && state.totalLabel !== String(expectTotal)) {
    console.error(`FAIL: 총건수 기대 ${expectTotal} != 화면 ${state.totalLabel}`);
    ok = false;
  }

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  await page.screenshot({ path: outPath, fullPage: false });
  console.log(`shot: ${outPath}`);
} finally {
  await browser.close();
}
process.exit(ok ? 0 : 1);
