/**
 * 뷰어 API 를 Node 에서 읽는 작은 클라이언트.
 *
 * 왜 fetch 를 안 쓰나: 목록 응답(2,880건)에서 Node 24 의 undici 파서가
 * `assert(!this.paused)` 로 죽는다. 브라우저 안에서 부를 때는 문제가 없어
 * 검증 스크립트마다 다르게 보였다. 표준 http 로 받으면 재현되지 않는다.
 *
 * 계획: _docs/20260909_01 (W2-3·W3-4 측정 스크립트)
 */
import http from 'node:http';

export function request(urlString, headers = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlString);
    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: 'GET',
        headers,
      },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => resolve({
          status: res.statusCode,
          headers: res.headers,
          body: Buffer.concat(chunks).toString('utf8'),
        }));
      }
    );
    req.on('error', reject);
    req.end();
  });
}

export async function getJson(urlString, headers) {
  const res = await request(urlString, headers);
  return { ...res, json: res.body ? JSON.parse(res.body) : null };
}
