/**
 * Headless viewer check for the YouTube platform.
 *
 * 검사 항목
 *   - 유튜브 필터 칩 존재 / 클릭 시 유튜브 카드만 렌더 / 작성자·아이콘
 *   - S1  카드에 제목 + 구분선 + 요약 2줄이 보인다 (클램프 6줄 이내)
 *   - S5  카드 본문에 마크다운 기호가 없다
 *   - S2  요약에만 등장하는 고유명사가 검색으로 잡힌다 (질의어는 런타임 도출)
 *   - S7  화면 총건수 == /api/posts total == 최신 total_full 의 total_count
 *   - S11 타 플랫폼 카드는 4줄 그대로 (유튜브 6줄 변경이 새어나가지 않았는지)
 *
 * 창을 띄우지 않아 사용자 포커스를 뺏지 않고, 0/1 종료코드로 판정된다.
 *
 * Usage:
 *   node scripts/verify_youtube_viewer_headless.mjs [--shot <png path>] [--ids <v1,v2,...>]
 *
 * --ids 를 주면 그 video_id 집합만 S1·S2·S5 로 검사한다. 웨이브 실행 직후에는
 * 나머지 게시글이 아직 옛 형식이라 전수 검사가 반드시 실패하기 때문이다.
 * --ids 를 생략하면 전수 모드다 (마지막 웨이브 종료 후 1회).
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
const idsArg = argValue('--ids');
const targetIds = idsArg
  ? idsArg.split(',').map((value) => value.trim()).filter(Boolean)
  : null;

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

function latestTotal() {
  const dir = 'output_total';
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir)
    .filter((name) => /^total_full_\d{8}\.json$/.test(name))
    .sort();
  if (!files.length) return null;
  const raw = fs.readFileSync(path.join(dir, files[files.length - 1]), 'utf8').replace(/^\uFEFF/, '');
  return JSON.parse(raw);
}

/** \uC790\uB9C9\uC774 \uC5C6\uC5B4 \uC694\uC57D\uC744 \uB9CC\uB4E4 \uC218 \uC5C6\uB294 \uC601\uC0C1. S1 \uB300\uC0C1\uC5D0\uC11C \uBE80\uB2E4.
 *  summary_status \uB294 API \uBA54\uD0C0 \uD544\uB4DC\uAC00 \uC544\uB2C8\uB77C \uD1B5\uD569\uBCF8 \uD30C\uC77C\uC5D0\uB9CC \uC788\uC5B4 \uC5EC\uAE30\uC11C \uC77D\uB294\uB2E4. */
function idsWithoutSummary(total) {
  return (total?.posts || [])
    .filter((p) => String(p.sns_platform || '').toLowerCase() === 'youtube')
    .filter((p) => p.summary_status && p.summary_status !== 'ok')
    .map((p) => String(p.platform_id));
}

async function main() {
  const browser = await launchHeadlessChromium();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  try {
    const response = await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    if (!response || !response.ok()) {
      console.error(`❌ 뷰어 응답 실패: ${response ? response.status() : 'no response'}`);
      console.error('   5000번 서버가 떠 있는지 확인하세요 (scripts/restart_viewer_server.ps1).');
      return 1;
    }
    await page.waitForTimeout(2500);

    // ---------------------------------------------------------- S7 / S11 (전수)
    const totalFile = latestTotal();
    const fileTotal = totalFile?.metadata?.total_count ?? null;
    const noSummaryIds = idsWithoutSummary(totalFile);
    if (noSummaryIds.length) {
      console.log(`ℹ️ 자막 없어 요약 불가 ${noSummaryIds.length}건은 S1 대상에서 제외한다`);
    }
    const totals = await page.evaluate(async () => {
      const res = await fetch('/api/posts');
      const data = await res.json();
      const posts = data.posts || data;
      // 라벨은 "2092 건" 또는 (숨김 필터가 걸리면) "2089 / 2092 건" 이다.
      // 마지막 숫자가 전체 건수다 - 전부 이어 붙이면 20892092 같은 값이 나온다.
      const label = document.getElementById('totalPostsCount');
      const numbers = label ? String(label.textContent).match(/\d+/g) : null;
      const shown = numbers && numbers.length ? Number(numbers[numbers.length - 1]) : null;
      return { api: posts.length, shown, raw: label ? label.textContent.trim() : null };
    });
    record(
      'S7 저장·통합·화면 총건수 일치',
      fileTotal !== null && totals.api === fileTotal && totals.shown === fileTotal,
      `파일 ${fileTotal} / API ${totals.api} / 화면 ${totals.shown} ("${totals.raw}")`
    );

    // 클램프 클래스가 붙은 카드만 센다. 150자 이하 짧은 글은 애초에 클램프가
    // 붙지 않고 전문이 렌더되므로(script.js isLongText) 줄 수 제한 대상이 아니다.
    const otherClamp = await page.evaluate(() =>
      [...document.querySelectorAll('article[data-platform]')]
        .filter((card) => card.dataset.platform !== 'youtube')
        .map((card) => {
          const p = card.querySelector('p[id^="text-"]');
          if (!p || !p.classList.contains('line-clamp-4')) return null;
          const lh = parseFloat(getComputedStyle(p).lineHeight);
          return {
            platform: card.dataset.platform,
            lines: Math.round(p.getBoundingClientRect().height / lh),
            clamp6: p.classList.contains('line-clamp-6'),
          };
        })
        .filter(Boolean)
    );
    const overClamped = otherClamp.filter((entry) => entry.lines > 4 || entry.clamp6);
    record(
      'S11 타 플랫폼 카드는 4줄 그대로',
      otherClamp.length > 0 && overClamped.length === 0,
      overClamped.length
        ? `4줄 초과 ${overClamped.length}건: ${[...new Set(overClamped.map((e) => e.platform))].join(', ')}`
        : `클램프 적용 ${otherClamp.length}건 전부 4줄 이하`
    );

    // ---------------------------------------------------------- 필터
    const chipCount = await page.locator('[data-filter="youtube"]').count();
    record('유튜브 필터 버튼 존재', chipCount === 1, `${chipCount}개`);
    if (chipCount !== 1) return 1;

    await page.locator('[data-filter="youtube"]').first().click();
    await page.waitForTimeout(2500);

    const platforms = await page.evaluate(() =>
      [...document.querySelectorAll('article[data-platform]')].map((el) => el.dataset.platform)
    );
    const nonYoutube = platforms.filter((value) => value !== 'youtube');
    record('필터 클릭 후 카드 렌더', platforms.length > 0, `카드 ${platforms.length}건`);
    record(
      '표시된 카드가 전부 youtube',
      platforms.length > 0 && nonYoutube.length === 0,
      nonYoutube.length ? `유튜브 아닌 카드 ${nonYoutube.length}건` : ''
    );

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
      firstCard ? `author="${firstCard.author}"` : 'no card'
    );

    // ---------------------------------------------------------- S1 / S5
    const cards = await page.evaluate(async ({ ids, skipIds }) => {
      const res = await fetch('/api/posts');
      const data = await res.json();
      const posts = (data.posts || data).filter(
        (p) => String(p.sns_platform || '').toLowerCase() === 'youtube'
      );
      const byUrl = new Map();
      posts.forEach((p) => {
        if (p.canonical_url) byUrl.set(p.canonical_url, p);
        if (p.url) byUrl.set(p.url, p);
      });

      return [...document.querySelectorAll('article[data-platform="youtube"]')]
        .map((card) => {
          const p = card.querySelector('p[id^="text-"]');
          if (!p) return null;
          const url = card.querySelector('[data-url]')?.dataset.url;
          const post = byUrl.get(url);
          if (!post) return null;
          if (ids && !ids.includes(String(post.platform_id))) return null;
          if (skipIds.includes(String(post.platform_id))) return null;

          const lh = parseFloat(getComputedStyle(p).lineHeight);
          const text = p.textContent || '';
          const sepIndex = text.indexOf('\u2500');
          const afterSep = sepIndex === -1 ? '' : text.slice(sepIndex).replace(/^\u2500+/, '').trim();
          return {
            id: post.platform_id,
            lines: Math.round(p.getBoundingClientRect().height / lh),
            hasSeparator: sepIndex !== -1,
            summaryStartsAfterSeparator: afterSep.startsWith('[요약]'),
            summaryChars: afterSep.length,
            markdown: ['##', '**', '__'].filter((sym) => text.includes(sym)),
          };
        })
        .filter(Boolean);
    }, { ids: targetIds, skipIds: noSummaryIds });

    const scope = targetIds ? `대상 ${targetIds.length}건 중 ${cards.length}건 렌더` : `전수 ${cards.length}건`;
    if (targetIds && cards.length === 0) {
      record('S1 요약 노출', false, '지정한 video_id 가 화면에 하나도 없다');
      return 1;
    }

    // 요약 두 줄 = 약 58자. 클램프 안에 그만큼 남아 있어야 한다.
    const s1Bad = cards.filter(
      (c) => c.lines > 6 || !c.hasSeparator || !c.summaryStartsAfterSeparator || c.summaryChars < 40
    );
    record(
      'S1 카드에 제목+구분선+요약 노출',
      cards.length > 0 && s1Bad.length === 0,
      s1Bad.length ? `실패 ${s1Bad.length}건 (예: ${s1Bad[0].id} lines=${s1Bad[0].lines} sep=${s1Bad[0].hasSeparator} chars=${s1Bad[0].summaryChars})` : scope
    );

    const s5Bad = cards.filter((c) => c.markdown.length > 0);
    record(
      'S5 마크다운 기호 미노출',
      s5Bad.length === 0,
      s5Bad.length ? `${s5Bad[0].id} 에 ${s5Bad[0].markdown.join(', ')}` : scope
    );

    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      await page.screenshot({ path: shotPath, fullPage: false });
      console.log(`스크린샷: ${shotPath}`);
    }

    // ---------------------------------------------------------- S2
    // 질의어를 하드코딩하지 않는다 - 요약 본문에서 제목·설명에 없는 고유명사를
    // 런타임에 뽑아야 웨이브마다 검사가 돈다.
    const searchResult = await page.evaluate(async ({ ids, skipIds }) => {
      const listRes = await fetch('/api/posts');
      const listData = await listRes.json();
      const metas = (listData.posts || listData).filter(
        (p) => String(p.sns_platform || '').toLowerCase() === 'youtube'
      );
      const targets = (ids ? metas.filter((p) => ids.includes(String(p.platform_id))) : metas)
        .filter((p) => !skipIds.includes(String(p.platform_id)));

      for (const meta of targets.slice(0, 30)) {
        const detailRes = await fetch(`/api/post/${meta.sequence_id}`);
        if (!detailRes.ok) continue;
        const post = await detailRes.json();
        const text = String(post.full_text || '');
        const sumStart = text.indexOf('[요약]');
        const sumEnd = text.indexOf('[설명]');
        if (sumStart === -1) continue;
        const summary = text.slice(sumStart, sumEnd === -1 ? undefined : sumEnd);
        const head = text.slice(0, sumStart) + (sumEnd === -1 ? '' : text.slice(sumEnd));

        const tokens = [...new Set(summary.match(/\b[A-Z][A-Za-z]{3,}\b/g) || [])]
          .filter((token) => !head.includes(token));
        if (!tokens.length) continue;

        const term = tokens[0];
        const searchRes = await fetch(
          `/api/search?q=${encodeURIComponent(term)}&platform=youtube&limit=200`
        );
        if (!searchRes.ok) return { ok: false, term, status: searchRes.status };
        const found = await searchRes.json();
        const hit = (found.posts || []).some(
          (p) => String(p.platform_id) === String(meta.platform_id)
        );
        return { ok: hit, term, videoId: meta.platform_id, total: found.total_matched };
      }
      return { ok: false, reason: 'no-candidate' };
    }, { ids: targetIds, skipIds: noSummaryIds });

    record(
      'S2 요약 고유명사가 검색으로 잡힌다',
      searchResult.ok === true,
      searchResult.ok
        ? `q="${searchResult.term}" → ${searchResult.videoId} (매칭 ${searchResult.total}건)`
        : searchResult.reason === 'no-candidate'
          ? '요약에서 검색용 고유명사를 찾지 못했다 (요약이 아직 생성되지 않았을 수 있다)'
          : `q="${searchResult.term}" 가 대상 영상을 반환하지 않았다`
    );

    const failed = checks.filter((check) => !check.ok);
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
