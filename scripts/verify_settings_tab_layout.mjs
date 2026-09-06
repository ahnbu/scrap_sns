/**
 * 설정 모달 탭 배치 검증 — 데스크톱 세로 레일 / 모바일 가로 폴더 탭. 창을 띄우지 않는다.
 *
 * 375 / 393 / 640 / 1440 네 뷰포트에서 재고, 전부 통과하면 exit 0, 하나라도
 * 실패하면 실패 항목명을 찍고 exit 1. 완료 판정 근거는 이 종료코드와 아래 로그이며,
 * 같이 남기는 캡처는 나중에 사람이 되짚기 위한 보조 증거다.
 *
 *   S1  비활성 탭 대비가 4.5:1 이상 (실효 배경 기준)
 *   S2  탭 글자가 줄바꿈되지 않는다 (탭 높이 <= 48px)
 *   S3  클릭 영역이 40px 이상이다
 *   S4  <640px 는 가로, >=640px 는 세로로 배치된다
 *   S5  활성 탭과 활성 패널의 실효 배경색이 같다
 *   S6  본문 가용폭이 남는다 (>=640px 400px / <640px 290px)
 *   S7  탭 바가 잘리지 않는다
 *   S8  role="tab" 5개, aria-selected="true" 는 정확히 1개
 *   S9  콘솔 에러가 없다
 *   S10 375px 에서 태그 관리 툴바가 한 줄에 들어간다
 *   S11 1440px 에서 태그 목록 행이 깨지지 않는다
 *
 * Usage: node scripts/verify_settings_tab_layout.mjs [--shot-dir <dir>]
 * 계획: _docs/20260906_02 (T5)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = process.env.SNS_HUB_BASE_URL || 'http://127.0.0.1:5000/';
const VIEWPORTS = [
  { name: '375x812', width: 375, height: 812 },
  { name: '393x852', width: 393, height: 852 },
  { name: '640x900', width: 640, height: 900 },
  { name: '1440x900', width: 1440, height: 900 },
];

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}
const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260906_02'));

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}
function skip(name, detail) {
  checks.push({ name, ok: true, skipped: true, detail });
  console.log(`SKIP ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

// 페이지 안에서 쓸 헬퍼들. 브라우저 컨텍스트로 문자열로 넘어간다.
const PAGE_HELPERS = `
  const parseRgb = (value) => {
    const m = String(value).match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((v) => parseFloat(v.trim()));
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  // 투명한 요소는 실제로 조상의 배경 위에 그려진다. 첫 불투명 조상을 찾는다.
  const effectiveBg = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
      const rgb = parseRgb(getComputedStyle(node).backgroundColor);
      if (rgb && rgb.a > 0) return rgb;
      node = node.parentElement;
    }
    return { r: 0, g: 0, b: 0, a: 1 };
  };
  const lum = ({ r, g, b }) => {
    const f = (c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const contrast = (fg, bg) => {
    const a = lum(fg);
    const b = lum(bg);
    const [hi, lo] = a > b ? [a, b] : [b, a];
    return (hi + 0.05) / (lo + 0.05);
  };
`;

const openSettings = async (page) => {
  await page.evaluate(() => document.getElementById('settingsBtn')?.click());
  await page.waitForTimeout(500);
};
const clickTab = async (page, target) => {
  await page.evaluate((t) => {
    [...document.querySelectorAll('.tab-btn')].find((b) => b.dataset.target === t)?.click();
  }, target);
  await page.waitForTimeout(400);
};

const browser = await launchHeadlessChromium();
try {
  fs.mkdirSync(shotDir, { recursive: true });

  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
    });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text());
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForSelector('.glass-card', { timeout: 90000 });
    await openSettings(page);

    const measured = await page.evaluate(`(() => {
      ${PAGE_HELPERS}
      const btns = [...document.querySelectorAll('.tab-btn')];
      const activeBtn = btns.find((b) => b.classList.contains('active'));
      const activePane = [...document.querySelectorAll('.tab-pane')]
        .find((p) => !p.classList.contains('hidden'));
      const bar = document.querySelector('.tab-btn')?.parentElement;
      const panes = document.querySelector('.settings-panes');

      const inactive = btns.filter((b) => !b.classList.contains('active'));
      const contrasts = inactive.map((b) => {
        const style = getComputedStyle(b);
        const fg = parseRgb(style.color);
        const opacity = parseFloat(style.opacity);
        const bg = effectiveBg(b);
        // opacity 가 걸려 있으면 배경과 섞인 실효 색으로 잰다.
        const mixed = opacity < 1 && fg
          ? { r: fg.r * opacity + bg.r * (1 - opacity),
              g: fg.g * opacity + bg.g * (1 - opacity),
              b: fg.b * opacity + bg.b * (1 - opacity) }
          : fg;
        return { label: b.dataset.target, value: mixed ? contrast(mixed, bg) : null };
      });

      const rects = btns.map((b) => b.getBoundingClientRect());
      const bgOf = (el) => {
        const c = effectiveBg(el);
        return el ? \`rgb(\${Math.round(c.r)}, \${Math.round(c.g)}, \${Math.round(c.b)})\` : null;
      };

      return {
        count: btns.length,
        contrasts,
        heights: btns.map((b, i) => ({ label: b.dataset.target, h: Math.round(rects[i].height) })),
        firstTwoTops: rects.length >= 2 ? [Math.round(rects[0].top), Math.round(rects[1].top)] : null,
        activeBtnBg: activeBtn ? bgOf(activeBtn) : null,
        activePaneBg: activePane ? bgOf(activePane) : null,
        activePaneId: activePane ? activePane.id : null,
        panesWidth: panes ? Math.round(panes.clientWidth) : null,
        bar: bar ? {
          scrollWidth: bar.scrollWidth,
          clientWidth: bar.clientWidth,
          overflowX: getComputedStyle(bar).overflowX,
        } : null,
        roleTabs: btns.filter((b) => b.getAttribute('role') === 'tab').length,
        selectedTrue: btns.filter((b) => b.getAttribute('aria-selected') === 'true').length,
      };
    })()`);

    const v = viewport.name;

    const worstContrast = measured.contrasts
      .filter((c) => c.value !== null)
      .reduce((min, c) => (min === null || c.value < min.value ? c : min), null);
    record(`S1 [${v}] 비활성 탭 대비 >= 4.5:1`,
      Boolean(worstContrast) && worstContrast.value >= 4.5,
      worstContrast ? `최저 ${worstContrast.value.toFixed(2)}:1 (${worstContrast.label})` : '비활성 탭 없음');

    const tallest = measured.heights.reduce((max, h) => (h.h > max.h ? h : max), measured.heights[0]);
    record(`S2 [${v}] 탭 글자가 줄바꿈되지 않는다`, tallest.h <= 48,
      `최대 ${tallest.h}px (${tallest.label})`);

    const shortest = measured.heights.reduce((min, h) => (h.h < min.h ? h : min), measured.heights[0]);
    record(`S3 [${v}] 클릭 영역 >= 40px`, shortest.h >= 40,
      `최소 ${shortest.h}px (${shortest.label})`);

    const wantRow = viewport.width < 640;
    const sameTop = measured.firstTwoTops
      && measured.firstTwoTops[0] === measured.firstTwoTops[1];
    record(`S4 [${v}] ${wantRow ? '가로 폴더 탭' : '세로 레일'}로 배치된다`,
      wantRow ? sameTop === true : sameTop === false,
      `첫 두 탭 top = ${measured.firstTwoTops?.join(' / ')}`);

    record(`S5 [${v}] 활성 탭과 본문의 배경이 같다`,
      Boolean(measured.activeBtnBg) && measured.activeBtnBg === measured.activePaneBg,
      `탭 ${measured.activeBtnBg} · 패널(${measured.activePaneId}) ${measured.activePaneBg}`);

    const minPanes = viewport.width >= 640 ? 400 : 290;
    record(`S6 [${v}] 본문 가용폭 >= ${minPanes}px`,
      measured.panesWidth !== null && measured.panesWidth >= minPanes,
      `${measured.panesWidth}px`);

    const barOk = measured.bar
      && (measured.bar.scrollWidth <= measured.bar.clientWidth
        || ['auto', 'scroll'].includes(measured.bar.overflowX));
    record(`S7 [${v}] 탭 바가 잘리지 않는다`, Boolean(barOk),
      measured.bar
        ? `scrollW ${measured.bar.scrollWidth} / clientW ${measured.bar.clientWidth} · overflow-x ${measured.bar.overflowX}`
        : '탭 바를 못 찾음');

    record(`S8 [${v}] 접근성 마크업`,
      measured.count === 5 && measured.roleTabs === 5 && measured.selectedTrue === 1,
      `탭 ${measured.count}개 · role=tab ${measured.roleTabs}개 · aria-selected=true ${measured.selectedTrue}개`);

    // S10 375px 에서 태그 관리 툴바가 한 줄
    if (viewport.width === 375) {
      await clickTab(page, 'tabTags');
      // top 이 같은지로 재지 않는다. 툴바는 items-center 라 높이가 다른 요소끼리
      // top 이 어긋나는 것이 정상이다(실측: 검색창 38px / 버튼 50px → 6px 차이).
      // 「한 줄」은 세로 구간이 서로 겹치고, 툴바 높이가 가장 큰 요소 높이를
      // 넘지 않는 것으로 판정한다. 계획: _docs/20260906_02 (T5 S10)
      const toolbar = await page.evaluate(() => {
        const ids = ['tagSearchInput', 'addTagBtn', 'runBatchAutoTagBtn'];
        const els = ids.map((id) => document.getElementById(id));
        if (els.some((el) => !el)) return null;
        const rects = els.map((el) => el.getBoundingClientRect());
        const row = els[0].closest('.flex.items-center');
        const rowRect = row ? row.getBoundingClientRect() : null;
        return {
          maxTop: Math.round(Math.max(...rects.map((r) => r.top))),
          minBottom: Math.round(Math.min(...rects.map((r) => r.bottom))),
          tallest: Math.round(Math.max(...rects.map((r) => r.height))),
          rowHeight: rowRect ? Math.round(rowRect.height) : null,
          widths: rects.map((r) => Math.round(r.width)),
        };
      });
      if (!toolbar) {
        record(`S10 [${v}] 태그 관리 툴바가 한 줄에 들어간다`, false, '툴바 요소를 못 찾음');
      } else {
        const overlap = toolbar.maxTop < toolbar.minBottom;
        const notWrapped = toolbar.rowHeight !== null && toolbar.rowHeight <= toolbar.tallest + 1;
        record(`S10 [${v}] 태그 관리 툴바가 한 줄에 들어간다`, overlap && notWrapped,
          `툴바 높이 ${toolbar.rowHeight}px / 최대 요소 ${toolbar.tallest}px · 폭 ${toolbar.widths.join(' / ')}px`);
      }
    }

    // S11 1440px 에서 태그 목록 행이 안 깨짐
    if (viewport.width === 1440) {
      await clickTab(page, 'tabTags');
      await page.waitForTimeout(400);
      const list = await page.evaluate(() => {
        const el = document.getElementById('tagManagementList');
        if (!el) return null;
        const rows = [...el.children].filter((c) => c.getBoundingClientRect().height > 0);
        return {
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          rowCount: rows.length,
          minH: rows.length ? Math.min(...rows.map((r) => Math.round(r.getBoundingClientRect().height))) : null,
          maxH: rows.length ? Math.max(...rows.map((r) => Math.round(r.getBoundingClientRect().height))) : null,
        };
      });
      if (!list) {
        record(`S11 [${v}] 태그 목록 행이 깨지지 않는다`, false, '#tagManagementList 를 못 찾음');
      } else if (list.rowCount === 0) {
        skip(`S11 [${v}] 태그 목록 행이 깨지지 않는다`, '태그 행이 0개라 검사 대상 없음');
      } else {
        const noOverflow = list.scrollWidth <= list.clientWidth + 1;
        const evenRows = list.maxH < list.minH * 1.5;
        record(`S11 [${v}] 태그 목록 행이 깨지지 않는다`, noOverflow && evenRows,
          `행 ${list.rowCount}개 · scrollW ${list.scrollWidth}/clientW ${list.clientWidth} · 높이 ${list.minH}~${list.maxH}px`);
      }
    }

    // 사용자가 하는 순서 그대로 - 탭 5개를 차례로 눌러보고 마지막에 태그 검색창에 입력.
    for (const target of ['tabTags', 'tabHidden', 'tabDisplay', 'tabBenchmark', 'tabMaintenance']) {
      await clickTab(page, target);
    }
    await clickTab(page, 'tabTags');
    await page.fill('#tagSearchInput', 'a').catch(() => {});
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(shotDir, `settings_tabs_${v}.png`) });

    record(`S9 [${v}] 콘솔 에러가 없다`, consoleErrors.length === 0,
      consoleErrors.slice(0, 3).join(' | '));

    await context.close();
  }
} finally {
  await browser.close();
}

const failed = checks.filter((c) => !c.ok);
const skipped = checks.filter((c) => c.skipped);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과${skipped.length ? ` (SKIP ${skipped.length})` : ''}`);
if (failed.length) {
  console.log('실패 항목:');
  failed.forEach((c) => console.log(`  - ${c.name}${c.detail ? ` — ${c.detail}` : ''}`));
}
process.exit(failed.length ? 1 : 0);
