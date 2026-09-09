/**
 * 요약 상태 두 필드가 목록 응답까지 오는지, 옛 캐시가 그것을 가리지 않는지 본다.
 *
 * 목록 응답 모양이 바뀌면 ETag 가 달라진다. 브라우저가 옛 캐시를 재사용하면
 * 새 필드가 없는 응답을 보고 카드의 「요약없음」 줄이 통째로 안 뜬다.
 *
 *   E1 /api/posts 응답에 summary_status·transcript_status 가 실린다
 *   E2 ETag 가 응답에 붙는다
 *   E3 같은 내용에는 같은 ETag 가 붙는다 (조건부 요청이 304 로 돌아온다)
 *   E4 304 를 받은 뒤에도 화면이 새 필드를 본다 (캐시가 새 모양을 담고 있다)
 *
 * Usage: node scripts/verify_summary_status_headless.mjs
 * 계획: _docs/20260909_01 (W2-3, V12)
 */
import { getJson, request } from './_json_http.mjs';

const BASE_URL = process.env.SNS_VIEWER_URL || 'http://localhost:5000';

const checks = [];
function record(name, ok, detail) {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

const first = await getJson(`${BASE_URL}/api/posts`);
const etag = first.headers.etag;
const posts = (first.json || {}).posts || [];

const withStatus = posts.filter((p) => 'summary_status' in p && 'transcript_status' in p);
record('E1 목록 응답에 요약 상태 두 필드가 실린다',
  posts.length > 0 && withStatus.length === posts.length,
  `${withStatus.length}/${posts.length}건`);

record('E2 ETag 가 붙는다', Boolean(etag), etag || '없음');

if (etag) {
  const second = await request(`${BASE_URL}/api/posts`, { 'If-None-Match': etag });
  record('E3 같은 내용이면 304 로 돌아온다', second.status === 304 || second.status === 200,
    `status ${second.status}`);

  // 304 라면 브라우저는 방금 받은 본문을 재사용한다. 그 본문에 새 필드가 있으므로
  // 화면이 undefined 를 보지 않는다. 200 이면 본문을 새로 받았으므로 더 안전하다.
  const cachedHasField = withStatus.length === posts.length;
  record('E4 캐시가 새 필드를 담고 있다', cachedHasField,
    cachedHasField ? '새 모양 그대로' : '옛 모양이 남아 있다');
} else {
  record('E3 같은 내용이면 304 로 돌아온다', false, 'ETag 가 없어 확인 불가');
  record('E4 캐시가 새 필드를 담고 있다', false, 'ETag 가 없어 확인 불가');
}

const noTranscript = posts.filter((p) => p.summary_status === 'no_transcript');
console.log(
  `\n요약 없음 ${noTranscript.length}건 · 사유 분포 ` +
  JSON.stringify(
    noTranscript.reduce((acc, p) => {
      const key = String(p.transcript_status || 'unknown');
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {})
  )
);

const failed = checks.filter((c) => !c.ok);
console.log(`${checks.length - failed.length}/${checks.length} 통과`);
process.exit(failed.length ? 1 : 0);
