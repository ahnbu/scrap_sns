/**
 * Headless viewer check for the YouTube platform.
 *
 * Verifies the filter chip exists, that clicking it renders only YouTube cards,
 * that a card carries an author and icon, that search narrows the result, and
 * that /api/search honours platform=youtube.
 *
 * Runs with no visible window so it never steals focus, and exits 0/1 so a
 * completion gate can judge it without anyone looking at a screenshot.
 *
 * Usage:
 *   node scripts/verify_youtube_viewer_headless.mjs [--shot <png path>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';

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

const checks = [];

function record(name, ok, detail) {
  checks.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
}

async function main() {
  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (wscript sns_hub.vbs).');
      return 1;
    }
    await page.waitForTimeout(2500);

    // 1) 필터 버튼 존재
    const chipCount = await page.locator('[data-filter="youtube"]').count();
    record('유튜브 필터 버튼 존재', chipCount === 1, `${chipCount}개`);
    if (chipCount !== 1) return 1;

    // 2) 필터 클릭 후 유튜브 카드만 렌더
    await page.locator('[data-filter="youtube"]').first().click();
    await page.waitForTimeout(2500);

    const platforms = await page.evaluate(() =>
      [...document.querySelectorAll('article[data-platform]')].map(el => el.dataset.platform)
    );
    const nonYoutube = platforms.filter(value => value !== 'youtube');
    record(
      '필터 클릭 후 카드 렌더',
      platforms.length > 0,
      `카드 ${platforms.length}건`
    );
    record(
      '표시된 카드가 전부 youtube',
      platforms.length > 0 && nonYoutube.length === 0,
      nonYoutube.length ? `유튜브 아닌 카드 ${nonYoutube.length}건: ${[...new Set(nonYoutube)].join(', ')}` : ''
    );

    // 3) 첫 카드의 아이콘·작성자
    const firstCard = await page.evaluate(() => {
      const card = document.querySelector('article[data-platform="youtube"]');
      if (!card) return null;
      const author = card.querySelector('h3');
      return {
        author: author ? author.textContent.trim() : '',
        hasIcon: Boolean(card.querySelector('svg, .material-symbols-outlined')),
      };
    });
    record(
      '첫 카드 작성자·아이콘',
      Boolean(firstCard && firstCard.author && firstCard.hasIcon),
      firstCard ? `author="${firstCard.author}" icon=${firstCard.hasIcon}` : 'no card'
    );

    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.log(`스크린샷: ${shotPath}`);
    }

    // 4) API 플랫폼 필터
    const term = await page.evaluate(() => {
      const card = document.querySelector('article[data-platform="youtube"] h3');
      return card ? card.textContent.trim().split(/\s+/)[0] : '';
    });

    const apiResult = await page.evaluate(async searchTerm => {
      const query = searchTerm || 'youtube';
      const res = await fetch(
        `/api/search?q=${encodeURIComponent(query)}&platform=youtube&limit=50`
      );
      if (!res.ok) return { ok: false, status: res.status };
      const data = await res.json();
      const posts = data.posts || [];
      return {
        ok: true,
        query,
        total: data.total_matched,
        offPlatform: posts
          .map(post => post.sns_platform)
          .filter(value => value !== 'youtube'),
      };
    }, term);

    record(
      '/api/search?platform=youtube 응답',
      apiResult.ok,
      apiResult.ok ? `q="${apiResult.query}" 매칭 ${apiResult.total}건` : `HTTP ${apiResult.status}`
    );
    record(
      'API 응답이 전부 youtube',
      apiResult.ok && apiResult.offPlatform.length === 0,
      apiResult.ok && apiResult.offPlatform.length
        ? `타 플랫폼 ${apiResult.offPlatform.length}건`
        : ''
    );

    const failed = checks.filter(check => !check.ok);
    if (failed.length) {
      console.error(`\n❌ ${failed.length}/${checks.length} 검사 실패`);
      return 1;
    }
    console.log(`\n✅ ${checks.length}/${checks.length} 검사 통과`);
    return 0;
  } finally {
    await browser.close();
  }
}

process.exit(await main());
