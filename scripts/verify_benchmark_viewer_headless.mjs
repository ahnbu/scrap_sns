/**
 * 뷰어 구분 표시·필터 headless 검증. 창을 띄우지 않는다.
 *
 * P6 의 완료 판정이다. 시나리오 점검(verify_benchmark_scenarios.mjs)이
 * 「쓰는 순서 전체」를 보는 반면, 여기서는 표시 판정식 하나만 좁게 본다 —
 * 어느 쪽이 깨졌는지 갈라 읽기 위해서다.
 *
 *   V1 「저장」을 켜면 벤치마킹 전용 글이 안 보인다
 *   V2 ALL 에서는 벤치마킹 글이 보인다
 *   V3 계정을 끄면 그 계정 전용분만 사라진다 (저장글은 하나도 안 사라진다)
 *   V4 다시 켜면 카드 집합이 끄기 전과 같다
 *   V5 수동 숨김이 안 묻힌다 (Hidden 탭 항목 수 무변화)
 *   V6 CLI 가 같은 판정을 한다
 *
 * Usage: node scripts/verify_benchmark_viewer_headless.mjs
 * 계획: _docs/20260906_01 (P6)
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startBenchmarkVerifyServer } from './_bench_verify_server.mjs';

// 검증 전용 서버를 띄운다. 운영 5000번과 운영 계정 파일을 건드리지 않는다.
// 계획: _docs/20260906_03 (W2)
const verifyServer = await startBenchmarkVerifyServer();
const BASE_URL = verifyServer.baseUrl;
const ACCOUNTS_PATH = verifyServer.accountsPath;

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

const originalAccounts = fs.readFileSync(ACCOUNTS_PATH, 'utf8');
const browser = await launchHeadlessChromium();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // 표시 판정식을 브라우저 안에서 그대로 재현해 대조한다.
  const evaluate = () => page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    const activeIds = new Set(accounts.filter((a) => a.status === 'active').map((a) => a.id));
    return {
      total: posts.length,
      saved: posts.filter((p) => p.is_saved !== false).length,
      benchmarkOnly: posts.filter((p) => p.is_saved === false).length,
      visibleWhenOn: posts.filter(
        (p) => p.is_saved !== false
          || (p.benchmark_accounts || []).some((id) => activeIds.has(id))
      ).length,
    };
  });

  // 종전에는 설정 탭의 「목록에 벤치마킹 글 함께 보기」 토글을 켜고 껐다.
  // 그 토글은 삭제됐다 - ALL 은 항상 전부 보이고, 내 저장글만 보려면 상단
  // 「저장」 버튼을 켠다. 계획: _docs/20260909_01 (W3)
  const setSavedOnly = async (want) => {
    await page.evaluate((on) => {
      const btn = document.getElementById('savedPostsBtn');
      if (!btn) return;
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      if (pressed !== on) btn.click();
    }, want);
    await page.waitForTimeout(700);
  };

  // DOM 배지 수는 스크롤 깊이에 따라 달라진다(lazy render). 판정에는
  // 표시 판정식을 데이터에 그대로 적용한 결정적 값을 쓴다.
  const visibleBenchmarkCount = () => page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    const activeIds = new Set(accounts.filter((a) => a.status === 'active').map((a) => a.id));
    return posts.filter(
      (p) => p.is_saved === false
        && (p.benchmark_accounts || []).some((id) => activeIds.has(id))
    ).length;
  });

  // 화면에 실제로 배지가 붙는지는 별도로 본다(0인지 아닌지만).
  // selector 를 받는다. W1 이후 겹친 글(내 저장글이면서 벤치마킹 계정 소속)도
  // 배지를 달기 때문에, 「전용 글이 있나」와 「배지가 있나」가 갈렸다.
  // 계획: _docs/20260906_03 (W2)
  const badgeCount = (selector = '[data-benchmark-mark]') => page.evaluate(async (sel) => {
    for (let i = 0; i < 6; i++) {
      window.scrollBy(0, 3000);
      await new Promise((r) => setTimeout(r, 200));
    }
    const count = document.querySelectorAll(sel).length;
    window.scrollTo(0, 0);
    return count;
  }, selector);

  const hiddenTabCount = () => page.evaluate(async () => {
    document.getElementById('settingsBtn')?.click();
    await new Promise((r) => setTimeout(r, 300));
    [...document.querySelectorAll('.tab-btn')]
      .find((b) => b.dataset.target === 'tabHidden')?.click();
    await new Promise((r) => setTimeout(r, 300));
    const list = document.getElementById('invisiblePostsList');
    const count = list ? list.children.length : -1;
    document.getElementById('closeManagementModal')?.click();
    await new Promise((r) => setTimeout(r, 300));
    return count;
  });

  const stats = await evaluate();
  console.log(`데이터: 전체 ${stats.total} · 저장글 ${stats.saved} · 벤치마킹 전용 ${stats.benchmarkOnly}`);

  // V1 「저장」을 켜면 벤치마킹 전용 글이 사라진다 (겹친 글은 내 저장글이라 남는다)
  await setSavedOnly(true);
  const savedOnlyMarks = await badgeCount('[data-benchmark-also-saved="0"]');
  record('V1 「저장」을 켜면 벤치마킹 전용 글이 안 보인다', savedOnlyMarks === 0,
    `전용 마크 ${savedOnlyMarks}개`);

  const hiddenBefore = await hiddenTabCount();

  // V2 ALL 에서는 벤치마킹 글이 그대로 보인다 (숨은 상태가 없다)
  await setSavedOnly(false);
  const allMarks = await badgeCount();
  record('V2 ALL 에서는 벤치마킹 글이 보인다', allMarks > 0, `마크 ${allMarks}개`);

  // V3·V4 계정 하나를 껐다 켠다
  const victim = await page.evaluate(async () => {
    const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const scored = accounts
      .filter((a) => a.status === 'active')
      .map((a) => ({
        id: a.id,
        name: a.name,
        only: posts.filter((p) => p.is_saved === false && (p.benchmark_accounts || []).includes(a.id)).length,
        saved: posts.filter((p) => p.is_saved !== false && (p.benchmark_accounts || []).includes(a.id)).length,
      }))
      .filter((entry) => entry.only > 0)
      .sort((x, y) => (y.saved - x.saved) || (y.only - x.only));
    return scored[0] || null;
  });

  if (!victim) {
    record('V3 계정을 끄면 그 계정 전용분만 사라진다', false, '전용 글이 있는 켜진 계정이 없다');
    record('V4 다시 켜면 카드 집합이 복원된다', false, '확인 불가');
  } else {
    const before = await visibleBenchmarkCount();

    const toggleAccount = async () => {
      await page.evaluate(() => document.getElementById('settingsBtn')?.click());
      await page.waitForTimeout(300);
      await page.evaluate(() => {
        [...document.querySelectorAll('.tab-btn')]
          .find((b) => b.dataset.target === 'tabBenchmark')?.click();
      });
      await page.waitForTimeout(300);
      await page.evaluate((id) => {
        document.querySelector(`[data-bm-id="${id}"] [data-bm-action="toggle"]`)?.click();
      }, victim.id);
      await page.waitForTimeout(900);
      await page.evaluate(() => document.getElementById('closeManagementModal')?.click());
      await page.waitForTimeout(500);
    };

    await toggleAccount();
    const afterOff = await visibleBenchmarkCount();
    // 저장글은 하나도 안 사라져야 한다.
    const savedVisible = await page.evaluate(async (id) => {
      const posts = (await (await fetch('/api/posts')).json()).posts || [];
      return posts.filter((p) => p.is_saved !== false && (p.benchmark_accounts || []).includes(id)).length;
    }, victim.id);
    record('V3 계정을 끄면 그 계정 전용분만 사라진다',
      afterOff < before && savedVisible === victim.saved,
      `배지 ${before}→${afterOff} · 저장글 ${savedVisible}/${victim.saved}건 유지 (${victim.name})`);

    await toggleAccount();
    const afterOn = await visibleBenchmarkCount();
    const restoredStatus = await page.evaluate(async (id) => {
      const accounts = (await (await fetch('/api/get-benchmark-accounts')).json()).accounts || [];
      return accounts.find((a) => a.id === id)?.status;
    }, victim.id);
    record('V4 다시 켜면 카드 집합이 복원된다',
      afterOn === before && restoredStatus === 'active',
      `${before} → ${afterOff} → ${afterOn} · status=${restoredStatus}`);
  }

  const hiddenAfter = await hiddenTabCount();
  record('V5 수동 숨김이 묻히지 않는다', hiddenBefore === hiddenAfter,
    `Hidden 탭 ${hiddenBefore} → ${hiddenAfter}`);

  await context.close();
} finally {
  await browser.close();
  fs.writeFileSync(ACCOUNTS_PATH, originalAccounts, 'utf8');
  await verifyServer.stop();
}

// V6 CLI 가 같은 판정을 하는지
try {
  const excluded = execFileSync('node', ['utils/query-sns.mjs', 'recent', '200', '--format', 'json'], {
    encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
  });
  const included = execFileSync(
    'node',
    ['utils/query-sns.mjs', 'recent', '200', '--format', 'json', '--benchmark', 'only'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }
  );
  const parse = (text) => {
    const data = JSON.parse(text);
    return Array.isArray(data) ? data : (data.posts || data.results || []);
  };
  const defaultPosts = parse(excluded);
  const onlyPosts = parse(included);
  const leaked = defaultPosts.filter((p) => p.is_saved === false).length;
  record('V6 CLI 기본값이 벤치마킹 글을 제외한다',
    leaked === 0 && onlyPosts.length > 0,
    `기본 결과에 섞인 벤치마킹 ${leaked}건 · --benchmark only ${onlyPosts.length}건`);
} catch (error) {
  record('V6 CLI 기본값이 벤치마킹 글을 제외한다', false, String(error.message).slice(0, 120));
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
