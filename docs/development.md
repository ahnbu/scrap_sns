---
title: "SNS Crawler 개발 기준"
created: "2026-04-17 13:20"
---

# SNS Crawler 개발 기준

이 문서는 현재 워킹트리 기준의 개발 참조 문서다. 빠른 실행법은 `README.md`, 전체 흐름은 `docs/crawling_logic.md`, 여기서는 데이터 구조와 URL 규칙, 영구화 surface를 정리한다.

## 정본

- 실행 진입점 정본: `sns_hub.vbs`, `server.py`, 레포 루트 `index.html`
- 표준 Post 스키마 정본: `utils/post_schema.py`
- 로컬 조회 CLI 정본: `utils/query-sns.mjs`
- Threads URL 정규화 정본: `utils/post_schema.py`, `utils/query-sns.mjs`, `web_viewer/script.js`

## 현재 런타임 구성

- 플랫폼 수집기: Threads, LinkedIn, X(Twitter)
- 오케스트레이터: `total_scrap.py`
- 뷰어 진입: `wscript sns_hub.vbs` 또는 `SNS허브_바로가기.lnk`
- API 서버: `server.py`
- 뷰어 상태: `web_viewer/sns_tags.json`, browser `localStorage`

현재 shipped HTML 진입점은 레포 루트 `index.html`이다. `server.py`는 `/api/*` 제공이 중심이며, `/` 라우트는 현재 로컬 런처 기준 진입점으로 가정하지 않는다.

## 영구화 surface

문서나 로직을 바꿀 때 실제로 영향받는 저장 surface는 아래다.

- Threads 목록: `output_threads/python/threads_py_simple_YYYYMMDD.json`
- Threads 상세: `output_threads/python/threads_py_full_YYYYMMDD.json`
- Threads 실패 이력: `scrap_failures_threads.json`
- LinkedIn 전체: `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- X 목록: `output_twitter/python/twitter_py_simple_YYYYMMDD.json`
- X 상세: `output_twitter/python/twitter_py_full_YYYYMMDD.json`
- X 실패 이력: `scrap_failures_twitter.json`
- 통합본: `output_total/total_full_YYYYMMDD.json`
- 태그 저장소: `web_viewer/sns_tags.json`
- 브라우저 상태: `localStorage`
- 인증 런타임: `C:\Users\ahnbu\.config\auth\`
  - LinkedIn: `linkedin/storage_state.json`
  - Threads: `threads/storage_state.json`
  - Skool: `skool/storage_state.json`
  - X canonical: `x/user_data/`, `x/cookies.json`, `x/storage_state.json`
  - X compatibility: `x_cookies_current.json`, `x_storage_state_current.json`

파싱·정규화 로직 변경 시 위 surface 중 어떤 파일이 영향을 받는지 먼저 확인해야 한다.

## 표준 Post 스키마

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
- `normalize_post()`는 `user`, `timestamp`, `post_url`, `source_url`를 현재 필드로 승격한다.
- Threads는 `url`이 비어 있으면 `username`과 `platform_id` 또는 `code`로 canonical URL을 합성한다.

## 플랫폼별 데이터 구조

### Threads

- 목록 수집기: `thread_scrap.py`
- 상세 수집기: `thread_scrap_single.py` (`requests` 기반 browserless consumer)
- 어댑터: `utils/threads_http_adapter.py`
- 주요 응답 루트: `data.xdt_text_app_viewer.saved_media.edges`
- 상세 추출 기준: `utils/threads_parser.py` (변경 없음)

주요 매핑:

- `platform_id` / `code`: 게시물 코드
- `username`: 작성자 계정
- `full_text`: 본문 또는 병합된 thread 본문
- `media`: `image_versions2` 또는 `carousel_media`에서 수집
- `created_at`: `taken_at` 기반 절대 시각
- `url`: `https://www.threads.com/@{username}/post/{code}`

상세 수집기는 `C:\Users\ahnbu\.config\auth\threads\storage_state.json` storage_state의 `.threads.com` 쿠키를 읽어 permalink HTML을 직접 가져오고, 같은 작성자의 연속된 타래글을 병합해 `is_merged_thread`, `original_item_count` 같은 보조 정보를 붙일 수 있다.

### LinkedIn

- 수집기: `linkedin_scrap.py`
- 주요 응답: Voyager GraphQL GET 응답
- 추출 기준: `utils/linkedin_parser.py`

주요 매핑:

- `platform_id`: `entityUrn`에서 추출한 activity id
- `urn`: 원본 `entityUrn`
- `display_name`, `username`: Voyager 응답 조합
- `created_at`: Snowflake id 디코딩 우선, 없으면 `time_text` 역산, 최후에는 수집 시각
- `media`: VectorImage artifact 또는 fallback URL
- `url`: 게시물 permalink

### X(Twitter)

- 목록 수집기: `twitter_scrap.py`
- 상세 수집기: `twitter_scrap_single.py` (`twitter-cli` 기반 focal tweet collector)
- 레거시 상세 HTML 파서: `utils/twitter_parser.py` (회귀 테스트용 유지, runtime 미사용)

주요 매핑:

- `platform_id`: `rest_id`
- `full_text`: `twitter-cli` payload의 `data[0].text`만 저장
- `media`: `photo`는 `wsrv` URL, `video`와 `animated_gif`는 raw URL 저장
- `created_at`: 목록 단계 값이 있으면 유지하고, 비어 있을 때만 상세 단계 수집 시각으로 fallback 채움
- `url`: 기본은 `https://x.com/{username}/status/{post_id}`, 사용자명이 비어 있으면 `https://x.com/i/status/{post_id}`

상세 수집 단계에서 실제 focal tweet 작성자명이 확인되면 `username`과 `url`이 재보정될 수 있다. 이 단계의 토큰 원본은 `C:\Users\ahnbu\.config\auth\x\cookies.json`이며, 필요 시 latest `cookies_*.json`으로 fallback한다.

## URL 정규화 규칙

- Threads canonical: `https://www.threads.com/@{username}/post/{code}`
- 레거시 alias:
  - `https://www.threads.net/...`
  - `https://www.threads.com/t/{code}`
  - `https://www.threads.net/t/{code}`
- 뷰어와 CLI는 위 alias를 모두 `.threads.com/@user/post/code`로 정규화한다.
- X와 LinkedIn은 수집 시점 원본 permalink를 유지한다.

## 뷰어와 태그 상태

- `index.html`은 `web_viewer/script.js`를 로드한다.
- 메타 목록은 `GET /api/posts`에서 읽고, 상세 본문과 미디어는 `GET /api/post/<sequence_id>`에서 lazy-load 한다.
- 검색은 `GET /api/search`, 자동 태그 일괄 적용은 `POST /api/auto-tag/apply`를 사용한다.
- 태그는 `localStorage`와 `web_viewer/sns_tags.json`에 함께 저장된다.
- 서버 API:
  - `/api/status`
  - `/api/posts`
  - `/api/post/<sequence_id>`
  - `/api/search`
  - `/api/auto-tag/apply`
  - `/api/get-tags`
  - `/api/save-tags`
  - `/api/run-scrap`
- `migrateLegacyTagKeys()`는 예전 Threads URL 키를 현재 canonical 키로 이동시킨다.

## 마이그레이션 및 유틸리티

- `python migrate_schema.py --target "output_total/total_full_*.json"`: 레거시 필드 구조 점검
- `python migrate_schema.py --target "output_total/total_full_*.json" --apply`: 스키마 승격 적용
- `python migrate_threads_domain.py --dry-run`: Threads 도메인 정규화 점검
- `node utils/query-sns.mjs --help`: 통합 데이터/태그 조회 CLI

## 관련 테스트

- `tests/unit/test_post_schema.py`
- `tests/unit/test_threads_parser.py`
- `tests/unit/test_linkedin_parser.py`
- `tests/unit/test_twitter_parser.py`
- `tests/unit/test_migrate_threads_domain.py`
- `tests/unit/test_web_viewer_resolve_post_url.py`
- `tests/unit/test_web_viewer_auto_tagging.py`
- `tests/contract/test_schemas.py`

## 문서 업데이트 규칙

다음이 바뀌면 이 문서를 같이 고친다.

- 표준 필드 목록 또는 required field
- 플랫폼별 canonical URL 규칙
- 영구화 surface 위치와 파일명 패턴
- 태그 저장 방식 또는 서버 API surface
