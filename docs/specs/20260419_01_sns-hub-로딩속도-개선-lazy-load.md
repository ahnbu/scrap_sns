---
title: SNS 허브 로딩 속도 개선 (메타 인라인 + 본문 Lazy Load)
created: 2026-04-19 09:31

session_id: 44cc41e7-94dc-4651-a9e9-6817af8a8521
session_path: C:/Users/ahnbu/.claude/projects/D--vibe-coding-scrap-sns/44cc41e7-94dc-4651-a9e9-6817af8a8521.jsonl
updated_sessions:
  - 44cc41e7-94dc-4651-a9e9-6817af8a8521

ai: claude
---

# SNS 허브 로딩 속도 개선 (메타 인라인 + 본문 Lazy Load)

## 목적

현재 SNS 허브(루트 `index.html` + `web_viewer/data.js` + `server.py`)의 초기 로딩이 느리다. 참조 프로젝트 `session-dashboard`가 동일한 "브라우저에 전체 데이터를 퍼붓는 구조"를 **메타 lazy + 본문 lazy + 서버 검색 + hover prefetch + 메모리 캐시**로 해결해 10초 → 1초 수준으로 개선한 선례가 있다. 이 패턴을 SNS 허브에 이식해 체감 로딩과 상호작용 속도를 획기적으로 개선한다.

- 1차 병목: `web_viewer/data.js`(3.0MB, `const snsFeedData = {metadata, posts:[1079]}`)를 **동기 `<script>`로 파싱**하고, 같은 데이터를 `/api/latest-data`(3.2MB)로 **중복 수신**.
- 2차 병목: 1,079 카드 + 수백 장의 `<img src>`를 **한 번에** masonry DOM에 삽입. `loading="lazy"`·`IntersectionObserver` 전무.
- 3차 병목: 검색·필터·정렬·리사이즈·태그 토글 등 **모든 UI 이벤트가 `renderPosts()` 전체 리빌드**. 검색은 키 입력마다 1,079건 × `full_text.toLowerCase().includes()` 전수 스캔.
- 4차 병목: `/api/latest-data`에 gzip·ETag·Cache-Control 없음. 이미지 242MB 디렉토리도 정적 캐시 미설정.

목표: **초기 첫 페인트 1초 이내**, 검색/필터 입력당 CPU 수 ms 이내, UX 회귀 없음.

## 요구사항

- **R1.** 사용자가 `npm run view`로 허브를 켰을 때, 피드 첫 화면(카드 목록)이 **1초 이내** 화면에 나타난다.
- **R2.** 현재의 핵심 UX를 그대로 유지한다 — masonry 그리드, 플랫폼 필터, 정렬, 검색, 수동 태그·즐겨찾기·숨김·접기·할일, 자동 태그 규칙, 스크래핑 실행 버튼, 이미지 확대 모달.
- **R3.** 스크롤 시 추가 요청에 의한 멈칫 없이 부드럽게 이어지도록 한다(카드·이미지 lazy 삽입).
- **R4.** 검색은 현 체감(실시간)에 준하는 반응을 유지하되, 엔진을 클라이언트 전수 스캔 → **서버 측 필터**로 전환한다. 검색 범위에 `full_text`·`display_name`·`username`을 포함한다.
  - **R4.1.** 검색 입력 이벤트는 **200ms 디바운스**를 적용하고, 타이핑 도중 새 입력이 오면 **진행 중이던 이전 요청을 AbortController로 취소**한 뒤 최신 쿼리만 서버로 보낸다. 연속 타이핑 중 중간 렌더는 발생하지 않는다.
  - **R4.2.** 서버는 `/api/search` 요청마다 전체 post에 대해 `full_text`·`display_name`·`username`을 소문자로 다시 변환하지 않는다. `_load_latest_posts()`가 최신 `total_full_*.json`을 로드할 때 post별 **`searchable` 문자열(사전계산 lowercased concat)**을 함께 생성해 메모리에 유지하고, 검색은 이 사전계산 값에 대한 `str.find()`로 수행한다.
- **R5.** 플랫폼 필터(threads/linkedin/twitter/all)와 정렬은 **서버 측 필터**로 처리해 클라이언트가 전 데이터를 훑지 않는다.
- **R6.** 자동 태그 규칙(`sns_auto_tag_rules`)의 "일괄 반영" 기능은 **규칙이 생성/수정/삭제되는 시점에 한정**해 동작하고, 초기 로딩 경로에서는 빠진다. 본문이 서버에만 있어도 정합성이 유지되어야 한다.
- **R7.** `web_viewer/data.js`(전량 인라인)를 완전 제거하고, 서버 API로만 데이터를 수신한다. 오프라인 뷰어 유스케이스는 포기한다.
- **R8.** 이미지는 뷰포트 진입 시점에만 로드한다(`loading="lazy"` + `decoding="async"` 기본, 필요 시 `IntersectionObserver` 기반 수동 lazy).
- **R9.** 카드 본문 중 **상세 정보**(전체 `full_text`·전체 `media`·전체 `local_images`)는 lazy 로드한다. 첫 페인트에 필요한 것은 메타 + 썸네일 1장 + `full_text_preview`(~200자)만이다.
- **R10.** 스크래핑 후 `total_full_*.json` 갱신 시, 브라우저가 새 데이터를 수동 새로고침으로 반영할 수 있어야 하고, 서버 재시작 없이도 곧바로 새 파일을 서빙해야 한다.

## 성공 기준

- **SC1.** 로컬 서버 기동 상태에서 `index.html`을 열었을 때 피드 첫 화면 표시까지 **1초 이내**(localhost, 2026-04 기준 데이터 1,079건).
- **SC2.** 검색창에 타이핑 시 **200ms 디바운스 + 서버 응답 포함 400ms 이내** 결과 갱신. 또한 **4타 연속 타이핑 시 중간 렌더 0회, 최종 결과만 1회 렌더**되고, 이전 in-flight 요청은 `AbortController`로 취소되어 응답이 뒤섞이지 않는다.
- **SC3.** 스크롤 중 멈칫 없이 이어지며, 한 번에 DOM에 삽입되는 카드는 **최초 N장(plan에서 튜닝)**으로 제한된다.
- **SC4.** 뷰포트 밖 이미지는 네트워크에 요청되지 않는다(DevTools Network 탭 확인).
- **SC5.** `/api/posts`의 메타 응답이 **gzip 후 300KB 이하**로 축소되고 `ETag`/`Cache-Control` 헤더가 붙는다.
- **SC6.** 플랫폼 필터·정렬·페이지 전환 시, 캐시된 쿼리는 즉시 렌더, 신규 쿼리는 1회 fetch 후 캐시.
- **SC7.** 자동 태그 규칙을 설정에서 생성/수정/삭제하면 전체 post에 일괄 반영되고, 그 외 경로(초기 로드·검색·정렬)에는 규칙 매칭 비용이 0이다.
- **SC8.** 기존 기능(수동 태그, 즐겨찾기, 숨김, 접기, 할일, 이미지 확대 모달, 스크래핑 실행 버튼, 태그 내보내기/가져오기)이 모두 동일하게 동작.

## 제약 조건

- **C1.** 데이터 소스는 기존 `output_total/total_full_YYYYMMDD.json` 그대로. `utils/post_schema.py`의 `STANDARD_FIELD_ORDER`·`REQUIRED_FIELDS` 계약을 깨지 않는다.
- **C2.** 서버는 기존 Flask + `flask_cors`(`server.py`) 유지. 새 프레임워크 도입 금지.
- **C3.** 실행 스택은 `npm run view → sns_hub.vbs → python server.py + 브라우저 오픈` 유지. 단, 현재 `start "" index.html`이 `file://`로 여는 동작은 **HTTP(`http://localhost:5000/`)로 전환**한다(오프라인 포기와 일관된 변경).
- **C4.** `sns_tags.json`·localStorage 태그 키는 `post.url`(canonical threads.com 포함) 기반. 이 계약을 유지해야 기존 태그가 보존된다.
- **C5.** 이미지 디렉토리 `web_viewer/images/`(≈242MB)는 그대로 유지. 재인코딩·썸네일 자동 생성은 범위 외.
- **C6.** 3개 플랫폼(threads/linkedin/twitter) + 플랫폼별 스크래퍼는 범위 외. 변경 대상은 **데이터 전달·뷰어 렌더·서버 API**에 한정.
- **C7.** 테스트는 기존 `tests/` 트리 유지. 신규 API는 `tests/integration/`에 계약·보안 테스트 추가.
- **C8.** `/api/run-scrap`의 동기 동작(`subprocess.wait`)은 본 SPEC 범위 외.

## 경계선

### [OK] 허용 범위 (확정)

- `web_viewer/data.js` **완전 제거**(파일 삭제 + `<script>` 태그 제거). `utils/build_data_js.py`는 제거하거나 no-op으로 둔다.
- `index.html`의 `<script>` 태그에 `defer` 적용.
- `sns_hub.vbs` 수정: `start "" index.html` → `start "" http://localhost:5000/`.
- `server.py`에 신규 엔드포인트 추가:
  - `GET /api/posts` — 메타 전용 전체 목록. 필드: `sequence_id`, `platform_id`, `sns_platform`, `code`, `username`, `display_name`, `url`, `canonical_url`, `created_at`, `date`, `source`, `full_text_preview`(≤200자), `full_text_length`, `media_count`, `local_images_count`, `thumbnail`, `is_detail_collected`, `is_merged_thread`.
  - `GET /api/post/<sequence_id>` — 단일 post 전체(`full_text` 원문, `media[]`, `local_images[]` 등).
  - `GET /api/search?q=&platform=&sort=&limit=&offset=` — 서버 측 검색/필터/정렬. 응답은 메타 구조.
  - `POST /api/auto-tag/apply` — 자동 태그 규칙을 전체 post에 일괄 적용(규칙 CRUD 시점에만 호출).
- 모든 신규 API에 **gzip 압축** + **ETag/Last-Modified/Cache-Control** 헤더.
- `server.py`에 **메모리 캐시**(최신 `total_full_*.json` 파싱 결과 프로세스 내 유지, mtime 기반 무효화).
- `server.py`의 `_load_latest_posts()`에 **검색 인덱스 프리워밍** — 로드 시점에 post별 `searchable` 사전계산 문자열을 붙여 보관(E3).
- `web_viewer/script.js` 검색 입력 핸들러에 **200ms 디바운스 + AbortController**(E1). 본 SPEC의 R4.1과 대응.
- 뷰어(`web_viewer/script.js`)에 `IntersectionObserver`로 카드 단계 삽입.
- `<img loading="lazy" decoding="async">` 기본 적용. `script.js:1094`의 `imgEl.src` → `dataset.src` + lazy 패턴.
- 서버에서 `canonical_url`(threads.com 정규화) 사전 계산 → 클라이언트 `normalizeThreadsUrl` 런타임 호출 제거.
- 본문·미디어 메모리 캐시(`Map<sequence_id, fullPost>`), hover prefetch(`mouseenter`).

### [ASK] SPEC 범위 내 미결

(없음 — A1·A2·A3은 사용자 확정으로 모두 [OK]로 이동됨. 아래 "확정된 A-항목" 참조)

### 확정된 A-항목 (2026-04-19 확정)

- **A1 → (a) 전체 메타 1회 응답**: `GET /api/posts`는 모든 post 메타를 단일 응답으로 반환. gzip 후 ≤80KB 예상. 5,000건 돌파 시 페이징 재검토.
- **A2 → (a) 저장 버튼 = 자동 호출**: 자동 태그 규칙 편집 UI의 "저장" 클릭 즉시 `POST /api/auto-tag/apply` 호출 + 진행 인디케이터 표시 후 결과 반영.
- **A3 → (a) Python 메모리 필터**: `_load_latest_posts()` 프리워밍 `_searchable` 문자열에 대해 `q.lower() in post["_searchable"]` 루프. SQLite FTS5 도입 금지(YAGNI).

### [NO] 금지 사항 (확정)

- 오프라인 뷰어 유스케이스 지원(서버 없이 `index.html` 열기). `web_viewer/data.js` 폴백 유지 금지.
- 새 서버 프레임워크(Express, Fastify, FastAPI 등) 도입.
- `utils/post_schema.py`의 `STANDARD_FIELD_ORDER`·`REQUIRED_FIELDS` 변경 또는 `total_full_*.json` 저장 포맷 변경.
- `sns_tags.json` 키 체계를 URL 기반에서 ID 기반으로 변경(기존 태그 파괴 위험).
- 이미지 썸네일 자동 생성·리사이즈·WebP 재인코딩. 현행 `wsrv.nl` 프록시 + `local_images` 우선 정책 유지.
- 스크래퍼 및 `/api/run-scrap` 동작 변경.
- 자동 태그를 초기 로드·검색·정렬 경로에서 **런타임 전수 스캔**으로 수행하는 방식(R6 위반).

## 결정안

### D1. 데이터 전달 구조 전환

- **Before**: `web_viewer/data.js`가 `snsFeedData.posts[1079]`를 전량 인라인(3.0MB 동기 파싱). `/api/latest-data`가 동일 데이터 3.2MB를 중복 반환.
- **After**: `web_viewer/data.js` 제거. 뷰어는 초기에 `GET /api/posts`로 **메타만** 수신(gzip ≤80KB 예상). 본문·전체 media는 `GET /api/post/<id>`로 뷰포트 진입 또는 상세 모달 시 lazy 로드.
- `/api/latest-data`는 deprecate(호환용으로 `/api/posts`에 리다이렉트하거나 제거 — plan에서 결정).

### D2. 서버 엔드포인트(server.py 추가)

```
GET  /api/posts?platform=&sort=&limit=&offset=    # 메타 전용
GET  /api/post/<sequence_id>                      # 단일 전체
GET  /api/search?q=&platform=&sort=&limit=&offset= # 서버 검색/필터/정렬
POST /api/auto-tag/apply                          # 규칙 CRUD 시 일괄 반영
```

- 모두 gzip + `ETag`(파일 mtime+size 해시) + `Cache-Control: private, max-age=0, must-revalidate`.
- 공용 헬퍼: `_load_latest_posts()` — 최신 `total_full_*.json` 메모리 캐시, mtime invalidation.
- 기존 `/api/get-tags`·`/api/save-tags`·`/api/status`·`/api/run-scrap`·정적 라우트는 유지.

### D3. 클라이언트 동작 (web_viewer/script.js)

1. `DOMContentLoaded` → 병렬 `fetch('/api/posts')` + `fetch('/api/get-tags')`.
2. 메타 도착 → `allPosts` 채움 → `renderPosts()`. **초기 N장만** DOM 삽입. `IntersectionObserver` sentinel로 스크롤 시 추가 삽입.
3. 카드 `<img>`는 `loading="lazy" decoding="async"`. 본문 preview는 메타의 `full_text_preview`로 렌더.
4. 카드 뷰포트 진입 또는 상세 모달 오픈 시 `/api/post/<id>` fetch → 캐시 저장 → 본문/전체 미디어 보강 렌더.
5. 검색·플랫폼 필터·정렬은 `/api/search`에 위임. 200ms 디바운스. 결과는 메타 목록(기존 렌더 파이프라인 재사용).
6. 카드 `mouseenter` prefetch — `/api/post/<id>` 선행 호출.
7. `migrateLegacyTagKeys` 유지. 서버가 `canonical_url`을 사전 계산해 내려주므로 `normalizeThreadsUrl` 런타임 반복 호출은 **제거**.

### D4. 자동 태그 일괄 적용 분리 (R6 충족 핵심)

- 초기 로드·검색·정렬 경로에서 `applyAutoTags()` 호출 **제거**.
- 규칙 CRUD 저장 시: 클라이언트가 규칙 목록을 `POST /api/auto-tag/apply`에 보내면, 서버가 모든 post의 `full_text` 원문으로 매칭해 `{url: [auto_tags]}` 맵을 반환. 클라이언트는 기존 `postTags`와 머지 후 `localStorage`·서버(`/api/save-tags`)에 저장.
- 이후 렌더는 저장된 태그를 그대로 사용. 본문이 서버에만 있어도 매칭 정합성 문제가 없다.
- 규칙 없이 새 post가 유입될 때(스크래핑 후 재진입): 서버에서 `/api/posts` 응답에 현재 저장된 규칙에 대한 매칭을 포함해 내려주거나, 뷰어가 새 sequence_id에 대해서만 단발 `apply` 호출. plan에서 구체 방식 결정.

### D5. 썸네일 / 이미지

- 메타의 `thumbnail` 필드: `local_images[0]`가 있으면 그 경로, 없으면 `media[0]`의 원격 URL(LinkedIn `licdn.com`은 직접, 그 외는 `wsrv.nl` 프록시). 서버가 1회 결정해 메타에 포함.
- 전체 `media[]`·`local_images[]`는 본문 lazy에 포함.
- `<img>` 속성: `loading="lazy" decoding="async"`. `fetchpriority`는 필요 시 첫 페인트 카드에만.

### D7. 검색 동선 1순위 설계 (사용자 실사용 60% 대응)

- **E1 / R4.1 — 디바운스 + AbortController**: `script.js`의 검색 `input` 리스너를 현행 "즉시 `renderPosts()`"에서 "200ms 디바운스 + 마지막 쿼리만 fetch"로 교체. fetch는 `AbortController`로 감싸 타이핑 도중 이전 in-flight 요청을 취소. 서버 응답이 뒤섞여 구 결과가 최신 결과를 덮는 경쟁 조건 차단.
- **E3 / R4.2 — 서버 프리워밍 인덱스**: `_load_latest_posts()`가 JSON 로드 직후 각 post에 `"_searchable"`(lowercased `full_text + "\n" + display_name + "\n" + username`)을 주입. `/api/search`는 이 사전계산 문자열에 대해 `str.find()`만 수행. 요청당 1,079 × `lower()` 중복 비용 제거.
- **E2는 채택하지 않음**: 검색 전용 별도 렌더 경로/하이라이트/DOM key diff는 본 SPEC의 D3-2(초기 N장 + `IntersectionObserver` sentinel 단계 렌더)와 해결 영역이 겹친다. 검색 결과도 동일한 단계 렌더 파이프라인을 타도록 하면 추가 복잡도 없이 프레임 드랍이 해소된다. 하이라이트(`<mark>`)가 필요하면 plan 단계의 구현 상세로 처리한다.

### D6. 캐시 전략

- **클라이언트**: 메모리 `Map<sequence_id, fullPost>` + `Set<쿼리키>`(로드된 쿼리 표시). 새로고침 시 초기화.
- **서버**: `_load_latest_posts()`가 최신 `total_full_*.json`을 프로세스 메모리에 보관. mtime 변화 시 재로드. 응답에 `ETag` + `Last-Modified`로 304 활용.
- **재빌드 반영**: 사용자가 "스크래핑 실행" 후 페이지 새로고침 시 서버 ETag 갱신으로 자동 반영.

## 사실 확인

- **F1.** 루트 `index.html` 29,517B, 651줄. 인라인 `window.__*` 없음. `<script src="web_viewer/data.js">` + `<script src="web_viewer/script.js">` 순서(`index.html:648-649`), 둘 다 `defer`/`async` 없음.
- **F2.** `web_viewer/data.js` 3,082,338B(≈3.0MB). `const snsFeedData = { metadata, posts: [...] }` 구조(`data.js:1-11`). 항목 수 1,079(threads 753 / linkedin 261 / twitter 79). 필드별 바이트 비중: `full_text` 44.4%, `media` 20.4%, `local_images` 2.5%, 기타 32.7%.
- **F3.** `/api/latest-data`가 `output_total/total_full_20260418.json`(3,239,311B) 전체를 `jsonify`로 반환(`server.py:53-72`). gzip·ETag·페이지네이션 없음.
- **F4.** `script.js` 초기 체인: `fetchData()`(`:587-690`) → `allPosts.forEach` 날짜 파싱 1,079회 → `migrateLegacyTagKeys()`(`:417-584`) → `applyAutoTags(allPosts, true)`(`:325-414`, silent 모드에서 yield 없음) → `renderPosts()`(`:764-822`).
- **F5.** `renderPosts()`는 `masonryGrid.innerHTML = ''` 후 전체 카드 재생성. 페이지네이션·가상 스크롤·`IntersectionObserver` 모두 부재(grep 0건).
- **F6.** `<img>`에 `loading`·`decoding`·`fetchpriority`·`srcset` 속성 모두 부재(`script.js:1094-1117`).
- **F7.** 검색·필터·정렬이 매번 `renderPosts()` 전체 재실행. 검색 디바운스는 미적용(즉시).
- **F8.** `server.py`는 Flask + flask_cors, 포트 5000, 단일 스레드(`server.py:8-18, 208-212`). `static_folder=None`으로 기본 캐시 비활성.
- **F9.** `sns_hub.vbs`는 포트 5000 기존 프로세스 taskkill 후 `python server.py` hidden 기동 + `start "" index.html`로 **`file://` 경로**로 연다. 브라우저는 file://에서 JS 실행, `http://localhost:5000` API를 CORS로 호출.
- **F10.** `sns_tags.json`(≈126KB)은 `{url: [tags]}` 평탄 구조. localStorage 키 8개(`sns_sort_order`, `sns_favorites`, `sns_invisible_posts`, `sns_folded_posts`, `sns_tags`, `sns_tag_types`, `sns_todos`, `sns_auto_tag_rules`). `migrateLegacyTagKeys`가 매 초기 로드 경로에 포함(`script.js:669`).
- **F11.** session-dashboard는 동일 방향으로 이미 구현 완료(참조 SPEC·검수 문서 2건). HTML 285MB → 4.8MB. lazy load + 서버 검색 + hover prefetch + 메모리 캐시.
- **F12.** session-dashboard 오프라인 지원은 **포기**(C1·R8·R9: "로컬 서버 상시 기동 전제, 오프라인 HTML 단독 공유 유스케이스는 포기"). scrap_sns도 같은 선택.
- **F13.** 자동 태그 "전체 본문 매칭"의 정의: `sns_auto_tag_rules`(localStorage)에 사용자가 등록한 키워드 → 태그 매핑을 저장. `applyAutoTags()`가 각 post의 `full_text`(+display_name+username+platform)를 소문자 변환 후 `includes()`로 매칭해 자동 태그를 부여. 규칙 CRUD 시 변경된 결과를 전체 post에 반영하는 "일괄 반영" 기능이다(`script.js:325-414`).
- **F14.** 이미지 경로: 다운로더가 `web_viewer/images/<md5(url)>.<ext>`로 저장하고 `post.local_images`에 `"web_viewer/images/<hash>.<ext>"`를 넣음(`total_scrap.py:327-342`). `script.js:1046-1117`에서 `local_images[0]` 우선 → LinkedIn 직접 → 기타 `wsrv.nl` 프록시 순.
- **F15.** 테스트 트리: `tests/unit/test_web_viewer_auto_tagging.py` 등 뷰어 순수 함수 커버, `tests/integration/test_server_routes.py`가 정적 라우트 커버, `/api/latest-data`·`/api/get-tags`·`/api/save-tags`는 직접 통합 테스트 부재.

## 의사결정 로그

| 시점 | 결정 내용 | 근거 | 검토한 대안 |
|------|-----------|------|-------------|
| 오프라인 유스케이스 | 지원 포기 | 사용자 확정 — 서버 없이 `index.html`만 보는 수요 없음. session-dashboard도 같은 선택(F12) | 메타 전용 `data.js` 폴백 유지 |
| 데이터 인라인 vs lazy | 메타 lazy(`/api/posts`) + 본문 lazy(`/api/post/:id`) | 현 3.0MB 동기 파싱 + 3.2MB 중복 fetch 제거. session-dashboard 선례(F11) | 메타 인라인 HTML 주입 + 본문 lazy / 전량 인라인 유지 |
| 검색 엔진 | 서버 측 메모리 필터(Python str 연산) | 1,079건 규모에 SQLite FTS 과잉. session-dashboard도 LIKE로 충분 | SQLite FTS5 / DuckDB / 클라이언트 전수 스캔 유지 |
| 자동 태그 반영 방식 | 규칙 CRUD 시점에만 서버에서 일괄 계산(`POST /api/auto-tag/apply`) | 초기 로드·검색·정렬의 O(N×M) 스캔 제거. 본문 lazy 환경에서도 정합성 확보 | 초기 로드마다 스캔 유지 / 뷰포트 진입 카드만 매칭(R6 위배·누락) |
| 브라우저 진입 방식 | `file://` → `http://localhost:5000/` | 오프라인 포기와 일관. HTTP 캐시·gzip·ETag 이득 | file:// 유지 + CORS 의존 |
| 이미지 lazy | `loading="lazy" decoding="async"` 기본 + 필요 시 수동 IO | 브라우저 네이티브로 대부분 해결, 구현 최소 | IntersectionObserver만 사용 / 현행 유지 |
| canonical URL | 서버 사전 계산 → 메타에 포함 | 런타임 `normalizeThreadsUrl` 반복 호출 제거, 태그 키 정합성↑ | 클라이언트 계산 유지 / 빌드 타임 `data.js` 사전 계산 |
| 서버 프레임워크 | 기존 Flask 유지 | `server.py` 데코레이터 패턴 그대로 확장 가능 | Express / Fastify / FastAPI |
| 캐시 수명 | 클라이언트 메모리(세션 내), 서버 메모리(mtime 무효화) | IndexedDB 영속 캐시는 동기화 리스크. scrap_sns는 데이터 변동 빈도 낮음 | IndexedDB / localStorage 영속화 |
| `web_viewer/data.js` | 완전 제거 | 오프라인 포기 확정 후 유지 이유 소멸. 빌더(`utils/build_data_js.py`)도 제거 후보 | 메타 전용으로 축소 유지 |
| 검색 동선 격상 | E1(디바운스+Abort) + E3(서버 프리워밍) 채택, E2 미채택 | 사용패턴 60%가 검색. E1이 버벅임의 1차 원인 해소, E3은 투입 대비 안전 확보. E2는 D3-2 단계 렌더와 중복 | E1만 / E1+E2+E3 모두 채택 / 전부 plan 단계로 이연 |
| 검색 입력 이벤트 | 즉시 `renderPosts()` → 200ms 디바운스 + AbortController | 현재 4타 = 4 사이클의 원인. 디바운스 없이 서버 전환만 하면 네트워크 왕복이 4회 발생해 오히려 악화될 수 있음 | 300ms+ 디바운스 / 엔터 시 검색 / 디바운스만(Abort 미사용) |
| 서버 검색 인덱스 | 프리워밍 `_searchable` 문자열 | 요청당 1,079 × `lower()` 비용 제거. 데이터 확장에도 여유 | 요청 시 즉석 lower() / SQLite FTS5 / 인메모리 역인덱스 |
| A1 페이지네이션 | (a) 전체 메타 1회 응답 확정 | 1,079건 규모에 충분, 구현 최단. 클라 페이지 상태 관리 불필요 | (b) cursor/offset+limit 페이징 |
| A2 자동태그 트리거 | (a) 저장 버튼 = 자동 호출 확정 | "변경 = 즉시 반영" 직관적. 수십~수백 ms 블록은 인디케이터로 수용 | (b) 별도 "재적용" 버튼 (정합성 깨짐 리스크) |
| A3 검색 엔진 | (a) Python 메모리 필터 + 프리워밍 확정 | YAGNI. 현재 규모·변동 빈도에 FTS 오버스펙 | (b) SQLite FTS5 (스키마 신설·이중화 부담) |

## 부록: 연관 변경 파일

| 범주 | 파일 | 변경 요지 |
|------|------|-----------|
| 뷰어 엔트리 | `index.html` | `<script defer>` 적용, `data.js` 태그 제거 |
| 뷰어 로직 | `web_viewer/script.js` | `fetchData` 재작성, `IntersectionObserver` 기반 단계 렌더, 서버 검색 위임, 자동 태그 CRUD 경로 분리, 이미지 lazy 속성, canonical 계산 제거 |
| 서버 | `server.py` | `/api/posts`·`/api/post/<id>`·`/api/search`·`/api/auto-tag/apply` 추가, gzip/ETag, `_load_latest_posts()` 캐시 헬퍼 |
| 실행 래퍼 | `sns_hub.vbs` | `start "" index.html` → `start "" http://localhost:5000/`, 서버 헬스체크 대기 |
| 빌더 | `utils/build_data_js.py` | 제거 또는 no-op |
| 정적 리소스 | `web_viewer/data.js` | 삭제 |
| 테스트 | `tests/integration/test_posts_api.py`, `test_post_detail.py`, `test_search_api.py`, `test_auto_tag_apply.py`(신규) + 기존 `test_server_routes.py`/`test_api_security.py` 보완 |
| 문서 | `CLAUDE.md`, `docs/development.md`, `docs/crawling_logic.md` | 데이터 플로우(1단계 `build_data_js` 제거, API 전용) 반영 |

## 부록: 검색 최적화 후보 비교분석 (E1·E2·E3)

본 SPEC이 검색 동선을 1순위로 격상한 근거. 1,079건 규모, 사용 패턴 "최근 50건 보기 40% + 검색 60%" 전제.

### 후보 정의

- **E1. 디바운스 + AbortController**: 검색 입력을 200ms 디바운스로 묶고, 타이핑 중 이전 in-flight 요청을 취소. 현재 코드는 디바운스 없이 매 키 입력마다 `renderPosts()` 전체 재실행.
- **E2. 검색 전용 렌더 경로 + 하이라이트**: 검색 모드에서 masonry 렌더 패턴을 분리. 결과 수 조건부 렌더, `<mark>` 하이라이트, DOM key diff로 재사용.
- **E3. 서버 프리워밍 인덱스**: `_load_latest_posts()` 로드 시 post별 `searchable` 사전계산 문자열을 생성. 요청당 1,079 × `lower()` 비용 제거.

### 기대효과 대비 투입 비교

| 비교 항목 | E1 디바운스+Abort | E2 검색 전용 렌더 경로 | E3 서버 프리워밍 인덱스 |
|---|---|---|---|
| 해결하는 병목 | 한 검색어 입력 중 `renderPosts()`가 글자 수만큼 반복 실행 (4타 = 4 사이클) | 결과 수백 장 렌더 시 `innerHTML=''` + 전체 재생성으로 인한 프레임 드랍 | 매 검색 요청마다 1,079건을 새로 `lower()` + `concat` 하는 CPU 낭비 |
| 사용자 체감 개선 | 🟢🟢🟢 매우 큼 — 타이핑 버벅임의 1차 원인 | 🟢🟢 큼 — 결과 렌더 프레임 드랍 감소 | 🟢 작음 — 요청당 10~30ms → 1ms 미만, 로컬이라 차이 미세 |
| 검색 60% 사용자에 대한 가치 | 🟢🟢🟢 직접적 | 🟢🟢 결과가 50장 초과일 때만 체감 | 🟢 백그라운드 최적화, 체감 무감지 |
| 구현 라인 수 (추정) | 🟢 10~20줄 | 🔴 80~150줄 | 🟢 5~10줄 |
| 수정 파일 수 | 🟢 1개 (`script.js`) | 🟡 2개 (`script.js` + `style.css`) | 🟢 1개 (`server.py`) |
| 기존 동작 회귀 위험 | 🟢 낮음 — 핸들러 교체 | 🔴 높음 — masonry·태그 DOM·이벤트 바인딩 재사용 로직 복잡, 모드 진입/종료 경로 관리 필요 | 🟢 매우 낮음 — 메모리 사전계산만 추가 |
| 테스트 비용 | 🟢 유닛 1~2개 (디바운스·Abort) | 🟡 E2E 시나리오 다수 (검색 모드 진입·종료·재진입·하이라이트 해제) | 🟢 기존 `/api/search` 테스트로 커버 |
| SPEC 범위 적합성 | 🟢 SPEC 수준 결정 가능 | 🟡 대부분 plan 단계 구현 상세 | 🟢 SPEC 수준 결정 가능 |
| 제거·롤백 난이도 | 🟢 쉬움 | 🔴 어려움 (두 경로 혼재 debt) | 🟢 쉬움 |
| 본 SPEC 없이 단독 효과 | 🟢🟢🟢 단독으로도 검색 체감 크게 개선 | 🟢 본 SPEC의 단계 렌더와 중복 해결 | 🟢 단독 효과 미미 |
| 본 SPEC과의 관계 | 보완적 — R4에 누락된 조각 | 🔴 **중복** — D3-2 "초기 N장 + 스크롤 sentinel"이 80% 커버 | 보완적 — D2 `/api/search` 성능 확정 |
| ROI (기대효과/투입) | 🟢🟢🟢 최상 | 🟡 낮음 (SPEC과 겹침, 복잡도만 추가) | 🟢🟢 높음 (투입 미미, 이득은 작아도 무리 없음) |

### 결론

- **E1 채택** — 본 SPEC의 서버 전환을 **성립시키는 전제**. 디바운스 없이 서버로 전환하면 4타 입력 = 4회 네트워크 왕복 + 4회 DOM 재생성으로 오히려 악화될 수 있다. R4.1로 반영.
- **E3 채택** — 투입이 거의 0(5~10줄)이고 롤백이 쉽다. 데이터가 2,000건대로 확장될 때 효과가 커지므로 "넣어두고 필요 없으면 빼는" 비용이 낮다. R4.2로 반영.
- **E2 미채택** — 본 SPEC D3-2(초기 N장 + `IntersectionObserver` sentinel)가 "결과 수가 많을 때 단계 렌더"를 자동 달성한다. E2에서 남는 가치는 하이라이트(`<mark>`)와 DOM key diff뿐인데, 전자는 plan 단계 상세이고 후자는 1,079건 규모에서 투입 대비 이득이 빈약하다. 범위만 커지고 성능 지표는 그대로. 이것이 "과설계"의 의미다.

### 본 SPEC 반영 위치

- R4 → R4.1 / R4.2로 세분화
- SC2에 "4타 연속 타이핑 중 중간 렌더 0" 및 AbortController 경쟁 조건 차단 추가
- [OK] 경계선에 E1·E3 명시
- 결정안 D7 신설

## 부록: 참조 자료

| 출처 | 용도 |
|------|------|
| `D:/vibe-coding/session-dashboard/docs/specs/20260419_01_index-html-로딩속도-개선-lazy-load.md` | 동형 문제의 SPEC. 요구사항·경계선·결정안 틀 차용 |
| `D:/vibe-coding/session-dashboard/docs/20260419_01_main-기준-세션대시보드-지연로딩-검수반영.md` | 구현·검수 결과 교훈 |
| `D:/vibe-coding/scrap_sns/CLAUDE.md` | 데이터 플로우·표준 스키마·태그 규칙 |
| `D:/vibe-coding/scrap_sns/utils/post_schema.py` | `STANDARD_FIELD_ORDER`, `REQUIRED_FIELDS` 계약 |
