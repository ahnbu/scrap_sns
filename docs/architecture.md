---
title: "SNS Crawler 아키텍처"
created: "2026-07-26 18:40"
---

# SNS Crawler 아키텍처

이 문서는 현재 워킹트리 기준의 통합 참조 문서다. 빠른 설치·실행법은 `README.md`를 본다.

기존 `docs/development.md`(데이터 구조·스키마)와 `docs/crawling_logic.md`(수집 흐름)를 통합했다. 플랫폼별 정보를 한 섹션에 모아, 한 플랫폼을 이해하려고 두 문서를 오갈 필요가 없게 했다.

## 1. 런타임 구성

### 정본

- 실행 진입점: `sns_hub.vbs`, `scrap_sns_server.py`, 레포 루트 `index.html`
- 표준 Post 스키마: `utils/post_schema.py`
- 로컬 조회 CLI: `utils/query-sns.mjs`
- Threads URL 정규화: `utils/post_schema.py`, `utils/query-sns.mjs`, `web_viewer/script.js`

### 구성 요소

- 플랫폼 수집기: Threads, LinkedIn, X(Twitter), YouTube
- 오케스트레이터: `total_scrap.py`
- 뷰어 진입: `wscript sns_hub.vbs` 또는 `SNS허브_바로가기.lnk`
- API 서버: `scrap_sns_server.py`
- 뷰어 상태: `web_viewer/sns_tags.json`, `web_viewer/sns_tag_catalog.json`, `web_viewer/sns_user_metadata.json`, browser `localStorage`

### 실행 엔트리

- 권장 런처: `wscript sns_hub.vbs`
- 서버 단독 실행: `python scrap_sns_server.py`
- 전체 수집: `python total_scrap.py --mode update` 또는 `--mode all`

현재 shipped HTML 진입점은 레포 루트 `index.html`이다. `scrap_sns_server.py`는 `/api/*` 제공이 중심이며, 서버 `/` 라우트와 `sns_hub.vbs`는 모두 루트 `index.html`을 기준으로 동작한다. 운영 문서도 동일하게 `http://localhost:5000/` 진입을 기준으로 설명한다.

`sns_hub.vbs`와 `run_viewer.bat`는 `scripts/restart_viewer_server.ps1`을 통해 5000번 포트의 기존 `scrap_sns_server.py` 프로세스만 종료한 뒤 새 서버를 시작한다. 서버가 이미 정상 응답 중이어도 런처 실행 시 항상 재시작한다.

### 인증 런타임

인증 런타임 정본은 `C:\Users\ahnbu\.config\auth`다. 레포의 `auth/`는 이 경로를 가리키는 junction이며, consumer는 repo-local auth 자산을 직접 정본으로 보지 않는다.

## 2. 표준 Post 스키마

정본은 `utils/post_schema.py:STANDARD_FIELD_ORDER`다.

```python
STANDARD_FIELD_ORDER = [
    "sequence_id",
    "platform_id",
    "sns_platform",
    "code",
    "urn",
    "username",
    "display_name",
    "full_text",
    "media",
    "url",
    "created_at",
    "date",
    "crawled_at",
    "source",
    "local_images",
    "is_detail_collected",
    "is_merged_thread",
]

REQUIRED_FIELDS = ["sns_platform", "username", "url", "created_at"]
```

추가 규칙:

- `full_text`와 `media` 중 하나는 반드시 있어야 한다.
- `normalize_post()`는 `user`, `timestamp`, `post_url`, `source_url`를 현재 필드로 승격한다. 레거시 필드 rename도 `normalize_post()`가 처리한다.
- Threads는 `url`이 비어 있으면 `username`과 `platform_id` 또는 `code`로 canonical URL을 합성한다.
- 저장 직전 `validate_post()`로 스키마 위반을 차단한다.

## 3. URL 정규화 규칙

- Threads canonical: `https://www.threads.com/@{username}/post/{code}`
- 레거시 alias:
  - `https://www.threads.net/...`
  - `https://www.threads.com/t/{code}`
  - `https://www.threads.net/t/{code}`
- 뷰어와 CLI는 위 alias를 모두 `.threads.com/@user/post/code`로 정규화한다.
- X와 LinkedIn은 수집 시점 원본 permalink를 유지한다.

## 4. 플랫폼별

### 4.1 Threads

**수집기와 파서**

- 목록 수집기(producer): `thread_scrap.py`
- 상세 수집기(consumer): `thread_scrap_single.py` (`requests` 기반 browserless consumer)
- 어댑터: `utils/threads_http_adapter.py`
- 상세 추출 기준: `utils/threads_parser.py`
- 주요 응답 루트: `data.xdt_text_app_viewer.saved_media.edges`

**데이터 매핑**

- `platform_id` / `code`: 게시물 코드
- `username`: 작성자 계정
- `full_text`: 본문 또는 병합된 thread 본문
- `media`: `image_versions2` 또는 `carousel_media`에서 수집
- `created_at`: `taken_at` 기반 절대 시각
- `url`: `https://www.threads.com/@{username}/post/{code}`

**수집 흐름**

1. `thread_scrap.py`가 저장 목록을 스크롤하며 simple 파일을 만든다.
2. simple 항목 중 `is_detail_collected`가 비어 있는 글만 `thread_scrap_single.py`가 `AUTH_HOME/threads/storage_state.json` 쿠키를 읽어 browserless `requests`로 permalink HTML을 가져온다.
3. `utils/threads_parser.py`가 HTML에 임베드된 `thread_items`를 파싱하고, 상세 수집기는 같은 작성자의 연속된 타래를 병합해 full 파일에 승격한다. 병합 시 `is_merged_thread`, `original_item_count` 같은 보조 정보를 붙일 수 있다.
4. 실패 항목은 `scrap_failures_threads.json`에 누적한다.

**출력**

- `output_threads/python/threads_py_simple_YYYYMMDD.json`
- `output_threads/python/threads_py_full_YYYYMMDD.json`
- `scrap_failures_threads.json`

### 4.2 LinkedIn

**수집기와 파서**

- 수집기: `linkedin_scrap.py`
- 주요 응답: Voyager GraphQL GET 응답
- 추출 기준: `utils/linkedin_parser.py`

**데이터 매핑**

- `platform_id`: `entityUrn`에서 추출한 activity id
- `urn`: 원본 `entityUrn`
- `display_name`, `username`: Voyager 응답 조합
- `created_at`: Snowflake id 디코딩 우선, 없으면 `time_text` 역산, 최후에는 수집 시각
- `media`: VectorImage artifact 또는 fallback URL
- `url`: 게시물 permalink

**수집 흐름**

1. `linkedin_scrap.py`가 Voyager GraphQL 응답을 가로채 저장 게시물을 추출한다.
2. 기존 full 파일을 읽어 증분 중복을 막고, 필요한 메타데이터를 보존한다.
3. `all` 모드는 `media` 없는 기존 글을 재수집 대상으로 삼는다.
4. 결과를 최신 full 파일과 update 디렉토리에 반영한다.

**출력**

- `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- `output_linkedin/python/update/`

#### 수집 순서

Voyager GraphQL 응답의 배열 순서는 저장글 화면의 표시 순서와 일치하지 않는다. **원인은 수집 코드가 아니라 응답 자체다.**

실측 근거:

- 화면 대조(2026-07-26, Chrome 확장으로 저장글 DOM 직접 추출): 화면 상위 9건이 수집 배열에서 `9, 0, 7, 3, 1, 2, 5, 6, 4` 위치에 분산. 뒤집힘도 부분 정렬도 아닌 무작위다.
- 수집 코드는 응답 순서를 그대로 보존한다(2026-07-07): 응답 원문의 묶음 내 순서와 Playwright 수집 배열이 10건 중 9건 위치까지 동일했다. 1건 차이는 그 사이 저장글이 바뀐 것이다.
- 네트워크 도착 순서도 정상이다: 응답별 `start` 오프셋을 계측한 결과 `start=0 → 10 → 20 → … → 623` 63개 응답이 완전한 오름차순으로 도착했고 역전은 0건이었다.

따라서 응답 순번이나 묶음 내 위치를 기록해도 화면 순서를 복원할 수 없다. `start` 오프셋은 묶음 경계를 알려줄 뿐, 묶음 안의 순서가 이미 화면과 다르다.

정렬 정책:

- `sequence_id` 부여 시 배열 순서를 신뢰하지 않는다
- `crawled_at`은 한 번의 실행에서 전부 동일하므로 단독 정렬 키가 되지 못한다
- 2차 정렬 키로 `date`(작성일) 오름차순을 사용한다. 단 저장 순서와 작성일 순서는 다를 수 있으므로 근사치다(예: 오래된 글을 오늘 저장하면 같은 수집 묶음 안에서 아래쪽에 배치된다)
- 실제 저장 순서가 필요하면 브라우저에서 저장글 페이지 DOM을 직접 읽어 대조하는 방법뿐이다
- 화면 순서 정본 예시: `tests/fixtures/golden/linkedin/20260726_saved_posts_screen_order.json`

`platform_sequence_id`는 3개 플랫폼 모두에 부여되지만(5절 참조), **LinkedIn 값은 화면 순서를 반영하지 않으므로 정렬에 사용하지 않는다.**

#### 모드별 스킵 규칙

`--mode all`은 "이미 수집한 글"이 아니라 **`media`가 있는 기존 글**을 건너뛴다.

- `--mode update`: 기존 글을 만나면 스킵하고, 20건 연속 시 조기 종료(`CONSECUTIVE_EXISTING_LIMIT`)
- `--mode all`: 기존 글이어도 `media`가 없으면 재수집(이미지 보강 목적)
- 따라서 `all` 실행 배열에 최신 글이 없을 수 있으며 이는 정상 동작이다

### 4.3 X(Twitter)

**수집기와 파서**

- 목록 수집기(producer): `twitter_scrap.py`
- 상세 수집기(consumer): `twitter_scrap_single.py` (`twitter-cli` 기반 focal tweet collector)
- 레거시 상세 HTML 파서: `utils/twitter_parser.py` (회귀 테스트용 유지, runtime 미사용)

**데이터 매핑**

- `platform_id`: `rest_id`
- `full_text`: `twitter-cli` payload의 `data[0].text`만 저장
- `media`: `photo`는 `wsrv` URL, `video`와 `animated_gif`는 raw URL 저장
- `created_at`: 목록 단계 값이 있으면 유지하고, 비어 있을 때만 상세 단계 수집 시각으로 fallback 채움
- `url`: 기본은 `https://x.com/{username}/status/{post_id}`, 사용자명이 비어 있으면 `https://x.com/i/status/{post_id}`

**수집 흐름**

1. `twitter_scrap.py`가 북마크 타임라인 JSON과 HTML fallback에서 simple 목록을 만든다.
2. `twitter_scrap_single.py`가 `AUTH_HOME/x/cookies.json`을 우선 읽고, 필요 시 latest `cookies_*.json` fallback에서 `auth_token`, `ct0`를 꺼내 `twitter tweet <url> --json`으로 focal tweet 상세를 조회한다.
3. 상세 단계는 CLI payload의 첫 항목만 사용해 focal tweet 본문, 미디어, 실제 작성자명만 보강한다. 대화 전체 thread 확장은 하지 않는다.
4. 3회 이상 실패한 항목은 `scrap_failures_twitter.json`을 기준으로 잠시 제외한다.

상세 수집 단계에서 실제 focal tweet 작성자명이 확인되면 `username`과 `url`이 재보정될 수 있다.

**인증 주의**

X 인증 정본은 `AUTH_HOME/x/user_data/` 하나다. producer는 이 profile을 직접 사용하고, consumer는 같은 profile에서 export된 `cookies.json`을 사용한다. 따라서 인증 갱신 완료 판정은 producer probe와 consumer token probe가 모두 통과해야 한다.

consumer 토큰이 없으면 상세 수집은 건너뛰고, simple 기반 메타데이터/full 동기화만 계속 진행한다.

**출력**

- `output_twitter/python/twitter_py_simple_YYYYMMDD.json`
- `output_twitter/python/twitter_py_full_YYYYMMDD.json`
- `scrap_failures_twitter.json`

## 5. 병합·통합

### 전체 흐름

1. `total_scrap.py`가 1차 wave에서 플랫폼별 목록 수집기(producer)를 실행한다.
2. 같은 실행의 2차 wave에서 Threads와 X 상세 수집기(consumer)가 최신 simple 파일을 다시 읽어 본문, 미디어, thread context를 보강한다.
3. consumer까지 끝난 뒤 `total_scrap.py`가 최신 full 파일을 병합해 통합본을 만든다.
4. 뷰어는 `GET /api/posts`로 메타 목록을 읽고 `GET /api/post/<int:sequence_id>`로 상세 본문과 미디어를 lazy-load 한다.

### 병합 순서

`total_scrap.py`는 아래 순서로 처리한다.

1. producer wave 실행: Threads, X, LinkedIn, YouTube 목록 수집
2. consumer wave 실행: Threads, X 상세 수집 (YouTube는 producer 단계에서 상세까지 끝낸다)
3. Threads, LinkedIn, X, YouTube 최신 full 파일 로드
4. 플랫폼 이름 정규화: `threads`, `linkedin`, `x`, `youtube`
5. 플랫폼 내부 순서를 `platform_sequence_id`로 부여 (4개 플랫폼 전부)
   단 LinkedIn 값은 화면 순서를 반영하지 않는다(4.2절 수집 순서 참조). 정렬에 사용하지 말 것.
6. ID 기준 중복 제거
7. 통합본을 `output_total/total_full_YYYYMMDD.json`에 저장
8. Markdown 변환과 로컬 이미지 다운로드를 수행

로그는 `logs/`에 플랫폼별로 남긴다.

## 6. 영구화 surface

문서나 로직을 바꿀 때 실제로 영향받는 저장 surface는 아래다. 파싱·정규화 로직 변경 시 어떤 파일이 영향을 받는지 먼저 확인해야 한다.

| 구분 | 경로 |
| --- | --- |
| Threads 목록 | `output_threads/python/threads_py_simple_YYYYMMDD.json` |
| Threads 상세 | `output_threads/python/threads_py_full_YYYYMMDD.json` |
| Threads 실패 이력 | `scrap_failures_threads.json` |
| LinkedIn 전체 | `output_linkedin/python/linkedin_py_full_YYYYMMDD.json` |
| X 목록 | `output_twitter/python/twitter_py_simple_YYYYMMDD.json` |
| X 상세 | `output_twitter/python/twitter_py_full_YYYYMMDD.json` |
| X 실패 이력 | `scrap_failures_twitter.json` |
| YouTube 전체 | `output_youtube/python/youtube_py_full_YYYYMMDD.json` |
| YouTube 자막 전문 | `output_youtube/transcripts/{videoId}.txt` |
| YouTube 요약 캐시 | `output_youtube/summaries/{videoId}.json` |
| 통합본 | `output_total/total_full_YYYYMMDD.json` |
| 게시물별 태그 | `web_viewer/sns_tags.json` |
| 태그 카탈로그 | `web_viewer/sns_tag_catalog.json` |
| 사용자 메타데이터 정본 | `web_viewer/sns_user_metadata.json` |
| 사용자 메타데이터 캐시 | `localStorage.sns_user_metadata` |
| 브라우저 상태 | `localStorage` |

인증 런타임 (`C:\Users\ahnbu\.config\auth\`):

| 플랫폼 | 경로 |
| --- | --- |
| LinkedIn | `linkedin/storage_state.json` |
| Threads | `threads/storage_state.json` |
| Skool | `skool/storage_state.json` |
| X canonical | `x/user_data/`, `x/cookies.json`, `x/storage_state.json` |
| X compatibility | `x_cookies_current.json`, `x_storage_state_current.json` |

## 7. 뷰어·API surface

### 뷰어 구성

- `index.html`은 `web_viewer/script.js`를 로드한다.
- 메타 목록은 `GET /api/posts`에서 읽고, 상세 본문과 미디어는 `GET /api/post/<int:sequence_id>`에서 lazy-load 한다.
- 검색은 `GET /api/search`, 자동 태그 일괄 적용은 `POST /api/auto-tag/apply`를 사용한다.
- 검색 매칭은 대소문자를 무시하고, `-`와 `_`를 공백처럼 정규화한 뒤 다단어 AND 부분일치를 적용한다. 오타 보정과 붙여쓰기 compact 검색은 지원하지 않는다.

### 태그·상태 저장

- 게시물별 태그는 `localStorage.sns_tags`와 `web_viewer/sns_tags.json`에 함께 저장된다. `sns_tags.json`은 URL→태그 배열 구조다.
- 태그명, 강조 표시, alias/키워드는 `localStorage.sns_tag_catalog`와 `web_viewer/sns_tag_catalog.json`에 저장된다.
- 별표, 숨김, 메모는 `post_key` 기준으로 `web_viewer/sns_user_metadata.json`에 저장된다.
- `canonical_url`은 원문 열기와 legacy 상태 migration 보조값으로 보존한다.
- 기존 `localStorage.sns_auto_tag_rules`는 첫 로드 때 태그 카탈로그 alias로 1회 병합된다.
- `web_viewer/script.js`는 `resolvePostUrl()`과 `migrateLegacyTagKeys()`로 예전 Threads 키를 현재 canonical URL 키에 매핑한다. 이 덕분에 기존 태그를 유지하면서 `.threads.com` 기반으로 점진 전환할 수 있다.

### 서버 API surface

정본은 `scrap_sns_server.py`의 라우트 정의다. 이 목록은 `tests/contract/test_api_surface.py`가 코드와 대조하므로, 라우트를 추가·삭제하면 이 문서도 함께 고쳐야 한다.

**게시물 데이터**

- `GET /api/status`
- `GET /api/posts`
- `GET /api/post/<int:sequence_id>`
- `GET /api/search`
- `GET /api/latest-data`

**태그·메타데이터**

- `GET /api/get-tags` / `POST /api/save-tags`
- `GET /api/get-tag-catalog` / `POST /api/save-tag-catalog`
- `GET /api/get-user-metadata` / `POST /api/save-user-metadata`
- `POST /api/auto-tag/apply`

**수집 실행**

- `POST /api/run-scrap`
- `GET /api/scrap-progress`

**인증 (미사용 — BL-0505-03)**

- `POST /api/auth/start`
- `GET /api/auth/status`
- `POST /api/auth/complete`

> 위 3종은 2026-05-04 `f7205f4`로 프론트엔드 호출이 끊긴 죽은 코드다. 라우트는 남아 있으나 운영 흐름에서 사용하지 않는다.

문서 산문에서 와일드카드 형태로 `/api/auth/` 계열을 언급할 때는 백틱으로 감싸지 않는다. 백틱 코드 표기는 개별 라우트에만 쓴다. 위 대조 테스트가 백틱 안의 경로를 라우트로 인식하기 때문이다.

### 뷰어 순서 검증 주의

게시물 표시 순서를 검증할 때 DOM 순서나 API 응답 순서를 그대로 읽으면 잘못된 결과가 나온다. 두 가지가 모두 최종 표시 순서와 다르다.

- 뷰어는 Masonry 레이아웃(`web_viewer/script.js`의 `buildMasonryColumns`)이라 카드를 여러 컬럼에 분산 배치한다. **DOM 순서와 시각적 순서가 다르다.**
- `GET /api/posts` 응답 배열도 `sequence_id` 순이 아니다. 정렬은 프론트엔드 `sortPosts()`가 담당한다.
- 순서 검증은 뷰어와 동일한 정렬 규칙을 응답 데이터에 적용해 비교한다. "로컬 수집순"은 `_seqId` 내림차순이다(`web_viewer/script.js`의 `sortPosts`, `currentSort === 'saved'` 분기).

## 8. 검증·마이그레이션

### 마이그레이션 및 유틸리티

- `python migrate_schema.py --target "output_total/total_full_*.json"`: 레거시 필드 구조 점검
- `python migrate_schema.py --target "output_total/total_full_*.json" --apply`: 스키마 승격 적용
- `python migrate_threads_domain.py --dry-run`: Threads 도메인 정규화 점검
- `node utils/query-sns.mjs --help`: 통합 데이터/태그 조회 CLI

### 검증 포인트

수집·정규화 로직을 바꾼 뒤에는 최소한 아래를 다시 확인한다.

- `pytest tests/unit`
- `pytest tests/contract`
- `pytest tests/e2e/test_api_security.py`
- `node utils/query-sns.mjs --help`
- 변경 범위가 Threads URL이면 `pytest tests/unit/test_migrate_threads_domain.py`

### 관련 테스트

- `tests/unit/test_post_schema.py`
- `tests/unit/test_threads_parser.py`
- `tests/unit/test_linkedin_parser.py`
- `tests/unit/test_twitter_parser.py`
- `tests/unit/test_migrate_threads_domain.py`
- `tests/unit/test_web_viewer_resolve_post_url.py`
- `tests/unit/test_web_viewer_auto_tagging.py`
- `tests/contract/test_schemas.py`
- `tests/contract/test_api_surface.py`

## 9. 문서 업데이트 규칙

다음이 바뀌면 이 문서를 같이 고친다.

- 표준 필드 목록 또는 required field
- 플랫폼별 canonical URL 규칙
- 영구화 surface 위치와 파일명 패턴
- 태그 저장 방식 또는 서버 API surface

함께 현행화할 문서:

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
