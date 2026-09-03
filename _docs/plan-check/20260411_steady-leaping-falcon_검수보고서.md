---
title: steady-leaping-falcon plan 검수보고서
created: 2026-04-11
session_id: 019d7bfe-fa68-7a40-945f-3d98f44280e7
plan: C:/Users/ahnbu/.claude/plans/steady-leaping-falcon.md
reviewer: Codex (gpt-5.4) 실코드·실데이터 검증
---

# Plan 검수보고서: steady-leaping-falcon

## 종합 판정

**목적 달성 가능성은 중간이다.**

`web_viewer/script.js`의 핵심 버그 진단은 맞아서, `applyAutoTags`를 `resolvePostUrl(post)`로 바꾸면 "Tag 일괄 업데이트 버튼이 돌긴 도는데 태그가 안 보이는" 현재 증상은 높은 확률로 해결된다.

다만 plan은 **기존 오염 태그 복구 범위를 과소진단**했고, **Threads 복구 휴리스틱이 현재 데이터 1건을 놓치며**, **실제 코드에 남아 있는 다른 URL fallback/반환 타입 리스크를 과소평가**한다. 그대로 실행하면 "앞으로 새로 붙는 태그"는 고쳐도 "이미 저장된 상당수 Threads 태그"는 계속 안 보일 수 있다.

---

## 크리티컬 검수 결과

### 1. 핵심 진단은 맞다: `applyAutoTags`만 레거시 키를 쓰고 있다

- `web_viewer/script.js:343` — `const url = post.post_url || post.source_url || post.code;`
- `web_viewer/script.js:514-522` — `resolvePostUrl(post)`는 `post.url` 우선, Threads는 `@user/post/code` 조합, 마지막에만 `post.post_url || post.source_url`
- `web_viewer/script.js:590` — 카드 렌더는 `const postUrl = resolvePostUrl(post);`
- `web_viewer/script.js:893-1004` — `renderTags(..., postUrl)`가 렌더 키로 `postUrl`을 사용

즉 plan이 지적한 "저장 키와 조회 키 네임스페이스 불일치"는 현재 코드와 일치한다.

---

### 2. `undefined` cleanup 시나리오는 현재 코드와 일치한다

- `web_viewer/script.js:48-51`
  - `if (postTags['undefined']) { ... delete postTags['undefined']; localStorage.setItem(...) }`
- `web_viewer/data.js`에는 `post_url`/`source_url`가 존재하지 않는다.
  - `rg -n 'post_url|source_url' web_viewer/data.js` 결과 없음
- 현재 `web_viewer/data.js`의 모든 포스트는 해석 가능한 URL을 가진다.
  - 정적 검증 결과 `missingUrl = 0 / 975`

따라서 LinkedIn/X 포스트에서 `applyAutoTags`가 `undefined` 키를 만드는 흐름은 성립한다.

---

### 3. plan의 "기존 오염 데이터 복구"는 실제 손상 범위를 다 못 덮는다

실제 저장 파일 `web_viewer/sns_tags.json`을 보면 손상 패턴이 plan 설명보다 넓다.

- 총 키: `1101`
- `undefined` 키: `1`
- `code-only` 키: `660`
- `https://www.threads.net/t/<code>` 키: `167`
- 현재 `data.js` URL과 정확히 일치하는 키: `30`

즉 현재 손상은 단순히 `undefined`와 `code-only`만이 아니다. `threads.net/t/<code>` 형태의 **또 다른 Threads 레거시 URL 네임스페이스**가 이미 많이 쌓여 있다.

plan은 `code-only` Threads 키만 full URL로 옮기고 `/t/<code>` 키는 다루지 않는다. 이 상태로는 기존 Threads 태그의 상당수가 계속 렌더되지 않는다.

관련 근거:
- `server.py:19-27` — 서버는 `web_viewer/sns_tags.json`을 그대로 읽는다
- `server.py:32-45` — 서버는 `web_viewer/sns_tags.json`을 그대로 다시 쓴다

즉 `/t/<code>` 키 omission은 문서상의 우려가 아니라 **실제 영구화 surface에 남아 있는 손상**이다.

---

### 4. Threads code 휴리스틱 `/^[A-Za-z0-9_-]{5,30}$/` 는 현재 데이터 1건을 놓친다

정적 검증 결과:

- 현재 Threads 포스트: `659`
- 위 정규식과 매칭되는 Threads `platform_id/code`: `658`
- 길이 30 초과로 누락되는 실제 코드: `DUniriOjLVh0U-UEGs4wVrUY7Oo12Wff6wcKhA0` (길이 39)

즉 plan의 복구 블록은 **현재 데이터에서도 1건을 복구하지 못한다.**

추가로 이 정규식은 Threads만 매칭하는 패턴이 아니다.

- LinkedIn `platform_id` 237건 전부 매칭
- X `platform_id` 79건 전부 매칭

다만 plan이 `allPosts.find(... platform.includes('thread') && (platform_id === key || code === key))` 조건을 함께 쓰므로 **오탐 확률은 낮다.** 문제는 오탐보다 **누락**과 **분류 로직이 불필요하게 취약한 휴리스틱 의존**이다.

---

### 5. 복구 블록 삽입 위치 판단은 맞다

- `web_viewer/script.js:458` — `allPosts = ...`
- `web_viewer/script.js:461-469` — `allPosts` 전처리
- `web_viewer/script.js:471-472` — `await applyAutoTags(allPosts, true);`

따라서 plan이 말한 "471-472행 사이"는 현재 파일 기준으로 **`allPosts` 로드 이후이면서 `applyAutoTags(..., true)` 이전**이 맞다.

---

### 6. plan이 "핸들러 자체는 정상"이라고 단정한 부분은 과감하다

현재 코드에는 plan이 무시한 실제 edge case가 있다.

- `web_viewer/script.js:330` — `if (allRules.size === 0) return 0;`
- `web_viewer/script.js:1462` — `const { count, ruleCount, stats } = await applyAutoTags(allPosts, false, ...)`

즉 자동 태그 규칙이 0개이면 버튼 핸들러는 객체가 아니라 숫자 `0`을 구조분해하게 된다. 이 경로는 현재 사용자 증상의 주원인은 아니어도, plan이 "서브에이전트 오탐"으로 치부한 건 부정확하다.

또한 plan의 "렌더·필터·수동 편집 경로는 전부 resolvePostUrl" 서술도 완전히 맞지는 않는다.

- `web_viewer/script.js:498` — `const postUrl = resolvePostUrl(post) || post.code;`

현재 데이터에서는 `missingUrl = 0`이라 영향이 작지만, namespace 정리 관점에서는 여전히 fallback 잔존 경로가 있다.

---

## 트레이드오프

### 얻는 것

- `script.js:343`만 바로잡아도 신규 자동 태그 저장 키가 렌더 키와 일치한다.
- 현재 `data.js` 975건 모두 URL이 있어, 앞으로 생성되는 태그는 안정적으로 `resolvePostUrl(post)` 기준으로 정규화된다.
- 삽입 위치도 적절해 silent 자동 태그 이전에 복구를 수행할 수 있다.

### 잃는 것

- plan의 복구 블록은 생각보다 많은 책임을 진다. `code-only` 복구, silent apply 순서, 서버 재동기화까지 한 번에 묶으면서 디버깅 표면이 넓어진다.
- 그런데도 `/t/<code>` legacy URL, 길이 39 Threads code 1건, stale tag key 다수는 그대로 남는다.
- 결과적으로 "복구 로직이 있는데도 복구가 덜 된 상태"가 되어 사용자가 다시 혼란을 겪을 수 있다.

---

## 과최적화 / 설계 냄새

현재 데이터에서는 모든 포스트가 이미 canonical URL을 갖는다. 이 상황에서 길이 제한 정규식으로 "Threads code처럼 보이는 값"을 추정하는 것은 과최적화에 가깝다.

더 단순하고 강한 방식은 `allPosts`에서 직접 canonical map을 만드는 것이다.

- URL 그대로면 유지
- `threads.net/t/<code>`면 code 추출 후 canonical URL로 이동
- `code-only`면 canonical URL map에 있으면 이동
- 그 외 키는 보존

이 방식은 휴리스틱보다 단순하고, 현재 plan이 놓친 `/t/<code>`까지 한 번에 정리할 수 있다.

---

## 권장 수정안

plan의 핵심 fix는 유지하되, 복구 로직은 아래처럼 바꾸는 편이 낫다.

1. `applyAutoTags`는 그대로 `const url = resolvePostUrl(post); if (!url) return;` 로 교체
2. `fetchData` 복구 블록은 regex heuristic 대신 `allPosts` 기반 canonical map 사용
3. 복구 대상은 최소 3종
   - `undefined`
   - `code-only`
   - `https://www.threads.net/t/<code>`
4. `applyAutoTags`의 `allRules.size === 0` 반환값은 객체로 통일
   - 예: `return { count: 0, ruleCount: 0, stats: { hits: 0, skips: 0, distinctTags: existingTags.size } };`

---

## 항목별 확증

### `web_viewer/script.js:343` applyAutoTags URL 키 해석

확증.

- 실제 코드: `web_viewer/script.js:343`
- plan 설명과 일치: `post.post_url || post.source_url || post.code`

### `web_viewer/script.js:514` resolvePostUrl 정의

확증.

- 실제 코드: `web_viewer/script.js:515-522`
- `post.url` 우선이 맞다.

### `web_viewer/script.js:48-51` undefined cleanup 로직

확증.

- 실제 코드: `web_viewer/script.js:48-51`
- plan 시나리오와 일치한다.

### 복구 블록 삽입 위치 `471-472` 사이

확증.

- `allPosts` 로드 이후이고
- `applyAutoTags(allPosts, true)` 직전이다.

### Threads code 휴리스틱 충돌 위험

부분 확증.

- **누락 위험은 확정**: 현재 데이터 1건이 길이 39라 정규식에서 빠진다.
- **LinkedIn/X 일부와 패턴 수준 충돌은 확정**: 두 플랫폼의 19자리 `platform_id`도 정규식에 걸린다.
- **실제 오이동 가능성은 낮음**: plan의 `platform.includes('thread') && equality match` 조건이 있어 단순 패턴 충돌만으로 잘못 옮겨질 가능성은 낮다.
- 결론: "오탐이 매우 크다"까지는 아님. 하지만 **현재 데이터도 1건 놓치므로 좋은 휴리스틱은 아니다.**

---

## 검증 불가

- 현재 브라우저 각 탭의 실제 `localStorage.sns_tags` 상태는 검증 불가
- 사용자가 본 콘솔 메시지 발생 빈도와 실제 UI 재현은 브라우저 런타임 실행 없이 완전 확증 불가
- `web_viewer/sns_tags.json`에 남은 key 중 현재 `data.js`에 없는 1041건이 "단순 stale data"인지 "별도 namespace drift"인지 전부는 검증 불가
