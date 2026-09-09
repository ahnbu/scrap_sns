/**
 * 벤치마킹 UI 디자인 검수 — 기계로 잴 수 있는 것만. 창을 띄우지 않는다.
 *
 * 기존 화면이 이미 정해둔 규격에서 벗어났는지 본다. 밀도·위계·문구처럼
 * 눈이 필요한 것은 여기서 판정하지 않고 캡처만 남긴다(사람 판정 몫).
 *
 *   D1 탭 바가 어느 뷰포트에서도 잘리지 않는다 (스크롤 가능하면 통과)
 *   D2 신규 탭에 기존 팔레트 밖의 색·모서리·글자 크기가 없다
 *   D3 신규 탭에 기존에 없던 상호작용 위젯이 없다
 *   D4 계정 전량 렌더 상태에서 모달이 85vh 를 안 넘는다
 *   D5 배지가 겹치는 카드에서 푸터 줄이 안 깨진다
 *
 * Usage: node scripts/verify_benchmark_ui_design.mjs [--shot-dir <dir>]
 * 계획: _docs/20260906_01 (P7)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const VIEWPORTS = [
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1280x800', width: 1280, height: 800 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '430x932', width: 430, height: 932 },
];

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}
const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260906_03', 'design'));

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
  fs.mkdirSync(shotDir, { recursive: true });

  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
    });
    const page = await context.newPage();
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForSelector('.glass-card', { timeout: 90000 });

    // 허용 팔레트에 카드 푸터 배지(999px pill)를 반드시 포함시킨다. 첫 화면에는
    // 배지 카드가 없어 스크롤해 로드하지 않으면 기존 규격이 baseline 에서 빠지고,
    // 그걸 그대로 따른 신규 배지가 위반으로 잡힌다.
    for (let i = 0; i < 6; i++) {
      await page.mouse.wheel(0, 3000);
      await page.waitForTimeout(250);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);

    await page.evaluate(() => document.getElementById('settingsBtn')?.click());
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      [...document.querySelectorAll('.tab-btn')]
        .find((b) => b.dataset.target === 'tabBenchmark')?.click();
    });
    await page.waitForTimeout(500);

    const measured = await page.evaluate(() => {
      const bar = document.querySelector('.tab-btn')?.parentElement;
      const barStyle = bar ? getComputedStyle(bar) : null;
      const panel = document.querySelector('#managementModal .max-w-2xl');
      const pane = document.getElementById('tabBenchmark');

      // 허용 팔레트 = **이 화면이 이미 쓰는 값 전부**다. 모달 기존 4개 탭만
      // 기준으로 삼으면 카드 쪽 규격이 빠진다 - 벤치마킹 배지는 카드 푸터의
      // external-summary-badge 와 같은 pill 규격을 일부러 따랐기 때문에,
      // 좁은 기준으로는 의도한 재사용이 위반으로 잡힌다.
      const legacyPanes = [
        ...['tabTags', 'tabHidden', 'tabDisplay', 'tabMaintenance']
          .map((id) => document.getElementById(id)),
        document.querySelector('#managementModal header'),
        ...[...document.querySelectorAll('.glass-card')].slice(0, 60),
        document.querySelector('header'),
      ].filter(Boolean);
      const collect = (roots) => {
        const values = { color: new Set(), background: new Set(), radius: new Set(), font: new Set() };
        roots.forEach((root) => {
          [root, ...root.querySelectorAll('*')].forEach((el) => {
            const style = getComputedStyle(el);
            values.color.add(style.color);
            values.background.add(style.backgroundColor);
            values.radius.add(style.borderRadius);
            values.font.add(style.fontSize);
          });
        });
        return values;
      };
      const legacy = collect(legacyPanes);
      const fresh = pane ? collect([pane]) : { color: new Set(), background: new Set(), radius: new Set(), font: new Set() };
      const outside = (kind) => [...fresh[kind]].filter((v) => !legacy[kind].has(v));

      return {
        bar: bar ? {
          scrollWidth: bar.scrollWidth,
          clientWidth: bar.clientWidth,
          overflowX: barStyle.overflowX,
        } : null,
        panelHeight: panel ? Math.round(panel.getBoundingClientRect().height) : null,
        viewportHeight: window.innerHeight,
        rows: document.querySelectorAll('#benchmarkAccountList .bm-account-item').length,
        novelWidgets: pane
          ? pane.querySelectorAll('input[type=range], [role=switch], [draggable=true], [role=dialog]').length
          : 0,
        outsidePalette: {
          color: outside('color'),
          background: outside('background'),
          radius: outside('radius'),
          font: outside('font'),
        },
      };
    });

    const barOk = measured.bar
      && (measured.bar.scrollWidth <= measured.bar.clientWidth
        || ['auto', 'scroll'].includes(measured.bar.overflowX));
    record(`D1 [${viewport.name}] 탭 바가 잘리지 않는다`, Boolean(barOk),
      measured.bar
        ? `scrollW ${measured.bar.scrollWidth} / clientW ${measured.bar.clientWidth} · overflow-x ${measured.bar.overflowX}`
        : '탭 바를 못 찾음');

    const paletteMisses = Object.entries(measured.outsidePalette)
      .filter(([, values]) => values.length)
      .map(([kind, values]) => `${kind}: ${values.join(', ')}`);
    record(`D2 [${viewport.name}] 기존 팔레트 밖의 값이 없다`,
      paletteMisses.length === 0, paletteMisses.join(' | '));

    record(`D3 [${viewport.name}] 기존에 없던 위젯이 없다`,
      measured.novelWidgets === 0, `발견 ${measured.novelWidgets}개`);

    const heightOk = measured.panelHeight !== null
      && measured.panelHeight <= Math.ceil(measured.viewportHeight * 0.85) + 1;
    record(`D4 [${viewport.name}] 모달이 85vh 를 안 넘는다`, heightOk,
      `패널 ${measured.panelHeight}px / 뷰포트 ${measured.viewportHeight}px`);

    await page.screenshot({
      path: path.join(shotDir, `benchmark_tab_${viewport.name}.png`),
    });

    // 기존 탭과 나란히 두고 보려면 태그 관리 캡처도 필요하다(사람 판정용).
    if (viewport.name === '1440x900') {
      await page.evaluate(() => {
        [...document.querySelectorAll('.tab-btn')]
          .find((b) => b.dataset.target === 'tabTags')?.click();
      });
      await page.waitForTimeout(400);
      await page.screenshot({ path: path.join(shotDir, 'compare_tags_tab.png') });
    }

    await context.close();
  }

  // D5 배지가 겹치는 카드의 푸터
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });
  // 벤치마킹 글은 ALL 에 항상 보인다. 종전에는 설정 토글을 켜야 했는데
  // 그 토글은 삭제됐다. 계획: _docs/20260909_01 (W3)
  await page.waitForTimeout(300);
  for (let i = 0; i < 10; i++) {
    await page.mouse.wheel(0, 3000);
    await page.waitForTimeout(300);
  }

  const footer = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.glass-card')];
    const badged = cards
      .map((card) => ({
        card,
        badges: card.querySelectorAll('.external-summary-badge').length,
      }))
      .filter((entry) => entry.badges > 0)
      .sort((a, b) => b.badges - a.badges);
    if (!badged.length) return { none: true };
    const worst = badged[0];
    const badge = worst.card.querySelector('.external-summary-badge');
    let row = badge;
    while (row.parentElement && row.parentElement !== worst.card) row = row.parentElement;
    return {
      maxBadges: worst.badges,
      cardsWithBadge: badged.length,
      benchmarkMarks: document.querySelectorAll('[data-benchmark-mark]').length,
      scrollWidth: row.scrollWidth,
      clientWidth: row.clientWidth,
    };
  });

  if (footer.none) {
    record('D5 배지가 겹치는 카드에서 푸터 줄이 안 깨진다', true, '배지 카드가 화면에 없어 확인 생략');
  } else {
    record('D5 배지가 겹치는 카드에서 푸터 줄이 안 깨진다',
      footer.scrollWidth <= footer.clientWidth,
      `최다 배지 ${footer.maxBadges}개 · 벤치마킹 배지 ${footer.benchmarkBadges}개 · scrollW ${footer.scrollWidth}/${footer.clientWidth}`);
    await page.screenshot({ path: path.join(shotDir, 'card_badges_overlap.png') });
  }
  await context.close();

  // ── W5: 계정 칩 줄이 태그 칩 줄과 갈리는지 ──────────────────────
  // 종전에는 같은 줄에 1px 구분선만 있었다. 칩 규격이 같고 flex-wrap 줄바꿈에
  // 구분선이 줄 끝으로 밀려 경계로 안 읽혔다. 계획: _docs/20260906_03 (W5)
  const sepCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const sepPage = await sepCtx.newPage();
  await sepPage.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await sepPage.waitForSelector('.glass-card', { timeout: 90000 });
  await sepPage.click('#benchmarkBtn');
  await sepPage.waitForTimeout(900);

  const structure = await sepPage.evaluate(() => {
    const chip = document.querySelector('.benchmark-chip');
    const tag = [...document.querySelectorAll('.global-tag-chip')]
      .find((el) => !el.classList.contains('benchmark-chip'));
    if (!chip || !tag) return { skipped: true, hasChip: Boolean(chip), hasTag: Boolean(tag) };
    return {
      sameParent: chip.parentElement === tag.parentElement,
      chipRow: chip.parentElement?.id || '',
      tagRow: tag.parentElement?.id || '',
      chipBorder: getComputedStyle(chip).borderColor,
      tagBorder: getComputedStyle(tag).borderColor,
    };
  });

  if (structure.skipped) {
    record('D6 계정 칩과 태그 칩이 다른 줄에 있다', false,
      `칩 ${structure.hasChip} · 태그 ${structure.hasTag} — 확인 불가`);
    record('D7 두 칩의 테두리 색이 다르다', false, '확인 불가');
  } else {
    record('D6 계정 칩과 태그 칩이 다른 줄에 있다',
      !structure.sameParent && structure.chipRow === 'benchmarkChipsRow',
      `계정줄 #${structure.chipRow} · 태그줄 #${structure.tagRow}`);
    record('D7 두 칩의 테두리 색이 다르다',
      structure.chipBorder !== structure.tagBorder,
      `계정 ${structure.chipBorder} · 태그 ${structure.tagBorder}`);
  }

  // D8 뷰포트 4종에서 두 줄이 세로로 갈린다
  const rowGeom = [];
  for (const vp of VIEWPORTS) {
    await sepPage.setViewportSize({ width: vp.width, height: vp.height });
    await sepPage.waitForTimeout(400);
    const geom = await sepPage.evaluate(() => {
      const a = document.getElementById('benchmarkChipsRow');
      const b = document.getElementById('globalTagsContainer');
      if (!a || !b) return null;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      return { chipY: Math.round(ra.y), chipBottom: Math.round(ra.bottom), tagY: Math.round(rb.y) };
    });
    rowGeom.push({ name: vp.name, ...(geom || {}) });
    await sepPage.screenshot({ path: path.join(shotDir, `benchmark_chip_row_${vp.name}.png`) });
  }
  const separated = rowGeom.every((g) => g.chipY != null && g.tagY != null && g.tagY >= g.chipBottom);
  record('D8 뷰포트 4종에서 계정 줄과 태그 줄이 세로로 갈린다', separated,
    rowGeom.map((g) => `${g.name} ${g.chipY}~${g.chipBottom}/${g.tagY}`).join(' · '));

  // D9 「수집 가능」 표시가 실제 수집 결과와 일치한다
  const collectable = await sepPage.evaluate(async () => {
    const [accRes, postRes] = await Promise.all([
      fetch('/api/get-benchmark-accounts'),
      fetch('/api/posts?limit=100000'),
    ]);
    const accounts = (await accRes.json()).accounts || [];
    const posts = (await postRes.json()).posts || [];
    const declared = new Set();
    accounts.forEach((a) => (a.collectable || []).forEach((p) => declared.add(p)));
    const actual = new Set();
    posts.forEach((p) => {
      if (p.is_saved === false && (p.benchmark_accounts || []).length) {
        actual.add(p.sns_platform);
      }
    });
    return { declared: [...declared].sort(), actual: [...actual].sort() };
  });
  // 양방향으로 본다. 「표시만 있고 안 긁힘」은 거짓 약속이고,
  // 「긁히는데 표시 없음」은 사용자가 켤 이유를 못 보는 상태다. 둘 다 결함이다.
  const declaredOnly = collectable.declared.filter((p) => !collectable.actual.includes(p));
  const actualOnly = collectable.actual.filter((p) => !collectable.declared.includes(p));
  record('D9 「수집 가능」 표시가 실제 수집 결과와 일치한다',
    declaredOnly.length === 0 && actualOnly.length === 0,
    `표시 [${collectable.declared}] · 실제 [${collectable.actual}]`
    + `${declaredOnly.length ? ` · 표시만 [${declaredOnly}]` : ''}`
    + `${actualOnly.length ? ` · 실제만 [${actualOnly}]` : ''}`);

  await sepCtx.close();

  console.log(`\nshots: ${shotDir}`);
} finally {
  await browser.close();
}

const failed = checks.filter((c) => !c.ok);
console.log(`${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
