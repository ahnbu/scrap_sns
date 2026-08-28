/**
 * LiveWiki 라이브러리 수집기.
 *
 * 인증 구조 — 「인증 생성자」와 「수집 실행자」 분리
 *   Playwright 인증 가이드의 기본 원칙을 따른다. `scripts/lilys_library.mjs` 와 같은 3-명령 구조다.
 *
 *   생성자 (브라우저 사용, 30일에 한 번)
 *     login      : 구글 로그인용 일반 Chrome 을 전용 프로필로 연다.
 *     check-auth : 로그인된 프로필이 앱으로 보내는 bearer JWT 를 가로채
 *                  credentials.json 으로 저장하고, 실제 API 를 한 번 때려 probe 한다.
 *
 *   실행자 (브라우저 없음)
 *     list       : 저장된 bearer 로 API 만 호출한다.
 *
 * Lilys 와 무엇이 다른가 (실측)
 *   Lilys 는 refresh_token 이 평문이고 회전하지 않아 access_token 을 무기한 재발급할 수 있다.
 *   LiveWiki 는 corelyAToken / corelyRToken 이 CryptoJS AES 암호문(`U2Fs...` = `Salted__`)이라
 *   복호화 키가 프런트 번들 안에 있다. 대신 bearer JWT 자체가 30일 유효하다.
 *   그래서 자동 갱신을 재현하지 않고 30일마다 check-auth 를 다시 도는 쪽을 택했다.
 *   복호화 재현은 배포마다 키가 바뀌면 조용히 깨지는 의존이고, 얻는 것이 30일에 1분뿐이라 기각했다.
 *
 * 인증 정본
 *   AUTH_HOME_LIVEWIKI > AUTH_HOME > ~/.config/auth  (utils/auth_paths.py 계약과 동일)
 *   <auth>/livewiki/user_data          Chrome 프로필 (yt-summary-livewiki 스킬과 공유)
 *   <auth>/livewiki/api_credentials.json   bearer JWT + 만료  ← 수집이 읽는 정본
 *   <auth>/livewiki/api_status.json        probe 결과 (비밀값 없음)
 *   <auth>/livewiki/profile.lock           프로필을 여는 명령에만 적용
 *
 *   status.json / storage_state.json 은 yt-summary-livewiki 스킬 소유라 건드리지 않는다.
 *
 * 사용법
 *   node scripts/livewiki_library.mjs login
 *   node scripts/livewiki_library.mjs check-auth
 *   node scripts/livewiki_library.mjs list [--out <path>] [--raw <path>] [--limit-pages N]
 *
 * 재실행/검증
 *   list 는 읽기 전용 수집이며 지정한 출력 파일만 덮어쓴다.
 *   결과 확인은 stdout 총건수와 저장 파일의 items 길이가 일치하는지로 본다.
 */

import fs from 'node:fs';
import fsp from 'node:fs/promises';
import https from 'node:https';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const API_HOST = 'api.livewiki.com';
const LIST_PATH = '/content/list/last/summarize';
const HOME_URL = 'https://livewiki.com/ko';
const CONTENT_BASE = 'https://livewiki.com/ko/content';
const PAGE_SIZE = 20;
/** 만료가 이만큼 남으면 경고한다. 30일짜리 토큰이라 일주일 전이면 충분하다. */
const EXPIRY_WARN_DAYS = 7;

const BROWSER_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  + 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36';
const BROWSER_LOCALE = 'ko-KR';
const BROWSER_VIEWPORT = { width: 1280, height: 1000 };

// --------------------------------------------------------------------------
// 경로 계약
// --------------------------------------------------------------------------

function authHome() {
  return process.env.AUTH_HOME || path.join(os.homedir(), '.config', 'auth');
}

function authPaths() {
  const root = process.env.AUTH_HOME_LIVEWIKI || path.join(authHome(), 'livewiki');
  return {
    root,
    userDataDir: path.join(root, 'user_data'),
    credentialsPath: path.join(root, 'api_credentials.json'),
    statusPath: path.join(root, 'api_status.json'),
    lockPath: path.join(root, 'profile.lock'),
  };
}

function nowKst() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date()).reduce((acc, p) => { acc[p.type] = p.value; return acc; }, {});
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} KST`;
}

function kstDate(ms) {
  return new Date(ms).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

async function writeJsonAtomic(target, payload) {
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.tmp`;
  await fsp.writeFile(tmp, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  await fsp.rename(tmp, target);
}

// --------------------------------------------------------------------------
// 프로필 잠금 — 브라우저를 여는 명령에만 적용한다 (list 는 잠그지 않는다)
// yt-summary-livewiki 스킬도 같은 프로필과 같은 lock 파일명을 쓴다.
// --------------------------------------------------------------------------

const LOCK_WAIT_MS = Number(process.env.LIVEWIKI_LOCK_WAIT_MS || 120 * 1000);
const LOCK_STALE_MS = Number(process.env.LIVEWIKI_LOCK_STALE_MS || 15 * 60 * 1000);

function processAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}

async function acquireProfileLock(lockPath, options = {}) {
  const waitMs = options.waitMs ?? LOCK_WAIT_MS;
  const staleMs = options.staleMs ?? LOCK_STALE_MS;
  const deadline = Date.now() + waitMs;
  let notified = false;

  for (;;) {
    try {
      await fsp.mkdir(path.dirname(lockPath), { recursive: true });
      const handle = await fsp.open(lockPath, 'wx');
      await handle.writeFile(JSON.stringify({
        pid: process.pid, acquired_at_ms: Date.now(), timestamp_kst: nowKst(),
      }));
      await handle.close();
      return makeReleaser(lockPath);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
    }

    let holder = null;
    try { holder = JSON.parse(await fsp.readFile(lockPath, 'utf8')); } catch (_) { holder = null; }

    const age = holder?.acquired_at_ms ? Date.now() - holder.acquired_at_ms : Infinity;
    const alive = processAlive(holder?.pid);
    if (!alive || age > staleMs) {
      process.stdout.write(`남아 있던 잠금을 회수합니다 (pid ${holder?.pid ?? '?'}, `
        + `${alive ? `${Math.round(age / 1000)}초 경과` : '프로세스 없음'})\n`);
      await fsp.unlink(lockPath).catch(() => {});
      continue;
    }
    if (Date.now() >= deadline) {
      throw new Error(`LiveWiki 프로필이 사용 중입니다 (pid ${holder.pid}). `
        + `${Math.round(waitMs / 1000)}초를 기다렸습니다: ${lockPath}`);
    }
    if (!notified) {
      process.stdout.write(`다른 LiveWiki 프로필 작업이 실행 중입니다 (pid ${holder.pid}). 대기합니다...\n`);
      notified = true;
    }
    await new Promise((resolve) => { setTimeout(resolve, 2000); });
  }
}

function makeReleaser(lockPath) {
  let released = false;
  const releaseSync = () => {
    if (released) return;
    released = true;
    try { fs.unlinkSync(lockPath); } catch (_) { /* 이미 없으면 그만이다 */ }
  };
  const onSignal = (signal) => { releaseSync(); process.exit(signal === 'SIGINT' ? 130 : 143); };
  process.once('exit', releaseSync);
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);
  return async () => {
    releaseSync();
    process.off('exit', releaseSync);
    process.off('SIGINT', onSignal);
    process.off('SIGTERM', onSignal);
  };
}

// --------------------------------------------------------------------------
// HTTP — node 기본 fetch(undici) 가 이 API 의 큰 응답에서 ERR_ASSERTION 으로
// 프로세스를 죽이는 것을 실측했다. https 모듈로 직접 받는다.
// --------------------------------------------------------------------------

function httpGet(pathname, headers, { timeoutMs = 90000 } = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request({
      host: API_HOST,
      path: pathname,
      method: 'GET',
      headers: { ...headers, 'accept-encoding': 'gzip' },
      agent: new https.Agent({ keepAlive: false }),
      timeout: timeoutMs,
    }, (res) => {
      const chunks = [];
      const stream = /gzip/.test(res.headers['content-encoding'] || '') ? res.pipe(zlib.createGunzip()) : res;
      stream.on('data', (chunk) => chunks.push(chunk));
      stream.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
      stream.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
    req.end();
  });
}

/** 실측: authorization 하나면 통과한다. 나머지 헤더는 예의 차원이다. */
function apiHeaders(token) {
  return {
    authorization: `Bearer ${token}`,
    accept: 'application/json',
    languagecode: 'ko',
    'user-agent': BROWSER_USER_AGENT,
    referer: 'https://livewiki.com/',
  };
}

// --------------------------------------------------------------------------
// 자격증명
// --------------------------------------------------------------------------

function jwtExpiryMs(token) {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
    return payload.exp ? payload.exp * 1000 : null;
  } catch (_) {
    return null;
  }
}

async function readCredentials(credentialsPath) {
  let raw;
  try {
    raw = await fsp.readFile(credentialsPath, 'utf8');
  } catch (_) {
    throw new Error('LiveWiki 자격증명이 없습니다.\n'
      + '  node scripts/livewiki_library.mjs login       (최초 1회, 브라우저 로그인)\n'
      + '  node scripts/livewiki_library.mjs check-auth  (자격증명 저장)');
  }
  const parsed = JSON.parse(raw);
  if (!parsed.bearer_token) {
    throw new Error(`자격증명이 불완전합니다: ${credentialsPath}\ncheck-auth 를 다시 실행하세요.`);
  }
  return parsed;
}

/** 만료가 지났으면 실패시키고, 임박하면 경고만 한다. */
function assertNotExpired(credentials) {
  const expiresAtMs = credentials.expires_at_ms || jwtExpiryMs(credentials.bearer_token);
  if (!expiresAtMs) return;
  const remainingDays = (expiresAtMs - Date.now()) / 86400000;
  if (remainingDays <= 0) {
    throw new Error(`LiveWiki 토큰이 만료됐습니다 (만료 ${kstDate(expiresAtMs)}).\n`
      + 'node scripts/livewiki_library.mjs login → check-auth 를 다시 실행하세요.');
  }
  if (remainingDays <= EXPIRY_WARN_DAYS) {
    process.stdout.write(`⚠ 토큰 만료까지 ${remainingDays.toFixed(1)}일 남았습니다 `
      + `(${kstDate(expiresAtMs)}). check-auth 를 다시 실행하세요.\n`);
  }
}

// --------------------------------------------------------------------------
// 브라우저 (login / check-auth 전용)
// --------------------------------------------------------------------------

function findChromeExecutable(env = process.env) {
  const candidates = [
    env.LIVEWIKI_CHROME_PATH,
    path.join(env.PROGRAMFILES || 'C:\\Program Files', 'Google\\Chrome\\Application\\chrome.exe'),
    path.join(env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google\\Chrome\\Application\\chrome.exe'),
    path.join(env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'Google\\Chrome\\Application\\chrome.exe'),
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || 'chrome.exe';
}

async function launchContext(profileDir) {
  const runnerPath = path.join(
    process.env.USERPROFILE || os.homedir(),
    '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs',
  );
  const { loadPlaywright } = await import(pathToFileURL(runnerPath).href);
  const { chromium } = loadPlaywright();
  await fsp.mkdir(profileDir, { recursive: true });
  return chromium.launchPersistentContext(profileDir, {
    headless: true,
    viewport: BROWSER_VIEWPORT,
    locale: BROWSER_LOCALE,
    timezoneId: 'Asia/Seoul',
    userAgent: BROWSER_USER_AGENT,
  });
}

/**
 * 로그인된 프로필이 API 로 보내는 bearer 를 가로챈다.
 * 토큰은 쿠키/localStorage 에 평문으로 없다 (AES 암호문이다). 런타임 요청에서만 잡힌다.
 */
async function captureBearer(page, { timeoutMs = 40000 } = {}) {
  let resolveFn;
  const captured = new Promise((resolve) => { resolveFn = resolve; });
  const onRequest = (req) => {
    if (!req.url().includes(API_HOST)) return;
    const auth = req.headers().authorization;
    if (auth) resolveFn(auth.replace(/^Bearer\s+/i, ''));
  };

  page.on('request', onRequest);
  try {
    await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
    const timer = new Promise((resolve) => { setTimeout(() => resolve(null), timeoutMs); });
    const token = await Promise.race([captured, timer]);
    if (token) return token;
    const loggedOut = await page.evaluate(() => /Google로 계속하기|Continue with Google|로그인 \/ 회원가입/i
      .test(document.body?.innerText || '')).catch(() => false);
    throw new Error(loggedOut
      ? 'LiveWiki 로그인이 필요합니다. `node scripts/livewiki_library.mjs login` 을 먼저 실행하세요.'
      : '인증 토큰을 잡지 못했습니다. 화면 구조가 바뀌었을 수 있습니다.');
  } finally {
    page.off('request', onRequest);
  }
}

// --------------------------------------------------------------------------
// 명령
// --------------------------------------------------------------------------

async function cmdLogin() {
  const paths = authPaths();
  await fsp.mkdir(paths.userDataDir, { recursive: true });
  if (fs.existsSync(paths.lockPath)) {
    let holder = null;
    try { holder = JSON.parse(fs.readFileSync(paths.lockPath, 'utf8')); } catch (_) { holder = null; }
    if (processAlive(holder?.pid)) {
      throw new Error(`LiveWiki 프로필 작업이 실행 중입니다 (pid ${holder.pid}). 끝난 뒤 다시 실행하세요.`);
    }
    await fsp.unlink(paths.lockPath).catch(() => {});
  }

  const executable = findChromeExecutable();
  const child = spawn(executable, [
    `--user-data-dir=${paths.userDataDir}`,
    '--profile-directory=Default',
    `--lang=${BROWSER_LOCALE}`,
    `--window-size=${BROWSER_VIEWPORT.width},${BROWSER_VIEWPORT.height}`,
    `--user-agent=${BROWSER_USER_AGENT}`,
    HOME_URL,
  ], { detached: true, stdio: 'ignore', windowsHide: false });
  child.unref();

  process.stdout.write([
    'LiveWiki 수동 로그인용 일반 Chrome 을 열었습니다.',
    '이 창에서 로그인을 완료한 뒤 반드시 창을 닫으세요.',
    '이 프로필은 yt-summary-livewiki 스킬과 공유합니다.',
    '그 다음 `node scripts/livewiki_library.mjs check-auth` 를 실행하세요.',
    `Chrome: ${executable}`,
    `프로필: ${paths.userDataDir}`,
    '',
  ].join('\n'));
}

async function cmdCheckAuth() {
  const paths = authPaths();
  const release = await acquireProfileLock(paths.lockPath);
  let token = null;
  let failure = '';
  try {
    const context = await launchContext(paths.userDataDir);
    try {
      const page = context.pages()[0] || await context.newPage();
      token = await captureBearer(page);
    } catch (error) {
      failure = error.message.split('\n')[0];
    } finally {
      await context.close();
    }
  } finally {
    await release();
  }

  const expiresAtMs = token ? jwtExpiryMs(token) : null;
  if (!failure) {
    await writeJsonAtomic(paths.credentialsPath, {
      platform: 'livewiki',
      // 30일짜리 API 토큰이다. 로그·출력·커밋에 절대 내보내지 않는다.
      bearer_token: token,
      expires_at_ms: expiresAtMs,
      expires_at_kst: expiresAtMs ? kstDate(expiresAtMs) : '',
      updated_at_kst: nowKst(),
    });
    // 파일 존재가 아니라 실제 API 통과를 성공 기준으로 삼는다.
    try {
      const probe = await httpGet('/folder/workspace/summary', apiHeaders(token));
      const payload = JSON.parse(probe.body);
      if (probe.status !== 200 || payload.apiCode !== 0) {
        failure = `api_probe_apiCode_${payload.apiCode ?? probe.status}`;
      }
    } catch (error) {
      failure = `api_probe_error:${error.message.slice(0, 60)}`;
    }
  }

  await writeJsonAtomic(paths.statusPath, {
    platform: 'livewiki',
    timestamp_kst: nowKst(),
    profile_ok: fs.existsSync(paths.userDataDir),
    credentials_saved: fs.existsSync(paths.credentialsPath),
    probe_ok: !failure,
    expires_at_kst: expiresAtMs ? kstDate(expiresAtMs) : '',
    failure_reason: failure,
    profile_dir: paths.userDataDir,
  });

  if (failure) {
    throw new Error(`LiveWiki 인증 확인 실패: ${failure}\n`
      + '`node scripts/livewiki_library.mjs login` 으로 다시 로그인하세요.');
  }
  process.stdout.write(`AUTH_OK ${paths.statusPath}`
    + `${expiresAtMs ? ` (만료 ${kstDate(expiresAtMs)})` : ''}\n`);
}

// --------------------------------------------------------------------------
// 항목 정규화
// --------------------------------------------------------------------------

function toItem(content) {
  const video = content?.source?.youtubeVideo;
  if (!video?.v) return null;
  return {
    video_id: video.v,
    content_id: content.id,
    url: `${CONTENT_BASE}/${content.slug}`,
    title: video.title || '',
    channel: video.youtubeChannel?.name || '',
    channel_handle: video.youtubeChannel?.handle || '',
    upload_date: video.uploadDate || '',
  };
}

async function cmdList(options) {
  const paths = authPaths();
  const outPath = path.resolve(options.out || path.join('output_external', 'livewiki_library.json'));
  const maxPages = Number(options['limit-pages'] || 300);

  const credentials = await readCredentials(paths.credentialsPath);
  assertNotExpired(credentials);
  const headers = apiHeaders(credentials.bearer_token);

  const contents = [];
  let totalContents = null;
  let bytes = 0;
  for (let p = 0; p < maxPages; p += 1) {
    let page = null;
    for (let attempt = 0; attempt < 3 && page === null; attempt += 1) {
      let res;
      try {
        res = await httpGet(`${LIST_PATH}?page=${p}&size=${PAGE_SIZE}`, headers);
      } catch (error) {
        if (attempt === 2) throw new Error(`page ${p} 요청 실패: ${error.message}`);
        await new Promise((resolve) => { setTimeout(resolve, 700 * (attempt + 1)); });
        continue;
      }
      if (res.status !== 200) throw new Error(`page ${p} HTTP ${res.status}`);
      bytes += res.body.length;
      const payload = JSON.parse(res.body);
      if (payload.apiCode === 401) {
        throw new Error('LiveWiki 토큰이 거부됐습니다 (401).\n'
          + 'node scripts/livewiki_library.mjs login → check-auth 를 다시 실행하세요.');
      }
      const result = payload.result;
      if (!result || !Array.isArray(result.contentList)) {
        throw new Error(`page ${p} 응답 형태가 예상과 다릅니다.`);
      }
      totalContents = result.totalContents ?? totalContents;
      page = result.contentList;
    }
    if (page === null) throw new Error(`page ${p} 를 3회 시도에도 받지 못했습니다.`);
    if (page.length === 0) break;
    contents.push(...page);
    if (p % 5 === 0 || page.length < PAGE_SIZE) {
      process.stdout.write(`  page ${p}: 누적 ${contents.length}`
        + `${totalContents ? ` / ${totalContents}` : ''}\n`);
    }
    if (totalContents && contents.length >= totalContents) break;
    if (page.length < PAGE_SIZE) break;
  }

  const unique = [...new Map(contents.filter((c) => c?.slug).map((c) => [c.slug, c])).values()];
  const items = unique.map(toItem).filter(Boolean);
  // 같은 영상을 두 번 요약한 경우가 있다. 마지막 것을 남긴다.
  const byVideo = new Map(items.map((item) => [item.video_id, item]));
  const finalItems = [...byVideo.values()];

  await writeJsonAtomic(outPath, {
    source: 'livewiki',
    collected_at_kst: nowKst(),
    total_contents: unique.length,
    youtube_contents: items.length,
    unique_video_count: finalItems.length,
    items: finalItems,
  });

  if (options.raw) {
    const rawPath = path.resolve(options.raw);
    await fsp.mkdir(path.dirname(rawPath), { recursive: true });
    await fsp.writeFile(rawPath, `${JSON.stringify(unique, null, 1)}\n`, 'utf8');
    process.stdout.write(`원본 저장: ${rawPath}\n`);
  }

  process.stdout.write([
    '',
    `콘텐츠 ${unique.length}건 / 유튜브 ${items.length}건 / 고유 영상 ${finalItems.length}건`
      + ` (응답 ${(bytes / 1048576).toFixed(1)}MB)`,
    `저장: ${outPath}`,
    '',
  ].join('\n'));
}

// --------------------------------------------------------------------------

function parseArgs(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    const key = argv[i].slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) { options[key] = next; i += 1; } else { options[key] = true; }
  }
  return options;
}

const USAGE = `사용법:
  node scripts/livewiki_library.mjs login        # 최초 1회 (그리고 토큰 만료 시). 브라우저 로그인
  node scripts/livewiki_library.mjs check-auth   # bearer 저장 + 실제 API probe
  node scripts/livewiki_library.mjs list [--out <path>] [--raw <path>] [--limit-pages N]
                                                 # 브라우저 없이 수집
`;

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  const options = parseArgs(rest);
  if (command === 'login') return cmdLogin();
  if (command === 'check-auth') return cmdCheckAuth();
  if (command === 'list') return cmdList(options);
  process.stdout.write(USAGE);
  process.exitCode = command ? 1 : 0;
  return undefined;
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
