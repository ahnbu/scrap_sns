/**
 * 계정 연결 파일럿 — 스레드 계정 페이지의 소개란 링크(본인이 게시한 링크)로 다른
 * 플랫폼 계정을 찾는다. 창을 띄우지 않는다. 비로그인만 쓴다.
 *
 * 왜 파일럿인가: "링크 모음 페이지 하나로 전 채널"은 미검증 가설이다(SPEC F19 정정).
 * 병행 세션은 정적 스크랩으로 실패했다(허브 링크가 JS 렌더). 소수로 적중률을 먼저 재고
 * 기준을 넘을 때만 넓힌다(SPEC A2′-개정, 계획 W5).
 *
 *   ① 스레드 계정 페이지를 비로그인으로 받는다 — scrap-my 의 scrapling 경로(F30).
 *   ② 소개란 링크가 링크 모음(linktr.ee·litt.ly 등)이면 헤드리스 브라우저로 렌더해 링크를 모은다.
 *   ③ 얻은 핸들을 통합본 저자 키와 대조한다(x·threads username, youtube channel_id).
 *
 * 조회 상한: 대상 1명당 최대 2페이지, 요청 간격 3초 이상. 요청마다 로그를 남긴다.
 * 게이트: 파일럿 5명 중 3명 이상이 "통합본에 글이 있는 다른 플랫폼 계정" 1개 이상.
 *
 * 확정 연결(`--apply`)은 본인이 게시한 링크(소개란·링크 모음)로 찾은 것만 저장한다
 * (`source: self_declared`). 운영 서버의 `POST /api/save-creator-links` 를 쓴다.
 *
 * Usage:
 *   node scripts/creator_link_pilot.mjs                 # 파일럿 5명, 저장 안 함
 *   node scripts/creator_link_pilot.mjs --all --apply   # 게이트 통과 후 대상 전원 + 저장
 * 계획: _docs/20260911_01 (W5 T5-a~T5-d)
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const BASE_URL = (process.env.SNS_VIEWER_URL || 'http://localhost:5000').replace(/\/$/, '');
const EVIDENCE_DIR = path.join(process.cwd(), '_docs', 'evidence');
const REQUEST_LOG = path.join(EVIDENCE_DIR, '20260911_w5_requests.log');
const RESULT_LOG = path.join(EVIDENCE_DIR, '20260911_w5_pilot_result.log');
const CACHE_PATH = path.join(EVIDENCE_DIR, '20260911_w5_fetch_cache.log');
const SCRAPLING_RUNNER = path.join(os.homedir(), '.claude', 'skills', 'scrap-my', 'scripts', 'run-scrapling-extract.mjs');
const MIN_INTERVAL_MS = 3000;
const MAX_PAGES_PER_TARGET = 2;
const PILOT_SIZE = 5;
const PILOT_FIXED = 'unclejobs.ai';   // 링크 모음 보유가 확인된 계정(SPEC F19)
const AGGREGATOR_RE = /(^|\.)(linktr\.ee|litt\.ly|beacons\.ai|bio\.link|lnk\.bio|linkin\.bio|taplink\.cc|inpock\.co\.kr|linkbio\.co|campsite\.bio|carrd\.co|stan\.store|solo\.to|allmylinks\.com|hoo\.be|link\.me|contactin\.bio|linkr\.bio|linkfly\.to)$/i;

const args = new Set(process.argv.slice(2));
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const normalize = (value) => String(value || '').trim().toLowerCase().replace(/^@/, '');
let lastRequestAt = 0;
let requestCount = 0;
async function politeWait() {
  const wait = lastRequestAt + MIN_INTERVAL_MS - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  lastRequestAt = Date.now();
}
function logRequest(kind, url, status) {
  requestCount += kind === 'api' ? 0 : 1;
  const line = `${new Date().toISOString()}\t${kind}\t${status}\t${url}\n`;
  fs.appendFileSync(REQUEST_LOG, line, 'utf8');
}

// 재실행 때 같은 페이지를 다시 받지 않는다(상한 보호). 대상별 결과만 캐시한다.
const cache = fs.existsSync(CACHE_PATH) ? JSON.parse(fs.readFileSync(CACHE_PATH, 'utf8') || '{}') : {};
const saveCache = () => fs.writeFileSync(CACHE_PATH, JSON.stringify(cache, null, 2), 'utf8');

// 운영 서버 호출. node 내장 fetch 는 쓰지 않는다 - /api/posts(gzip 1MB+)를 받다가
// 서버가 연결을 닫는 순간 undici 내부 단언(assert(!this.paused))으로 프로세스가
// 죽었다(2026-09-11 재현, Node 24). 기본 http 모듈 + 무압축으로 받는다.
function requestJson(method, url, body) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const payload = body ? Buffer.from(JSON.stringify(body)) : null;
    const req = http.request({
      method,
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      headers: {
        'Accept-Encoding': 'identity',
        ...(payload ? { 'Content-Type': 'application/json', 'Content-Length': payload.length } : {}),
      },
    }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') });
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function loadPosts() {
  const { status, data } = await requestJson('GET', `${BASE_URL}/api/posts`);
  if (status !== 200) throw new Error(`/api/posts ${status}`);
  return data.posts;
}

/** T5-a 대상 — 스레드 5건 이상 · 레지스트리에 다른 플랫폼 미연결 · 벤치마킹 계정에 다른 채널 없음 · 내 글 아님. */
function computeTargets(posts) {
  const accounts = JSON.parse(fs.readFileSync(path.join('web_viewer', 'benchmark_accounts.json'), 'utf8')).accounts || [];
  const benchMulti = new Set(accounts
    .filter((a) => (a.channels || {}).threads && Object.entries(a.channels).some(([p, v]) => p !== 'threads' && v))
    .map((a) => normalize(a.channels.threads)));
  const platformsByCreator = new Map();
  posts.forEach((post) => {
    if (!post.creator_id || post.sns_platform === 'web' || post.sns_platform === 'file') return;
    const set = platformsByCreator.get(post.creator_id) || new Set();
    set.add(post.sns_platform === 'twitter' ? 'x' : post.sns_platform);
    platformsByCreator.set(post.creator_id, set);
  });
  const byHandle = new Map();
  posts.forEach((post) => {
    if (post.sns_platform !== 'threads' || !post.username) return;
    const handle = normalize(post.username);
    const entry = byHandle.get(handle) || { handle, count: 0, own: false, creatorId: post.creator_id || '' };
    entry.count += 1;
    entry.own = entry.own || post.is_own_post === true;
    byHandle.set(handle, entry);
  });
  return [...byHandle.values()]
    .filter((entry) => entry.count >= 5 && !entry.own && !benchMulti.has(entry.handle))
    .filter((entry) => {
      const platforms = platformsByCreator.get(entry.creatorId);
      return !platforms || [...platforms].every((p) => p === 'threads');
    })
    .sort((a, b) => b.count - a.count || a.handle.localeCompare(b.handle));
}

function fetchThreadsProfile(handle) {
  const url = `https://www.threads.com/@${handle}`;
  const out = path.join(os.tmpdir(), `w5_threads_${handle.replace(/[^\w.-]/g, '_')}.html`);
  // --reparse: 이미 받은 페이지를 다시 받지 않는다(1명당 2페이지 상한).
  if (args.has('--reparse') && fs.existsSync(out) && fs.statSync(out).size > 0) {
    logRequest('cache', url, 'reuse');
    requestCount -= 1;
    return fs.readFileSync(out, 'utf8');
  }
  const result = spawnSync('node', [SCRAPLING_RUNNER, '--fetcher', 'stealthy-fetch', '--url', url, '--output', out], {
    encoding: 'utf8', windowsHide: true, timeout: 120000,
  });
  const ok = result.status === 0 && fs.existsSync(out);
  logRequest('threads', url, ok ? 'ok' : `fail:${result.status}`);
  return ok ? fs.readFileSync(out, 'utf8') : '';
}

/** `"key":` 뒤의 JSON 배열을 괄호 짝으로 잘라낸다. 문자열 속 `]`(링크 제목 「[돈 버는 기술]」)에서
 *  끊기지 않는다 - 정규식 `[^\]]*` 로 잘랐다가 파싱이 실패해 소개란 링크를 통째로 잃었다(2026-09-11). */
function sliceJsonArray(text, start) {
  let depth = 0; let inString = false; let escaped = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '[' || ch === '{') depth += 1;
    else if (ch === ']' || ch === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return '';
}

/**
 * 소개란 링크 — **본인이 게시한 링크만**. 계정 페이지 내장 JSON 의 `bio_links` 와 머리의
 * `<link rel="me">` 둘이다. 게시글 속 링크(l.threads.com 리다이렉트)는 쓰지 않는다 - 남의
 * 콘텐츠 소개가 더 많아(SPEC D5 0단계 한계) 확정 연결의 근거가 못 된다.
 */
function extractBioLinks(html, handle) {
  const urls = new Set();
  for (const match of html.matchAll(/"bio_links"\s*:\s*\[/g)) {
    const block = sliceJsonArray(html, match.index + match[0].length - 1);
    try {
      JSON.parse(block).forEach((item) => item?.url && urls.add(item.url));
    } catch {
      // 짝이 안 맞는 조각은 건너뛴다.
    }
  }
  for (const match of html.matchAll(/<link rel="me" href="([^"]+)"/g)) {
    urls.add(match[1]);
  }
  return [...urls]
    .map((u) => (/^https?:\/\//i.test(u) ? u : `https://${u}`))
    .filter((u) => !new RegExp(`threads\\.(com|net)/@?${handle}(/|$)`, 'i').test(u));
}

async function renderAggregator(browser, url) {
  const context = await browser.newContext({ locale: 'ko-KR', viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  let status = 'fail';
  let links = [];
  try {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    status = response ? String(response.status()) : 'no-response';
    await page.waitForTimeout(3000);
    links = await page.$$eval('a[href]', (anchors) => anchors.map((a) => a.href));
  } catch (error) {
    status = `error:${String(error.message || error).slice(0, 60)}`;
  } finally {
    await context.close();
  }
  logRequest('aggregator', url, status);
  return links;
}

/** URL → 다른 플랫폼 계정. 판정 키는 핸들·채널 ID 뿐이다(이름으로 잇지 않는다). */
function accountsFromUrls(urls) {
  const found = new Map();
  const add = (platform, key, url) => {
    if (key) found.set(`${platform}|${normalize(key)}`, { platform, key: normalize(key), url });
  };
  urls.forEach((raw) => {
    let url;
    try { url = new URL(raw); } catch { return; }
    const host = url.hostname.toLowerCase().replace(/^(www|m|kr)\./, '');
    const segments = url.pathname.split('/').filter(Boolean).map((s) => decodeURIComponent(s));
    if (host === 'x.com' || host === 'twitter.com') {
      if (segments[0] && !['intent', 'share', 'home', 'i', 'search'].includes(segments[0].toLowerCase())) add('x', segments[0], raw);
    } else if (host === 'youtube.com' || host === 'youtu.be') {
      if (segments[0]?.startsWith('@')) add('youtube_handle', segments[0], raw);
      else if (segments[0] === 'channel' && segments[1]) found.set(`youtube|${segments[1]}`, { platform: 'youtube', key: segments[1], url: raw });
    } else if (host.endsWith('linkedin.com')) {
      if (segments[0] === 'in' && segments[1]) add('linkedin_slug', segments[1], raw);
    } else if (host.startsWith('threads.')) {
      if (segments[0]?.startsWith('@')) add('threads', segments[0], raw);
    }
  });
  return [...found.values()];
}

async function resolveYoutubeHandle(handle) {
  const url = `${BASE_URL}/api/verify-channel?platform=youtube&handle=${encodeURIComponent(handle)}`;
  const { status, data } = await requestJson('GET', url);
  logRequest('api', `youtube-api forHandle=${handle}`, data.ok ? 'ok' : (data.reason || status));
  return data.ok ? data.channel_id : '';
}

function buildDirectory(posts) {
  const directory = { x: new Map(), threads: new Map(), youtube: new Map() };
  posts.forEach((post) => {
    if (post.sns_platform === 'x' || post.sns_platform === 'twitter') {
      const key = normalize(post.username);
      if (key) directory.x.set(key, (directory.x.get(key) || 0) + 1);
    } else if (post.sns_platform === 'threads') {
      const key = normalize(post.username);
      if (key) directory.threads.set(key, (directory.threads.get(key) || 0) + 1);
    } else if (post.sns_platform === 'youtube' && post.channel_id) {
      directory.youtube.set(post.channel_id, (directory.youtube.get(post.channel_id) || 0) + 1);
    }
  });
  return directory;
}

async function investigate(target, browser, directory) {
  const previous = cache[target.handle];
  if (previous && !args.has('--reparse')) return previous;
  const result = { handle: target.handle, threads_posts: target.count, pages: 0, bio_links: [], aggregator: '', aggregator_links: [], accounts: [], matched: [] };
  if (!args.has('--reparse')) await politeWait();
  const html = fetchThreadsProfile(target.handle);
  result.pages += 1;
  result.bio_links = html ? extractBioLinks(html, target.handle) : [];
  let urls = [...result.bio_links];
  const aggregator = result.bio_links.find((u) => { try { return AGGREGATOR_RE.test(new URL(u).hostname); } catch { return false; } });
  if (aggregator && previous?.aggregator === aggregator) {
    // 이미 렌더한 링크 모음은 다시 요청하지 않는다(상한). 그때 모은 링크를 쓴다.
    result.aggregator = aggregator;
    result.aggregator_links = previous.aggregator_links || [];
    result.aggregator_reused = true;
    urls = urls.concat(result.aggregator_links);
    result.pages += 1;
  } else if (aggregator && result.pages < MAX_PAGES_PER_TARGET) {
    await politeWait();
    result.aggregator = aggregator;
    result.aggregator_links = await renderAggregator(browser, aggregator);
    urls = urls.concat(result.aggregator_links);
    result.pages += 1;
  }
  result.accounts = accountsFromUrls(urls).filter((a) => !(a.platform === 'threads' && a.key === target.handle));
  for (const account of result.accounts) {
    if (account.platform === 'youtube_handle') {
      const channelId = await resolveYoutubeHandle(account.key);
      if (channelId && directory.youtube.has(channelId)) {
        result.matched.push({ platform: 'youtube', key: channelId, posts: directory.youtube.get(channelId), via: account.url });
      }
    } else if (account.platform === 'youtube' && directory.youtube.has(account.key)) {
      result.matched.push({ platform: 'youtube', key: account.key, posts: directory.youtube.get(account.key), via: account.url });
    } else if (account.platform === 'x' && directory.x.has(account.key)) {
      result.matched.push({ platform: 'x', key: account.key, posts: directory.x.get(account.key), via: account.url });
    } else if (account.platform === 'threads' && directory.threads.has(account.key)) {
      result.matched.push({ platform: 'threads', key: account.key, posts: directory.threads.get(account.key), via: account.url });
    }
  }
  cache[target.handle] = result;
  saveCache();
  return result;
}

async function applyLinks(results, targets) {
  const byHandle = new Map(targets.map((t) => [t.handle, t]));
  const outcomes = [];
  for (const result of results) {
    if (!result.matched.length) continue;
    const target = byHandle.get(result.handle);
    const body = {
      creator_id: target?.creatorId || undefined,
      name: result.handle,
      accounts: [{ platform: 'threads', key: result.handle }, ...result.matched.map((m) => ({ platform: m.platform, key: m.key }))],
      source: 'self_declared',
    };
    const { status, data } = await requestJson('POST', `${BASE_URL}/api/save-creator-links`, body);
    outcomes.push({ handle: result.handle, status, creator_id: data.creator_id, added: data.added, message: data.message });
  }
  return outcomes;
}

const posts = await loadPosts();
const targets = computeTargets(posts);
const directory = buildDirectory(posts);
const pilot = [targets.find((t) => t.handle === PILOT_FIXED), ...targets.filter((t) => t.handle !== PILOT_FIXED)]
  .filter(Boolean).slice(0, PILOT_SIZE);
const chosen = args.has('--all') ? targets : pilot;
console.log(`대상 ${targets.length}명 · 이번 실행 ${chosen.length}명: ${chosen.map((t) => `${t.handle}(${t.count})`).join(', ')}`);

const runnerPath = path.join(process.env.USERPROFILE || os.homedir(), '.claude', 'skills', '_shared', 'hidden-browser-verify-runner.mjs');
const { launchHeadlessChromium } = await import(pathToFileURL(runnerPath).href);
const browser = await launchHeadlessChromium();
const results = [];
try {
  for (const target of chosen) {
    const result = await investigate(target, browser, directory);
    results.push(result);
    console.log(`- ${result.handle}: 페이지 ${result.pages} · 소개 링크 ${result.bio_links.length} · 링크모음 ${result.aggregator ? 'O' : '-'} · 계정 ${result.accounts.length} · 통합본 일치 ${result.matched.length} ${result.matched.map((m) => `${m.platform}:${m.key}(${m.posts})`).join(' ')}`);
  }
} finally {
  await browser.close();
}

const pilotResults = results.filter((r) => pilot.some((p) => p.handle === r.handle));
const hits = pilotResults.filter((r) => r.matched.length > 0).length;
const pagesTotal = results.reduce((sum, r) => sum + r.pages, 0);
const gatePassed = hits >= 3;
console.log(`\n게이트: 파일럿 ${pilotResults.length}명 중 ${hits}명 적중 (기준 3명) → ${gatePassed ? '통과' : '미달'}`);
console.log(`조회 페이지 ${pagesTotal} (상한 ${chosen.length * MAX_PAGES_PER_TARGET}) · 이번 실행 요청 ${requestCount}`);

let applied = [];
if (args.has('--apply')) {
  if (!gatePassed) {
    console.log('게이트 미달이라 저장하지 않는다(병행 세션 결론 — 자동보강 기각 — 을 따른다).');
  } else {
    applied = await applyLinks(results, targets);
    applied.forEach((o) => console.log(`  저장 ${o.handle}: ${o.status} ${o.creator_id || ''} ${o.message || `+${o.added}`}`));
  }
}
fs.writeFileSync(RESULT_LOG, JSON.stringify({
  generated_at: new Date().toISOString(), targets: targets.length, chosen: chosen.map((t) => t.handle),
  pilot: pilot.map((t) => t.handle), hits, gate_passed: gatePassed, pages_total: pagesTotal, results, applied,
}, null, 2), 'utf8');
console.log(`결과: ${RESULT_LOG}`);
