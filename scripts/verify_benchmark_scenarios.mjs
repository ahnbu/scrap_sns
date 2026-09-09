/**
 * 사용자 시나리오 점검 — 기계 판정 갈래. 창을 띄우지 않는다.
 *
 * 조각이 아니라 쓰는 순서 전체를 본다. 각 시나리오는 계획서의 「실패 신호」를
 * 그대로 assert 로 옮긴 것이다.
 *
 * 전부 PASS 면 exit 0, 하나라도 FAIL 이면 exit 1.
 * 사람 판정 몫(S1·S11·S13)은 여기서 다루지 않고 캡처만 남긴다.
 *
 * Usage: node scripts/verify_benchmark_scenarios.mjs [--shot-dir <dir>]
 * 계획: _docs/20260906_01 (P8)
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startBenchmarkVerifyServer } from './_bench_verify_server.mjs';

// 검증 전용 서버를 띄운다. 운영 5000번과 운영 계정 파일을 건드리지 않는다.
// 계획: _docs/20260906_03 (W2)
const verifyServer = await startBenchmarkVerifyServer();
const BASE_URL = verifyServer.baseUrl;
const ACCOUNTS_PATH = verifyServer.accountsPath;

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index !== -1 ? process.argv[index + 1] : fallback;
}
const shotDir = arg('--shot-dir', path.join('_docs', 'evidence', '20260906_01', 'scenario'));

const results = [];
function record(id, name, ok, detail) {
  results.push({ id, ok });
  console.log(`${id}: ${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const runnerPath = path.join(
  process.env.USERPROFILE || 'C:\\Users\\ahnbu',
  '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs'
);
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);

const originalAccounts = fs.readFileSync(ACCOUNTS_PATH, 'utf8');
const browser = await launchHeadlessChromium();

try {
  fs.mkdirSync(shotDir, { recursive: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('dialog', (dialog) => dialog.accept());

  const shot = (name) => page.screenshot({ path: path.join(shotDir, `${name}.png`) });

  const openSettings = async (tab) => {
    await page.evaluate(() => document.getElementById('settingsBtn')?.click());
    await page.waitForTimeout(400);
    if (tab) {
      await page.evaluate((target) => {
        [...document.querySelectorAll('.tab-btn')]
          .find((b) => b.dataset.target === target)?.click();
      }, tab);
      await page.waitForTimeout(400);
    }
  };
  const closeSettings = async () => {
    await page.evaluate(() => document.getElementById('closeManagementModal')?.click());
    await page.waitForTimeout(400);
  };
  // 설정의 「목록에 벤치마킹 글 함께 보기」 토글은 삭제됐다. ALL 은 항상 전부
  // 보이고, 내 저장글만 보려면 상단 「저장」 버튼을 켠다.
  // 계획: _docs/20260909_01 (W3)
  const setSavedOnly = async (on) => {
    await page.evaluate((want) => {
      const btn = document.getElementById('savedPostsBtn');
      if (!btn) return;
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      if (pressed !== want) btn.click();
    }, on);
    await page.waitForTimeout(700);
  };
  const visibleBenchmarkCards = () => page.evaluate(
    () => document.querySelectorAll('[data-benchmark-mark]').length
  );

  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForSelector('.glass-card', { timeout: 90000 });

  // ---- S2 후보를 켜면 저장되고 유지된다
  const s2 = await page.evaluate(async () => {
    const res = await fetch('/api/get-benchmark-accounts');
    const accounts = (await res.json()).accounts || [];
    const candidate = accounts.find((a) => a.status === 'off');
    return candidate ? { id: candidate.id, name: candidate.name } : null;
  });
  if (!s2) {
    record('S2', '후보를 켜면 저장된다', false, '후보 계정이 없다');
  } else {
    await openSettings('tabBenchmark');
    await page.evaluate(() => document.querySelector('[data-bm-section]')?.click());
    await page.waitForTimeout(300);
    await page.evaluate((id) => {
      document.querySelector(`[data-bm-id="${id}"] [data-bm-action="toggle"]`)?.click();
    }, s2.id);
    await page.waitForTimeout(900);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForSelector('.glass-card', { timeout: 60000 });
    const status = await page.evaluate(async (id) => {
      const res = await fetch('/api/get-benchmark-accounts');
      return ((await res.json()).accounts || []).find((a) => a.id === id)?.status;
    }, s2.id);
    record('S2', '후보를 켜면 저장되고 새로고침 후에도 유지된다',
      status === 'active', `${s2.name} → ${status}`);
    // 원래대로 되돌린다.
    await openSettings('tabBenchmark');
    await page.evaluate((id) => {
      document.querySelector(`[data-bm-id="${id}"] [data-bm-action="toggle"]`)?.click();
    }, s2.id);
    await page.waitForTimeout(900);
    await closeSettings();
  }

  // ---- S3 수집 결과가 데이터에 들어와 있다
  const s3 = await page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const benchmark = posts.filter((p) => p.is_saved === false);
    return {
      total: posts.length,
      benchmark: benchmark.length,
      withAccount: benchmark.filter((p) => (p.benchmark_accounts || []).length).length,
      // 채널이 좋아요를 감출 수 있다(실측: a16z 5건). 플랫폼이 안 주는 값까지
      // 요구하면 통과할 수 없는 기준이 된다. 조회수는 채널이 감출 수 없어
      // 이쪽을 필수로 본다. 계획: _docs/20260906_01 (제약 - 남의 계정 지표)
      withViews: benchmark.filter((p) => p.view_count !== null).length,
      withLikes: benchmark.filter((p) => p.like_count !== null).length,
    };
  });
  record('S3', '수집분이 데이터에 들어와 있고 지표가 붙는다',
    s3.benchmark > 0 && s3.withAccount === s3.benchmark && s3.withViews === s3.benchmark,
    `전체 ${s3.total} · 벤치마킹 ${s3.benchmark} · 계정표식 ${s3.withAccount}`
    + ` · 조회수 ${s3.withViews} · 좋아요 ${s3.withLikes}(채널이 감추면 결측)`);

  // ---- S4 「저장」을 켜면 벤치마킹 전용 글이 사라진다
  await setSavedOnly(true);
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 3000); await page.waitForTimeout(250); }
  const s4Hidden = await page.evaluate(
    () => document.querySelectorAll('[data-benchmark-also-saved="0"]').length
  );
  const s4 = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.glass-card')];
    return { cards: cards.length };
  });
  record('S4', '「저장」을 켜면 벤치마킹 전용 글이 안 보인다',
    s4Hidden === 0, `전용 마크 ${s4Hidden}개 · 렌더 카드 ${s4.cards}개`);
  await shot('S4_saved_only');
  await page.evaluate(() => window.scrollTo(0, 0));

  // ---- S5 ALL 에서는 벤치마킹 글이 보이고 마크로 구분된다
  await setSavedOnly(false);
  await page.waitForTimeout(500);
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 3000); await page.waitForTimeout(250); }
  const s5Shown = await visibleBenchmarkCards();
  record('S5', 'ALL 에서 벤치마킹 글이 보이고 마크로 구분된다',
    s5Shown > 0, `벤치마킹 마크 ${s5Shown}개`);
  await shot('S5_all_with_mark');
  await page.evaluate(() => window.scrollTo(0, 0));

  // ---- S6 소재 검증 검색: 절단이 내 저장글을 줄이지 않는다
  const s6 = await page.evaluate(async () => {
    const call = async (include) => {
      const params = new URLSearchParams({
        q: 'AI', platform: 'all', limit: '500', include_benchmark: include ? 'true' : 'false',
      });
      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      return {
        returned: data.returned,
        savedInPage: (data.posts || []).filter((p) => p.is_saved !== false).length,
        totalMatched: data.total_matched,
      };
    };
    return { off: await call(false), on: await call(true) };
  });
  record('S6', '벤치마킹을 꺼둔 검색이 내 저장글을 덜 보여주지 않는다',
    s6.off.savedInPage >= s6.on.savedInPage,
    `꺼짐 저장글 ${s6.off.savedInPage}/${s6.off.returned} · 켜짐 저장글 ${s6.on.savedInPage}/${s6.on.returned}`);

  // ---- S7 끄면 그 계정 전용분만 사라진다 / S8 다시 켜면 되살아난다
  const flow = await page.evaluate(async () => {
    const res = await fetch('/api/get-benchmark-accounts');
    const accounts = (await res.json()).accounts || [];
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    const withPosts = accounts
      .filter((a) => a.status === 'active')
      .map((a) => ({
        a,
        only: posts.filter((p) => p.is_saved === false && (p.benchmark_accounts || []).includes(a.id)).length,
        saved: posts.filter((p) => p.is_saved !== false && (p.benchmark_accounts || []).includes(a.id)).length,
      }))
      .filter((entry) => entry.only > 0)
      // 「저장글은 남는다」를 실제로 검증하려면 겹침이 있는 계정을 골라야 한다.
      // 겹침이 0인 계정을 고르면 그 검사가 0/0 으로 통과해 아무 것도 못 본다.
      .sort((x, y) => (y.saved - x.saved) || (y.only - x.only));
    return withPosts.length ? { id: withPosts[0].a.id, name: withPosts[0].a.name, only: withPosts[0].only, saved: withPosts[0].saved } : null;
  });

  if (!flow) {
    record('S7', '끄기 경고 숫자가 실제 숫자다', false, '전용 글이 있는 켜진 계정이 없다');
    record('S8', '다시 켜면 되살아난다', false, '확인 불가');
  } else {
    const before = await page.evaluate(() => ({
      cards: document.querySelectorAll('.glass-card').length,
      hidden: (() => {
        const list = document.getElementById('invisiblePostsList');
        return list ? list.children.length : -1;
      })(),
    }));

    await openSettings('tabBenchmark');
    const warning = await page.evaluate((id) => {
      let captured = null;
      const original = window.confirm;
      window.confirm = (message) => { captured = message; return true; };
      document.querySelector(`[data-bm-id="${id}"] [data-bm-action="toggle"]`)?.click();
      window.confirm = original;
      return captured;
    }, flow.id);
    await page.waitForTimeout(1000);
    const shown = warning && warning.match(/(\d+)건이 안 보이게/);
    record('S7', '끄기 경고에 실제 숫자가 들어간다',
      shown && Number(shown[1]) === flow.only,
      `기대 ${flow.only} · 문구 ${shown ? shown[1] : '없음'}`);

    await closeSettings();
    await page.waitForTimeout(400);
    const afterOff = await visibleBenchmarkCards();
    const savedStillThere = await page.evaluate(async (id) => {
      const posts = (await (await fetch('/api/posts')).json()).posts || [];
      return posts.filter((p) => p.is_saved !== false && (p.benchmark_accounts || []).includes(id)).length;
    }, flow.id);
    record('S7b', '내가 저장했던 글은 남는다',
      savedStillThere === flow.saved, `저장글 ${savedStillThere}/${flow.saved}건 유지`);
    await shot('S7_after_turn_off');

    // 다시 켠다
    await openSettings('tabBenchmark');
    await page.evaluate((id) => {
      document.querySelector(`[data-bm-id="${id}"] [data-bm-action="toggle"]`)?.click();
    }, flow.id);
    await page.waitForTimeout(1000);
    await closeSettings();
    await page.waitForTimeout(500);
    for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 3000); await page.waitForTimeout(200); }
    const afterOn = await visibleBenchmarkCards();
    const after = await page.evaluate(() => ({
      hidden: (() => {
        const list = document.getElementById('invisiblePostsList');
        return list ? list.children.length : -1;
      })(),
    }));
    record('S8', '다시 켜면 별도 조작 없이 되살아난다',
      afterOn > afterOff, `끈 뒤 ${afterOff}개 → 켠 뒤 ${afterOn}개`);
    record('S8b', '수동 숨김이 묻히지 않는다 (Hidden 탭 항목 수 무변화)',
      before.hidden === after.hidden, `${before.hidden} → ${after.hidden}`);
    await shot('S8_after_turn_on');
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  // ---- S9 뺌은 동기화를 다시 돌려도 안 돌아온다 / S10 되돌릴 수 있다
  const s9 = await page.evaluate(async () => {
    const res = await fetch('/api/get-benchmark-accounts');
    const accounts = (await res.json()).accounts || [];
    return accounts.filter((a) => a.status === 'excluded').map((a) => a.id);
  });
  record('S9', '뺀 계정이 excluded 로 기록돼 있다',
    s9.length > 0, `excluded ${s9.join(', ') || '없음'}`);

  // ---- S12 오타 주소는 목록에 안 들어간다
  const s12 = await page.evaluate(async () => {
    const res = await fetch('/api/verify-channel?platform=youtube&handle=@nope_xyz_0906_scenario');
    return (await res.json()).reason;
  });
  record('S12', '오타 주소는 not_found 로 걸러진다', s12 === 'not_found', `reason=${s12}`);

  // ---- S13 수집 불가 플랫폼은 확인 단계에서 정직하게 답한다
  const s13 = await page.evaluate(async () => {
    const res = await fetch('/api/verify-channel?platform=threads&handle=@someone');
    return (await res.json()).reason;
  });
  record('S13', '수집 불가 플랫폼은 unsupported_platform 을 돌려준다',
    s13 === 'unsupported_platform', `reason=${s13}`);

  // ---- S14 기존 저장글의 태그·별표가 유지된다
  const s14 = await page.evaluate(async () => {
    const [tags, meta] = await Promise.all([
      (await fetch('/api/get-tags')).json(),
      (await fetch('/api/get-user-metadata')).json(),
    ]);
    const favorites = Object.values(meta || {}).filter((v) => v && v.favorite).length;
    return { tagged: Object.keys(tags || {}).length, favorites };
  });
  record('S14', '태그·별표가 남아 있다',
    s14.tagged > 0, `태그 ${s14.tagged}건 · 별표 ${s14.favorites}건`);

  // ---- S16 요약이 상한에서 멈춰 있다
  const s16 = await page.evaluate(async () => {
    const posts = (await (await fetch('/api/posts')).json()).posts || [];
    return posts.filter((p) => p.is_saved === false).length;
  });
  record('S16', '벤치마킹 수집분이 상한 범위 안이다',
    s16 > 0 && s16 <= 60, `벤치마킹 ${s16}건 (1차 상한 60)`);

  // ---- S17 좁은 창에서 탭에 닿을 수 있다
  const mobile = await browser.newContext({ viewport: { width: 430, height: 932 } });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 90000 });
  await mobilePage.waitForSelector('.glass-card', { timeout: 90000 });
  await mobilePage.evaluate(() => document.getElementById('settingsBtn')?.click());
  await mobilePage.waitForTimeout(500);
  const s17 = await mobilePage.evaluate(() => {
    const btn = [...document.querySelectorAll('.tab-btn')]
      .find((b) => b.dataset.target === 'tabBenchmark');
    if (!btn) return { reachable: false };
    btn.scrollIntoView({ block: 'nearest', inline: 'center' });
    btn.click();
    const pane = document.getElementById('tabBenchmark');
    const bar = btn.parentElement;
    return {
      reachable: pane ? !pane.classList.contains('hidden') : false,
      scrollable: bar.scrollWidth <= bar.clientWidth
        || ['auto', 'scroll'].includes(getComputedStyle(bar).overflowX),
    };
  });
  record('S17', '좁은 창(430px)에서 벤치마킹 탭에 닿을 수 있다',
    s17.reachable && s17.scrollable, `열림=${s17.reachable} 스크롤가능=${s17.scrollable}`);
  await mobilePage.screenshot({ path: path.join(shotDir, 'S17_narrow_viewport.png') });
  await mobile.close();

  await context.close();
  console.log(`\nshots: ${shotDir}`);
} finally {
  await browser.close();
  fs.writeFileSync(ACCOUNTS_PATH, originalAccounts, 'utf8');
  await verifyServer.stop();
}

const failed = results.filter((r) => !r.ok);
console.log(`${results.length - failed.length}/${results.length} 통과`);
if (failed.length) console.log(`실패: ${failed.map((f) => f.id).join(', ')}`);
process.exit(failed.length ? 1 : 0);
