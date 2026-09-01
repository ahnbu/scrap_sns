/**
 * 외부 요약 아이콘 렌더 headless 검증.
 *
 * 검사 항목
 *   V1 푸터 어디에도 문자열 `View Original` 이 없다
 *   V2 매핑에 있는 유튜브 카드에 외부 요약 앵커가 렌더되고 href 가 올바른 도메인이다
 *   V3 매핑에 없는 유튜브 카드에는 외부 요약 앵커가 0개다
 *   V4 유튜브 외 플랫폼 카드에는 외부 요약 앵커가 0개다
 *   V5 원본 보기 앵커가 카드마다 1개씩 있고 title 또는 aria-label 을 갖는다
 *   V6 렌더된 외부 앵커 수가 매핑 x 화면표시 교집합과 일치한다
 *
 * 창을 띄우지 않는다 - 창이 뜨면 사용자 포커스를 빼앗아 병행 작업이 끊긴다.
 * 대상 video_id 를 하드코딩하지 않고 web_viewer/sns_external_summaries.json 에서 런타임에 읽는다.
 * 실패 시에만 --shot 경로에 스크린샷을 남긴다.
 *
 * Usage:
 *   node scripts/verify_external_summary_icons.mjs [--shot <png path>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : null;
}

const shotPath = argValue('--shot');

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

function loadMapping() {
  const filePath = path.join('web_viewer', 'sns_external_summaries.json');
  if (!fs.existsSync(filePath)) return {};
  const raw = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  return JSON.parse(raw).items || {};
}

async function main() {
  const mapping = loadMapping();
  const mappedIds = Object.keys(mapping);
  if (!mappedIds.length) {
    console.error('❌ 매핑이 비어 있다. node scripts/build_external_summaries.mjs 를 먼저 돌려라.');
    return 1;
  }

  const browser = await launchHeadlessChromium();
  try {
    const page = await browser.newPage();
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('article[data-platform]', { timeout: 30000 });
    await page.waitForTimeout(1500);

    // 첫 화면은 최신순이라 매핑된 영상이 안 걸릴 수 있다.
    // 매핑 대상 카드를 실제로 화면에 올려야 V2 가 의미를 갖는다.
    const targetId = await page.evaluate(async (ids) => {
      const res = await fetch('/api/posts?limit=3000');
      if (!res.ok) return null;
      const body = await res.json();
      const posts = body.posts || body.items || [];
      const mapped = new Set(ids);
      const hit = posts.find(
        (p) => String(p.sns_platform || '').toLowerCase() === 'youtube'
          && mapped.has(p.platform_id || p.code)
      );
      return hit ? (hit.platform_id || hit.code) : null;
    }, mappedIds);

    if (targetId) {
      const chip = await page.$('[data-filter="youtube"]');
      if (chip) {
        await chip.click();
        await page.waitForTimeout(2000);
      }
      // 유튜브 필터만으로 대상이 안 보이면 끝까지 스크롤해 더 불러온다.
      for (let i = 0; i < 30; i += 1) {
        if (await page.$(`article[data-platform-id="${targetId}"]`)) break;
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(600);
      }
    }
    console.log(`대상 영상: ${targetId || '(매핑 교집합 없음)'}`);

    const snapshot = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('article[data-platform]')];
      return {
        bodyHasViewOriginal: /View Original/.test(document.body.innerText || ''),
        htmlHasViewOriginal: /View Original/.test(document.body.innerHTML || ''),
        cards: cards.map((card) => {
          const external = [...card.querySelectorAll('a[data-external-summary]')];
          const original = [...card.querySelectorAll('.footer-links a:not([data-external-summary])')];
          return {
            platform: card.dataset.platform || '',
            postKey: card.dataset.postKey || '',
            externals: external.map((a) => ({
              service: a.getAttribute('data-external-summary'),
              href: a.getAttribute('href') || '',
              text: (a.textContent || '').trim(),
              className: a.className || '',
              title: a.getAttribute('title') || '',
              ariaLabel: a.getAttribute('aria-label') || '',
              rel: a.getAttribute('rel') || '',
            })),
            footerOverflow: (() => {
              const footer = card.querySelector('.footer-links');
              if (!footer) return null;
              return footer.scrollWidth > footer.clientWidth + 1;
            })(),
            originalCount: original.length,
            originalLabelled: original.every(
              (a) => Boolean(a.getAttribute('title') || a.getAttribute('aria-label'))
            ),
          };
        }),
      };
    });

    // 화면에 보이는 유튜브 카드의 video_id 를 API 로 확인한다.
    const visibleYoutube = await page.evaluate(() =>
      [...document.querySelectorAll('article[data-platform="youtube"]')]
        .map((card) => card.dataset.videoId || card.dataset.platformId || '')
        .filter(Boolean)
    );

    record(
      'V1 푸터에 View Original 문자열이 없다',
      !snapshot.bodyHasViewOriginal && !snapshot.htmlHasViewOriginal,
      snapshot.bodyHasViewOriginal || snapshot.htmlHasViewOriginal ? '아직 남아 있다' : ''
    );

    const externalCards = snapshot.cards.filter((c) => c.externals.length > 0);
    const badHref = externalCards.flatMap((c) => c.externals).filter((e) =>
      !(e.href.startsWith('https://lilys.ai/digest/')
        || e.href.startsWith('https://livewiki.com/ko/content/'))
    );
    record(
      'V2 외부 요약 앵커의 href 가 올바른 도메인이다',
      externalCards.length > 0 && badHref.length === 0,
      externalCards.length === 0
        ? '외부 앵커가 하나도 렌더되지 않았다 (매핑된 영상이 화면에 없을 수 있다)'
        : `앵커 ${externalCards.flatMap((c) => c.externals).length}개, 잘못된 href ${badHref.length}개`
    );

    const youtubeCards = snapshot.cards.filter((c) => c.platform === 'youtube');
    const nonYoutubeWithExternal = snapshot.cards.filter(
      (c) => c.platform !== 'youtube' && c.externals.length > 0
    );
    record(
      'V4 유튜브 외 플랫폼 카드에는 외부 앵커가 없다',
      nonYoutubeWithExternal.length === 0,
      `위반 ${nonYoutubeWithExternal.length}건`
    );

    record(
      'V5 원본 보기 앵커가 카드마다 1개이고 라벨을 갖는다',
      snapshot.cards.length > 0
        && snapshot.cards.every((c) => c.originalCount === 1 && c.originalLabelled),
      `카드 ${snapshot.cards.length}개 중 위반 `
        + `${snapshot.cards.filter((c) => c.originalCount !== 1 || !c.originalLabelled).length}건`
    );

    const mappedSet = new Set(mappedIds);
    const expectedCards = visibleYoutube.filter((id) => mappedSet.has(id));
    const unmappedVisible = visibleYoutube.filter((id) => !mappedSet.has(id));
    record(
      'V6 외부 앵커가 붙은 카드 수가 매핑 교집합과 일치한다',
      visibleYoutube.length === 0 || externalCards.length === expectedCards.length,
      `화면 유튜브 ${visibleYoutube.length} / 매핑 교집합 ${expectedCards.length}`
        + ` / 앵커 카드 ${externalCards.length}`
    );
    record(
      'V3 매핑에 없는 유튜브 카드에는 외부 앵커가 없다',
      youtubeCards.length - externalCards.length === unmappedVisible.length
        || unmappedVisible.length === 0,
      `매핑 없는 화면 유튜브 ${unmappedVisible.length}건`
    );

    // V7~V9: 아이콘을 이름 배지로 바꾼 뒤 추가된 검사.
    // 계획: _docs/20260901_01_링크드인-이미지-복구와-외부요약-자동화-아이콘-개선-계획.md
    const allExternals = externalCards.flatMap((c) => c.externals);
    const EXPECTED_BADGE = { lilys: 'Lilys', livewiki: 'LiveWiki' };
    const badBadgeText = allExternals.filter(
      (e) => e.text !== EXPECTED_BADGE[e.service]
    );
    record(
      'V7 외부 요약 앵커가 서비스 이름을 그대로 노출한다',
      allExternals.length > 0 && badBadgeText.length === 0,
      allExternals.length === 0
        ? '외부 앵커가 하나도 렌더되지 않았다'
        : `앵커 ${allExternals.length}개 중 이름 불일치 ${badBadgeText.length}개`
        + (badBadgeText.length
          ? ` (예: ${badBadgeText[0].service} -> "${badBadgeText[0].text}")`
          : '')
    );

    const badAccessibility = allExternals.filter(
      (e) => !e.title || !e.ariaLabel || !/noopener/.test(e.rel)
        || !e.className.includes('external-summary-badge')
    );
    record(
      'V8 배지가 라벨·rel·전용 클래스를 유지한다',
      allExternals.length > 0 && badAccessibility.length === 0,
      `앵커 ${allExternals.length}개 중 위반 ${badAccessibility.length}개`
    );

    const overflowCards = snapshot.cards.filter((c) => c.footerOverflow === true);
    record(
      'V9 배지를 넣어도 카드 푸터가 가로로 넘치지 않는다',
      overflowCards.length === 0,
      `푸터 가로 넘침 ${overflowCards.length}건`
    );

    const failed = checks.filter((check) => !check.ok);
    if (failed.length) {
      if (shotPath) {
        await page.screenshot({ path: shotPath, fullPage: true });
        console.error(`스크린샷: ${shotPath}`);
      }
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
