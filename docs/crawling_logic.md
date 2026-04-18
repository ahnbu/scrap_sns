---
title: "SNS Crawler 크롤링 로직"
created: "2026-04-17 13:25"
---

# SNS Crawler 크롤링 로직

이 문서는 현재 코드 기준의 수집 파이프라인을 설명한다. 플랫폼별 응답 구조 배경보다, 어떤 스크립트가 어떤 순서로 데이터를 만들고 어디에 저장하는지에 집중한다.

## 전체 흐름

1. 플랫폼별 목록 수집기가 저장 게시물 목록을 읽는다.
2. Threads와 X는 상세 수집기로 본문, 미디어, thread context를 보강한다.
3. `total_scrap.py`가 최신 full 파일을 병합해 통합본을 만든다.
4. 필요 시 `python -m utils.build_data_js`가 `web_viewer/data.js`를 갱신한다.
5. 뷰어는 루트 `index.html`에서 통합 데이터와 태그 상태를 로드한다.

## 실행 엔트리

- 권장 런처: `wscript sns_hub.vbs`
- 서버 단독 실행: `python server.py`
- 전체 수집: `python total_scrap.py --mode update` 또는 `--mode all`

`sns_hub.vbs`는 서버를 백그라운드로 띄운 뒤 `/api/status`를 확인하고 레포 루트 `index.html`을 연다. 현재 운영 흐름은 "로컬 HTML + API 서버" 조합이다.

## 플랫폼별 수집 흐름

### Threads

1. `thread_scrap.py`가 저장 목록을 스크롤하며 simple 파일을 만든다.
2. simple 항목 중 `is_detail_collected`가 비어 있는 글만 `thread_scrap_single.py`가 `auth/auth_threads.json` 쿠키를 읽어 browserless `requests`로 permalink HTML을 가져온다.
3. `utils/threads_parser.py`가 HTML에 임베드된 `thread_items`를 파싱하고, 상세 수집기는 같은 작성자의 연속된 타래를 병합해 full 파일에 승격한다.
4. 실패 항목은 `scrap_failures_threads.json`에 누적하고, 저장 직전 `validate_post()`로 스키마 위반을 차단한다.

주요 출력:

- `output_threads/python/threads_py_simple_YYYYMMDD.json`
- `output_threads/python/threads_py_full_YYYYMMDD.json`
- `scrap_failures_threads.json`

### LinkedIn

1. `linkedin_scrap.py`가 Voyager GraphQL 응답을 가로채 저장 게시물을 추출한다.
2. 기존 full 파일을 읽어 증분 중복을 막고, 필요한 메타데이터를 보존한다.
3. 결과를 최신 full 파일과 update 디렉토리에 반영한다.

주요 출력:

- `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- `output_linkedin/python/update/`

### X(Twitter)

1. `twitter_scrap.py`가 북마크 타임라인 JSON과 HTML fallback에서 simple 목록을 만든다.
2. `twitter_scrap_single.py`가 `auth/x_cookies_*.json`에서 `auth_token`, `ct0`를 읽고 `twitter tweet <url> --json`으로 focal tweet 상세를 조회한다.
3. 상세 단계는 CLI payload의 첫 항목만 사용해 focal tweet 본문, 미디어, 실제 작성자명만 보강한다. 대화 전체 thread 확장은 하지 않는다.
4. 3회 이상 실패한 항목은 `scrap_failures_twitter.json`을 기준으로 잠시 제외한다.

consumer 토큰이 없으면 상세 수집은 건너뛰고, simple 기반 메타데이터/full 동기화만 계속 진행한다.

주요 출력:

- `output_twitter/python/twitter_py_simple_YYYYMMDD.json`
- `output_twitter/python/twitter_py_full_YYYYMMDD.json`
- `scrap_failures_twitter.json`

## 병합 로직

`total_scrap.py`는 플랫폼별 최신 full 파일을 찾아 아래 순서로 처리한다.

1. Threads, LinkedIn, X full 파일 로드
2. 플랫폼 이름 정규화: `threads`, `linkedin`, `x`
3. 플랫폼 내부 순서를 `platform_sequence_id`로 보존
4. ID 기준 중복 제거
5. 통합본을 `output_total/total_full_YYYYMMDD.json`에 저장
6. 필요 시 Markdown 변환과 뷰어용 정적 데이터 갱신 수행

로그는 `logs/`에 플랫폼별로 남긴다.

## 표준화와 정규화

- Post 스키마 정본은 `utils/post_schema.py`
- 레거시 필드 rename은 `normalize_post()`가 처리
- Threads canonical URL은 `https://www.threads.com/@{username}/post/{code}`
- 레거시 Threads 도메인과 `/t/{code}` 패턴은 뷰어와 CLI에서 alias로 흡수

관련 도구:

- `migrate_schema.py`
- `migrate_threads_domain.py`
- `utils/query-sns.mjs`

## 뷰어 연동

뷰어는 아래 두 축으로 상태를 읽는다.

### 게시물 데이터

- `/api/latest-data`
- `web_viewer/data.js`

### 태그와 UI 상태

- `localStorage`
- `web_viewer/sns_tags.json`
- `/api/get-tags`
- `/api/save-tags`

`web_viewer/script.js`는 `resolvePostUrl()`과 `migrateLegacyTagKeys()`로 예전 Threads 키를 현재 canonical URL 키에 매핑한다. 이 덕분에 기존 태그를 유지하면서 `.threads.com` 기반으로 점진 전환할 수 있다.

## 서버 역할

`server.py`는 현재 아래 API만 안정적인 public surface로 본다.

- `/api/status`
- `/api/latest-data`
- `/api/get-tags`
- `/api/save-tags`
- `/api/run-scrap`

서버 `/` 라우트는 `web_viewer/index.html`을 찾도록 작성돼 있지만, 현재 저장소의 shipped 진입 HTML은 루트 `index.html`이다. 따라서 운영 문서에서는 서버 루트보다 `sns_hub.vbs` 기반 진입을 기준으로 설명한다.

## 검증 포인트

수집·정규화 로직을 바꾼 뒤에는 최소한 아래를 다시 확인한다.

- `pytest tests/unit`
- `pytest tests/contract`
- `pytest tests/e2e/test_api_security.py`
- `node utils/query-sns.mjs --help`
- 변경 범위가 Threads URL이면 `pytest tests/unit/test_migrate_threads_domain.py`

## 함께 현행화할 문서

- `README.md`
- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- `docs/development.md`
