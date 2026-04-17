# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project Overview

개인 SNS 저장 게시물 수집기. 현재 활성 플랫폼은 Threads, LinkedIn, X(Twitter)이며, Python 스크래퍼와 Flask API, 바닐라 JS 웹 뷰어로 구성된다.

## Commands

### 런처와 서버

```bash
npm run view     # 권장 진입. wscript sns_hub.vbs -> python server.py -> root index.html
npm run start    # python server.py
npm run stop     # stop_viewer.bat
```

`run_viewer.bat`는 보조 런처다. 현재 shipped HTML 진입점은 레포 루트 `index.html`이며, `server.py`는 API 제공이 중심이다.

### 스크래핑 실행

```bash
python total_scrap.py --mode update
python total_scrap.py --mode all

python thread_scrap.py --mode update
python thread_scrap_single.py
python linkedin_scrap.py --mode update
python twitter_scrap.py --mode update
python twitter_scrap_single.py
```

### 인증 갱신

```bash
python renew_auth.py
python renew_twitter_auth.py
```

### 유틸리티

```bash
node utils/query-sns.mjs --help
python -m utils.build_data_js
python migrate_schema.py --target "output_total/total_full_*.json"
python migrate_schema.py --target "output_total/total_full_*.json" --apply
python migrate_threads_domain.py --dry-run
```

### 테스트

```bash
pytest --collect-only
pytest tests/unit
pytest tests/contract
pytest tests/e2e/test_api_security.py
pytest tests/smoke
```

## Architecture

### 데이터 플로우

1. `thread_scrap.py`, `linkedin_scrap.py`, `twitter_scrap.py`가 플랫폼별 목록을 수집한다.
2. Threads와 X는 `thread_scrap_single.py`, `twitter_scrap_single.py`가 상세 본문과 미디어를 보강한다.
3. `total_scrap.py`가 최신 full 파일을 병합해 `output_total/total_full_YYYYMMDD.json`을 만든다.
4. `python -m utils.build_data_js`가 필요 시 `web_viewer/data.js`를 재생성한다.
5. 뷰어는 루트 `index.html`에서 `/api/latest-data`와 `web_viewer/data.js`를 읽어 렌더링한다.

### 핵심 파일

- `total_scrap.py`: 전체 플랫폼 병렬 실행, 병합, 로그 정리
- `thread_scrap.py`, `thread_scrap_single.py`: Threads Producer/Consumer
- `linkedin_scrap.py`: LinkedIn 저장 게시물 수집
- `twitter_scrap.py`, `twitter_scrap_single.py`: X Producer/Consumer
- `server.py`: `/api/status`, `/api/latest-data`, `/api/get-tags`, `/api/save-tags`, `/api/run-scrap`
- `index.html`: 현재 shipped 뷰어 진입점
- `web_viewer/script.js`: 렌더링, 태그, 자동 태그, URL 정규화
- `utils/post_schema.py`: Post 표준 스키마 단일 진실 원천
- `utils/query-sns.mjs`: 로컬 통합 데이터 조회 CLI
- `migrate_schema.py`, `migrate_threads_domain.py`: 레거시 데이터 정리 도구

## Standard Post Schema

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
```

- 필수 필드: `sns_platform`, `username`, `url`, `created_at`
- `normalize_post()`는 레거시 필드 rename과 Threads URL 합성을 담당한다.
- Threads canonical URL은 `https://www.threads.com/@{username}/post/{code}`다.

## Viewer and Tag State

- 태그/강조/자동 태그 규칙은 `localStorage`와 `web_viewer/sns_tags.json`을 함께 사용한다.
- 레거시 태그 키는 `web_viewer/script.js`에서 `migrateLegacyTagKeys()`로 `.threads.com` canonical에 매핑한다.
- 뷰어에서 스크래핑 실행 버튼을 누르면 `/api/run-scrap`가 `total_scrap.py`를 foreground로 실행하고 최근 로그를 반환한다.

## Output Surfaces

```text
output_threads/python/
output_linkedin/python/
output_twitter/python/
output_total/
  total_full_YYYYMMDD.json
web_viewer/
  data.js
  sns_tags.json
```

## Platform Notes

- Threads: `www.threads.com`이 정본 도메인이다. `threads.net`, `/t/{code}`는 레거시 alias로만 취급한다.
- LinkedIn: 저장 게시물은 Voyager GraphQL 응답을 기준으로 파싱한다.
- X(Twitter): 상세 수집 시 실제 이동 URL과 `real_user` 기준으로 URL이 보정될 수 있다. 인기 페이지 리다이렉트 등으로 동일 본문 중복이 생길 수 있다.

## Reference Docs

- `docs/development.md`: 플랫폼별 데이터 구조, URL 규칙, 영구화 surface
- `docs/crawling_logic.md`: Producer/Consumer 흐름, 병합, 뷰어 연동

## Working Notes

- `tmp/`, `temp_code/`, `temp-code/`는 실험용 폴더다.
- 문서가 코드와 어긋나면 README보다 이 파일을 우선하지 말고, 실제 코드와 테스트를 먼저 확인해 문서를 함께 고친다.
