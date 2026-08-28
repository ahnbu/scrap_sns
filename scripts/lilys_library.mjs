/**
 * Lilys AI 라이브러리 수집기.
 *
 * 인증 구조 — 「인증 생성자」와 「수집 실행자」 분리
 *   Playwright 인증 가이드의 기본 원칙을 따른다.
 *
 *   생성자 (브라우저 사용, 사람이 한 번)
 *     login      : 구글 로그인용 일반 Chrome 을 전용 프로필로 연다.
 *     check-auth : 그 프로필에서 refresh_token 과 Firebase API key 를 꺼내
 *                  credentials.json 으로 저장하고, 실제 API 를 한 번 때려 probe 한다.
 *
 *   실행자 (브라우저 없음)
 *     list       : credentials.json 으로 access_token 을 발급받아 API 만 호출한다.
 *
 * 왜 storage_state 가 아닌가 (실측)
 *   Lilys 는 Firebase Auth 를 쓴다. access_token 수명은 3600초고,
 *   Playwright storage_state 는 localStorage 만 담고 IndexedDB 를 담지 않아
 *   복제한 컨텍스트에서 토큰 자동 재발급이 실패한다.
 *   그래서 storage_state 를 정본으로 쓰지 않는다.
 *
 * 왜 브라우저를 매번 띄우지 않는가 (실측)
 *   refresh_token 은 회전하지 않고, securetoken.googleapis.com 으로
 *   access_token 을 얼마든지 다시 받을 수 있다. 즉 장기 자격증명은 파일 하나면 된다.
 *   덕분에 수집 실행에는 브라우저도 프로필 잠금도 필요 없고,
 *   total_scrap 의 병렬 실행과도 충돌하지 않는다.
 *   저장하는 것은 만료되는 access_token 이 아니라 refresh_token 이다.
 *   LinkedIn/Threads 가 쿠키 jar 를 저장하는 것과 같은 층이다.
 *
 * 인증 정본
 *   AUTH_HOME_LILYS > AUTH_HOME > ~/.config/auth  (utils/auth_paths.py 계약과 동일)
 *   <auth>/lilys/user_data          Chrome 프로필 (로그인 갱신용)
 *   <auth>/lilys/credentials.json   refresh_token + api_key  ← 수집이 읽는 정본
 *   <auth>/lilys/status.json        probe 결과 (비밀값 없음)
 *   <auth>/lilys/profile.lock       프로필을 여는 명령에만 적용
 *
 * 사용법
 *   node scripts/lilys_library.mjs login
 *   node scripts/lilys_library.mjs check-auth
 *   node scripts/lilys_library.mjs list [--out <path>] [--raw <path>] [--limit-pages N]
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

const API_HOST = 'api.lilys.ai';
const TOKEN_HOST = 'securetoken.googleapis.com';
const LIST_PATH = '/backend/digest-sessions';
const HOME_URL = 'https://lilys.ai/ko/';
const PROVIDER = 'google';
const PAGE_SIZE = 20;

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
  const root = process.env.AUTH_HOME_LILYS || path.join(authHome(), 'lilys');
  return {
    root,
    userDataDir: path.join(root, 'user_data'),
    credentialsPath: path.join(root, 'credentials.json'),
    statusPath: path.join(root, 'status.json'),
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

async function writeJsonAtomic(target, payload) {
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.tmp`;
  await fsp.writeFile(tmp, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  await fsp.rename(tmp, target);
}

// --------------------------------------------------------------------------
// 프로필 잠금 — 브라우저를 여는 명령에만 적용한다 (list 는 잠그지 않는다)
// --------------------------------------------------------------------------

const LOCK_WAIT_MS = Number(process.env.LILYS_LOCK_WAIT_MS || 120 * 1000);
const LOCK_STALE_MS = Number(process.env.LILYS_LOCK_STALE_MS || 15 * 60 * 1000);

function processAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM 은 살아 있으나 권한이 없는 경우다.
    return error.code === 'EPERM';
  }
}

/**
 * 하드 실패시키지 않는다. 강제 종료(taskkill /F)로 남은 잠금은 회수하고,
 * 살아 있는 홀더가 있으면 기다린다.
 */
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
      throw new Error(`Lilys 프로필이 사용 중입니다 (pid ${holder.pid}). `
        + `${Math.round(waitMs / 1000)}초를 기다렸습니다: ${lockPath}`);
    }
    if (!notified) {
      process.stdout.write(`다른 Lilys 프로필 작업이 실행 중입니다 (pid ${holder.pid}). 대기합니다...\n`);
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
// HTTP — node 기본 fetch(undici) 가 큰 응답에서 ERR_ASSERTION 으로
// 프로세스를 죽이는 사례를 실측했다. https 모듈로 직접 받는다.
// --------------------------------------------------------------------------

function request(host, pathname, { method = 'GET', headers = {}, body = null, timeoutMs = 60000 } = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request({
      host,
      path: pathname,
      method,
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
    if (body) req.write(body);
    req.end();
  });
}

// --------------------------------------------------------------------------
// 자격증명
// --------------------------------------------------------------------------

async function readCredentials(credentialsPath) {
  let raw;
  try {
    raw = await fsp.readFile(credentialsPath, 'utf8');
  } catch (_) {
    throw new Error('Lilys 자격증명이 없습니다.\n'
      + '  node scripts/lilys_library.mjs login       (최초 1회, 브라우저 로그인)\n'
      + '  node scripts/lilys_library.mjs check-auth  (자격증명 저장)');
  }
  const parsed = JSON.parse(raw);
  if (!parsed.refresh_token || !parsed.api_key) {
    throw new Error(`자격증명이 불완전합니다: ${credentialsPath}\ncheck-auth 를 다시 실행하세요.`);
  }
  return parsed;
}

/** refresh_token 으로 1시간짜리 access_token 을 받는다. 브라우저가 필요 없다. */
async function mintAccessToken(credentials) {
  const res = await request(TOKEN_HOST, `/v1/token?key=${encodeURIComponent(credentials.api_key)}`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: credentials.refresh_token,
    }).toString(),
  });
  let payload = {};
  try { payload = JSON.parse(res.body); } catch (_) { /* 아래에서 처리 */ }
  const token = payload.id_token || payload.access_token;
  if (res.status !== 200 || !token) {
    const reason = payload?.error?.message || `HTTP ${res.status}`;
    throw new Error(`access_token 발급 실패: ${reason}\n`
      + 'refresh_token 이 무효해졌을 수 있습니다. login → check-auth 를 다시 실행하세요.');
  }
  return { token, expiresInSec: Number(payload.expires_in || 3600) };
}

function apiHeaders(token) {
  return {
    authorization: `Bearer ${token}`,
    'lilys-provider': PROVIDER,
    accept: 'application/json',
    'accept-language': 'ko',
    'user-agent': BROWSER_USER_AGENT,
    referer: 'https://lilys.ai/',
  };
}

function listUrl(page) {
  return `${LIST_PATH}?provider=${PROVIDER}&page=${page}&sortType=newest`
    + `&limit=${PAGE_SIZE}&inboxStatus=inbox`;
}

function extractList(payload) {
  if (Array.isArray(payload)) return payload;
  for (const key of ['digestSessions', 'sessions', 'data', 'items', 'result', 'list']) {
    if (Array.isArray(payload?.[key])) return payload[key];
  }
  return null;
}

// --------------------------------------------------------------------------
// 브라우저 (login / check-auth 전용)
// --------------------------------------------------------------------------

function findChromeExecutable(env = process.env) {
  const candidates = [
    env.LILYS_CHROME_PATH,
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

/** 로그인된 프로필에서 장기 자격증명만 꺼낸다. access_token 은 가져가지 않는다. */
async function extractCredentials(page) {
  await page.goto(HOME_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(6000);
  return page.evaluate(async () => {
    const refreshToken = localStorage.getItem('refresh_token') || '';
    let keys = [];
    try {
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('firebaseLocalStorageDb');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      const store = db.transaction('firebaseLocalStorage', 'readonly').objectStore('firebaseLocalStorage');
      keys = await new Promise((resolve) => {
        const req = store.getAllKeys();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve([]);
      });
    } catch (_) { keys = []; }
    // 키 형식: firebase:authUser:<API_KEY>:[DEFAULT]
    const authKey = keys.find((k) => /^firebase:authUser:/.test(String(k))) || '';
    const account = (document.body?.innerText || '').match(/[\w.+-]+@[\w.-]+\.\w+/)?.[0] || '';
    const loggedOut = /로그인 \/ 회원가입|Sign in/i.test(document.body?.innerText || '');
    return {
      refreshToken,
      apiKey: String(authKey).split(':')[2] || '',
      account,
      loggedOut,
    };
  });
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
      throw new Error(`Lilys 프로필 작업이 실행 중입니다 (pid ${holder.pid}). 끝난 뒤 다시 실행하세요.`);
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
    'Lilys 수동 로그인용 일반 Chrome 을 열었습니다.',
    '이 창에서 로그인을 완료한 뒤 반드시 창을 닫으세요.',
    '평소 쓰던 것과 같은 계정, 같은 로그인 수단을 쓰세요. 다르면 라이브러리가 비어 보입니다.',
    '그 다음 `node scripts/lilys_library.mjs check-auth` 를 실행하세요.',
    `Chrome: ${executable}`,
    `프로필: ${paths.userDataDir}`,
    '',
  ].join('\n'));
}

async function cmdCheckAuth() {
  const paths = authPaths();
  const release = await acquireProfileLock(paths.lockPath);
  let extracted = null;
  let failure = '';
  try {
    const context = await launchContext(paths.userDataDir);
    try {
      const page = context.pages()[0] || await context.newPage();
      extracted = await extractCredentials(page);
    } finally {
      await context.close();
    }
  } finally {
    await release();
  }

  if (!extracted?.refreshToken || !extracted.apiKey) {
    failure = extracted?.loggedOut
      ? 'not_logged_in'
      : 'credentials_not_found';
  }

  if (!failure) {
    await writeJsonAtomic(paths.credentialsPath, {
      platform: 'lilys',
      // 장기 자격증명이다. 로그·출력·커밋에 절대 내보내지 않는다.
      refresh_token: extracted.refreshToken,
      api_key: extracted.apiKey,
      account: extracted.account,
      updated_at_kst: nowKst(),
    });
    // 파일 존재가 아니라 실제 API 통과를 성공 기준으로 삼는다.
    try {
      const { token } = await mintAccessToken(await readCredentials(paths.credentialsPath));
      const probe = await request(API_HOST, listUrl(1), { headers: apiHeaders(token) });
      if (probe.status !== 200) failure = `api_probe_http_${probe.status}`;
      else if (extractList(JSON.parse(probe.body)) === null) failure = 'api_probe_shape';
    } catch (error) {
      failure = error.message.split('\n')[0];
    }
  }

  await writeJsonAtomic(paths.statusPath, {
    platform: 'lilys',
    timestamp_kst: nowKst(),
    profile_ok: fs.existsSync(paths.userDataDir),
    credentials_saved: fs.existsSync(paths.credentialsPath),
    probe_ok: !failure,
    account: extracted?.account || '',
    failure_reason: failure,
    profile_dir: paths.userDataDir,
  });

  if (failure) {
    throw new Error(`Lilys 인증 확인 실패: ${failure}\n`
      + '`node scripts/lilys_library.mjs login` 으로 다시 로그인하세요.');
  }
  process.stdout.write(`AUTH_OK ${paths.statusPath}`
    + `${extracted.account ? ` (${extracted.account})` : ''}\n`);
}

// --------------------------------------------------------------------------
// 항목 정규화
// --------------------------------------------------------------------------

function videoIdOf(session) {
  const fromResource = (session.resources || []).map((r) => r?.sourceId).find(Boolean);
  if (fromResource) return fromResource;
  const thumb = String(session.sessionData?.thumbnailUrl || '');
  const matched = thumb.match(/ytimg\.com\/vi(?:_webp)?\/([A-Za-z0-9_-]{6,})\//);
  return matched ? matched[1] : null;
}

function toItem(session) {
  return {
    video_id: videoIdOf(session),
    session_id: session.sid,
    url: `https://lilys.ai/digest/${session.sid}`,
    title: session.name || '',
    channel: session.sessionData?.channelName || '',
    created_at: session.created || '',
  };
}

async function cmdList(options) {
  const paths = authPaths();
  const outPath = path.resolve(options.out || path.join('output_external', 'lilys_library.json'));
  const maxPages = Number(options['limit-pages'] || 200);

  const credentials = await readCredentials(paths.credentialsPath);
  let minted = await mintAccessToken(credentials);
  // 만료 직전에 미리 갱신한다. 발급은 HTTP 한 번이라 싸다.
  let expiresAt = Date.now() + (minted.expiresInSec - 120) * 1000;
  process.stdout.write(`access_token 발급 완료 (유효 ${minted.expiresInSec}초). 페이징을 시작합니다.\n`);

  const sessions = [];
  let remints = 0;
  for (let p = 1; p <= maxPages; p += 1) {
    if (Date.now() > expiresAt) {
      minted = await mintAccessToken(credentials);
      expiresAt = Date.now() + (minted.expiresInSec - 120) * 1000;
      remints += 1;
    }

    let list = null;
    for (let attempt = 0; attempt < 3 && list === null; attempt += 1) {
      let res;
      try {
        res = await request(API_HOST, listUrl(p), { headers: apiHeaders(minted.token) });
      } catch (error) {
        if (attempt === 2) throw new Error(`page ${p} 요청 실패: ${error.message}`);
        continue;
      }
      if (res.status === 401 || res.status === 403) {
        minted = await mintAccessToken(credentials);
        expiresAt = Date.now() + (minted.expiresInSec - 120) * 1000;
        remints += 1;
        continue;
      }
      if (res.status !== 200) throw new Error(`page ${p} HTTP ${res.status}`);
      const parsed = extractList(JSON.parse(res.body));
      if (parsed === null) throw new Error(`page ${p} 응답 형태가 예상과 다릅니다.`);
      list = parsed;
    }
    if (list === null) throw new Error(`page ${p} 를 3회 시도에도 받지 못했습니다.`);
    if (list.length === 0) break;
    sessions.push(...list);
    process.stdout.write(`  page ${p}: ${list.length}건 (누적 ${sessions.length})\n`);
    if (list.length < PAGE_SIZE) break;
  }
  if (remints) process.stdout.write(`토큰 재발급 ${remints}회\n`);

  const uniqueSessions = [...new Map(sessions.map((s) => [s.sid, s])).values()];
  const youtube = uniqueSessions.filter((s) => s.sourceType === 'youtube_video');
  const items = youtube.map(toItem).filter((item) => item.video_id);
  // 같은 영상을 두 번 요약한 경우가 있다. 최신 세션을 남긴다.
  const byVideo = new Map();
  for (const item of items.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))) {
    byVideo.set(item.video_id, item);
  }
  const finalItems = [...byVideo.values()];

  await writeJsonAtomic(outPath, {
    source: 'lilys',
    collected_at_kst: nowKst(),
    total_sessions: uniqueSessions.length,
    youtube_sessions: youtube.length,
    unique_video_count: finalItems.length,
    items: finalItems,
  });

  if (options.raw) {
    const rawPath = path.resolve(options.raw);
    await fsp.mkdir(path.dirname(rawPath), { recursive: true });
    await fsp.writeFile(rawPath, `${JSON.stringify(uniqueSessions, null, 1)}\n`, 'utf8');
    process.stdout.write(`원본 저장: ${rawPath}\n`);
  }

  process.stdout.write([
    '',
    `세션 ${uniqueSessions.length}건 / 유튜브 ${youtube.length}건 / 고유 영상 ${finalItems.length}건`,
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
  node scripts/lilys_library.mjs login        # 최초 1회. 브라우저 로그인
  node scripts/lilys_library.mjs check-auth   # 자격증명 저장 + 실제 API probe
  node scripts/lilys_library.mjs list [--out <path>] [--raw <path>] [--limit-pages N]
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
