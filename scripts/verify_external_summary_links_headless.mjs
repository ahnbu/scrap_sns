/**
 * Headless viewer check: 새로 매핑된 유튜브 영상에 외부 요약 링크가 실제로 붙는지 본다.
 *
 * `verify_external_summary_icons.mjs` 는 화면에 걸린 카드의 구조(href 도메인·라벨·폭)를 본다.
 * 이 스크립트는 그 앞 단계를 본다 - 매핑 파일에 있는 영상이 뷰어 API 를 타고 카드까지
 * 도달해 앵커로 렌더되는가. 자동 갱신(`refresh_external_summaries_after_success()`)이
 * 매핑만 만들고 뷰어에는 안 붙는 상태를 잡기 위한 것이다.
 *
 * 판정
 *   - 매핑에 있고 뷰어 API 에도 있는 유튜브 영상(교집합)을 고른다.
 *   - 그중 표본 N개를 화면에 올려 `a[data-external-summary]` 가 매핑과 일치하는지 본다.
 *   - 하나라도 어긋나면 exit 1.
 *
 * 사용법
 *   node scripts/verify_external_summary_links_headless.mjs [--shot <png path>] [--sample 5]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const MAPPING_PATH = path.join('web_viewer', 'sns_external_summaries.json');

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : null;
}

const shotPath = argValue('--shot');
const sampleSize = Number(argValue('--sample') || '5');

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude',
  'skills',
  '_shared',
  'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

function loadMapping() {
  if (!fs.existsSync(MAPPING_PATH)) return { generatedAt: '', items: {} };
  const text = fs.readFileSync(MAPPING_PATH, 'utf8').replace(/^\uFEFF/, '');
  const data = JSON.parse(text);
  return { generatedAt: data.generated_at_kst || '', items: data.items || {} };
}

async function main() {
  const { generatedAt, items } = loadMapping();
  const mappedIds = Object.keys(items);
  if (!mappedIds.length) {
    console.error('❌ 매핑이 비어 있다. node scripts/build_external_summaries.mjs 를 먼저 돌려라.');
    return 1;
  }
  console.log(`매핑: ${MAPPING_PATH} (${mappedIds.length}건, 생성 ${generatedAt || '시각 없음'})`);

  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (python scrap_sns_server.py).');
      return 1;
    }
    await page.waitForSelector('article[data-platform]', { timeout: 30000 });

    // 매핑과 뷰어 데이터의 교집합을 구한다. 매핑에만 있고 뷰어에 없는 영상은
    // 아직 수집되지 않은 것이라 화면 검증 대상이 아니다.
    const targets = await page.evaluate(async ({ ids, limit }) => {
      const res = await fetch('/api/posts?limit=5000');
      if (!res.ok) return null;
      const body = await res.json();
      const posts = body.posts || body.items || [];
      const mapped = new Set(ids);
      const hits = posts
        .filter(
          p =>
            String(p.sns_platform || '').toLowerCase() === 'youtube' &&
            mapped.has(p.platform_id || p.code)
        )
        .map(p => p.platform_id || p.code);
      return { total: posts.length, hits: hits.slice(0, limit), hitCount: hits.length };
    }, { ids: mappedIds, limit: sampleSize });

    if (!targets) {
      console.error('❌ /api/posts 응답을 읽지 못했습니다.');
      return 1;
    }
    console.log(`뷰어 게시글 ${targets.total}건 중 매핑 교집합 유튜브 ${targets.hitCount}건`);

    if (!targets.hitCount) {
      console.error('❌ 매핑과 뷰어 데이터의 교집합이 0건입니다.');
      console.error('   요약 라이브러리 인증이 만료됐거나 매핑이 갱신되지 않았을 수 있습니다.');
      return 1;
    }

    // 유튜브 필터를 켜고, 대상 카드가 나올 때까지 스크롤해 더 불러온다.
    const chip = await page.$('[data-filter="youtube"]');
    if (chip) {
      await chip.click();
      await page.waitForTimeout(2000);
    }

    const found = [];
    const missing = [];
    for (const videoId of targets.hits) {
      let card = null;
      for (let i = 0; i < 40; i += 1) {
        card = await page.$(`article[data-platform-id="${videoId}"]`);
        if (card) break;
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(500);
      }
      if (!card) {
        missing.push({ videoId, reason: '카드를 화면에 올리지 못함' });
        continue;
      }

      const anchors = await card.$$eval('a[data-external-summary]', nodes =>
        nodes.map(a => ({
          service: a.getAttribute('data-external-summary'),
          href: a.getAttribute('href') || '',
        }))
      );

      const expected = Object.entries(items[videoId] || {})
        .filter(([, url]) => Boolean(url))
        .map(([service, url]) => ({ service, href: url }));

      const actualKey = anchors
        .map(a => `${a.service}|${a.href}`)
        .sort()
        .join(',');
      const expectedKey = expected
        .map(a => `${a.service}|${a.href}`)
        .sort()
        .join(',');

      if (actualKey === expectedKey && expected.length > 0) {
        found.push({ videoId, services: expected.map(e => e.service).join('+') });
      } else {
        missing.push({
          videoId,
          reason: `기대 [${expectedKey || '없음'}] / 실제 [${actualKey || '없음'}]`,
        });
      }
    }

    for (const item of found) {
      console.log(`  ✅ ${item.videoId} — ${item.services}`);
    }
    for (const item of missing) {
      console.error(`  ❌ ${item.videoId} — ${item.reason}`);
    }

    if (missing.length) {
      if (shotPath) {
        fs.mkdirSync(path.dirname(shotPath), { recursive: true });
        await page.screenshot({ path: shotPath, fullPage: false });
        console.error(`스크린샷: ${shotPath}`);
      }
      console.error(`\n❌ 표본 ${targets.hits.length}건 중 ${missing.length}건 불일치`);
      return 1;
    }

    console.log(`\n✅ 표본 ${found.length}건 모두 매핑과 화면 앵커가 일치`);
    return 0;
  } finally {
    await browser.close();
  }
}

process.exit(await main());
