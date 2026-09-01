<!-- 생성물: AGENTS.md의 사본. 정본은 같은 폴더의 AGENTS.md이며 수정은 그쪽에서 한다.
     갱신: node ~/.claude/scripts/sync-project-rules.mjs --write
     @AGENTS.md 참조를 쓰지 않는 이유: 하위 폴더에서 작업하면 상위 CLAUDE.md의 import가
     전개되지 않아 규칙이 통째로 유실된다(2026-08-29 실측). -->

# 레포지토리 가이드라인

## 프로젝트 구조 및 모듈 구성

- 핵심 스크립트는 레포 루트에 위치: `thread_scrap.py`, `thread_scrap_single.py`, `linkedin_scrap.py`, `twitter_scrap.py`, `twitter_scrap_single.py`, `total_scrap.py`
- 런처와 API: `sns_hub.vbs`, `run_viewer.bat`, `stop_viewer.bat`, `scrap_sns_server.py`, `index.html`, `web_viewer/`
- 출력 디렉토리: `output_threads/`, `output_twitter/`, `output_linkedin/`, `output_total/`

## 설계 원칙

- 브라우저 제어와 파싱 로직을 분리한다. 추출 로직은 `utils/*_parser.py`에 둔다.
- 파서나 URL 정규화 로직을 바꿀 때는 관련 unit test를 먼저 확인하고, 수정 후 다시 실행한다.

## 빌드·테스트·개발 명령어

- 런타임 설치: `pip install -r requirements.txt`
- Playwright 브라우저 설치: `playwright install chromium`
- 필요 시 프런트엔드 자산용 의존성 설치: `npm install`
- 로컬 실행:
  - `npm run start` → `python scrap_sns_server.py`
  - `npm run restart` → `scripts/restart_viewer_server.ps1` (서버만 재시작, 창·탭 없음)
  - `npm run view` → `wscript sns_hub.vbs` (서버 재시작 + 브라우저 탭)
  - `npm run stop` → `stop_viewer.bat` (대화형 `pause`가 있어 사용자용이다. 에이전트가 서버를 내릴 일은 `npm run restart`로 갈음한다)
- 크롤링:
  - `npm run scrap:threads`
  - `npm run scrap:linkedin`
  - `npm run scrap:all`
  - 예시: `python total_scrap.py --mode update`
- 유틸리티:
  - `node utils/query-sns.mjs --help`
  - `python migrate_threads_domain.py --dry-run`
  - `python migrate_schema.py` — 기존 데이터의 스키마 점검
  - `node scripts/lilys_library.mjs list` / `node scripts/livewiki_library.mjs list` — 외부 요약 라이브러리 수집
  - `node scripts/build_external_summaries.mjs` — 위 두 산출물을 합쳐 `web_viewer/sns_external_summaries.json` 생성

## 에이전트 관련 메모

- 이 저장소는 더 이상 repo-local `.agent/` 플러그인 자산을 포함하지 않는다.
- 일부 Codex 클라이언트는 일부 슬래시 커맨드를 거부할 수 있다.
- `/commit`이 지원되지 않으면 자연어로 대체: `commit changes using the commit skill workflow`

## 참조 문서

- `README.md` — 현재 실행 진입점, 설치, 태그 동기화 개요
- `docs/architecture.md` — 플랫폼별 데이터 구조·수집 흐름, 표준 스키마, 병합, 뷰어·API surface

## 작업별 정본 위치

- Post 스키마 변경: `utils/post_schema.py`
- API 메타데이터 변경: `utils/post_meta.py`, `scrap_sns_server.py`
- Threads URL 정규화: `utils/post_schema.py`, `utils/post_meta.py`, `utils/query-sns.mjs`, `web_viewer/script.js`
- 뷰어 태그·상태 변경: `web_viewer/script.js`, `web_viewer/sns_tags.json`, `web_viewer/sns_tag_catalog.json`, `web_viewer/sns_user_metadata.json`
- 수집 파이프라인 변경: 플랫폼별 수집기와 `total_scrap.py`
- LinkedIn 참여지표: `utils/linkedin_metrics.py`(추출·대상 선정 정본), `linkedin_metric_single.py`(상시 consumer), `scripts/linkedin_metric_backfill.py`(백필). 지표는 로그인 경로로 얻을 수 없어 비로그인 공개 페이지에서 읽는다
- 로컬 SNS 조회: 원천 JSON 직접 조회보다 `node utils/query-sns.mjs` 우선

## 영구 데이터 surface

- 플랫폼 출력: `output_threads/python/*`, `output_linkedin/python/*`, `output_twitter/python/*`
- 통합 출력: `output_total/total_full_YYYYMMDD.json`
- 실패 이력: `scrap_failures_threads.json`, `scrap_failures_twitter.json`, `scrap_failures_linkedin.json`
- 뷰어 상태: `web_viewer/sns_tags.json`, `web_viewer/sns_tag_catalog.json`, `web_viewer/sns_user_metadata.json`, browser `localStorage`
- 외부 요약 매핑: `web_viewer/sns_external_summaries.json` — `scripts/build_external_summaries.mjs` 산출물이며 손으로 고치지 않는다. 중간 산출물 `output_external/*.json`은 재생성 가능하므로 git 무시 대상이다
- 인증 런타임 정본: `C:/Users/ahnbu/.config/auth/`; repo `auth/`는 정본으로 보지 않는다.

## 데이터 identity 규칙

- `sequence_id`는 통합 파일 안에서 다시 부여되는 로컬 순서값이며 durable identity로 쓰지 않는다.
- LinkedIn 수집 배열 순서는 화면 순서와 무관하다. 순서 관련 변경 전 `docs/architecture.md`의 LinkedIn 수집 순서 항목을 확인한다.
- 별표, 숨김, 메모는 `post_key` 기준으로 `web_viewer/sns_user_metadata.json`에 저장한다.
- `canonical_url`은 원문 열기와 legacy migration 보조값이며, 사용자 상태의 주 key가 아니다.
- 의미 있는 뷰어 상태는 file-backed JSON에 남기고, `localStorage`는 cache 또는 migration 보조로 본다.
- X(Twitter)는 리다이렉트와 실제 사용자명 보정 때문에 URL과 본문이 단순 1:1이 아닐 수 있다.

## 수집 데이터 수정 규칙

- `output_total/total_full_YYYYMMDD.json`은 downstream 통합 산출물이다.
- LinkedIn 본문·메타데이터를 durable하게 바꾸려면 최신 `output_linkedin/python/linkedin_py_full_*.json`도 함께 맞춘 뒤 통합본을 재생성한다.
- 수집·병합 변경 완료 기준은 프로세스 성공이 아니라 upstream full 파일, downstream total 파일, 웹 뷰어 표시가 일치하는 것이다.

## 코딩·테스트·PR 기준

- Python: 4칸 들여쓰기, `snake_case`; JS: `camelCase`
- 데이터 순서·타입은 `utils/post_schema.py` 기준으로 유지
- JSON 편집 시 UTF-8 안전 워크플로우를 사용
- 테스트는 `tests/fixtures/snapshots/`의 자동 생성 파일을 직접 참조하지 않는다.
- 필요한 샘플은 `tests/fixtures/golden/<platform>/`으로 승격해 git에 포함한다.
- 검증은 변경 범위에 맞는 현재 테스트로 수행한다. 예:
  - `pytest tests/unit`
  - `pytest tests/contract`
  - `pytest tests/e2e/test_api_security.py`
  - `pytest tests/smoke`
- CLI·서버 검색·태그·URL 정규화 변경 시 `node utils/query-sns.mjs --help`와 관련 unit test를 함께 확인한다.
- `scrap_sns_server.py`, `index.html`, `web_viewer/` 변경 후에는 `npm run restart`로 5000번 서버를 재시작한 뒤 검증한다. 5000번 포트를 점유한 `scrap_sns_server.py`만 종료하고, 서버가 이미 정상 응답 중이어도 항상 새로 시작한다. `npm run view`·`wscript sns_hub.vbs`는 브라우저 탭까지 여는 사용자용 진입점이라, 사용자가 화면을 보겠다고 한 경우에만 쓴다.
- 검색·필터·태그·정렬 등 웹 뷰어 사용자 경험이 바뀌는 변경은 API/CLI 결과만으로 완료 판단하지 않는다. 실제 `http://localhost:5000/` 화면에서 사용자가 하는 순서대로 입력·클릭해 결과를 확인하고, 결과 화면 캡처를 증거로 남긴다. 단 창을 띄우지 않는다 — `scripts/verify_*.mjs`처럼 `_shared/hidden-browser-verify-runner.mjs`를 쓰고, 창이 꼭 필요한 예외는 사유를 적는다.
- SNS 수집·병합·이미지 반영 로직 변경 시 완료 기준은 최신 `output_total` 생성이 아니라 저장 데이터와 뷰어 반영의 일치다. 최소 검증은 `merge_results()` → `download_images()` → `validate_local_image_links()` 통과, 대상 ID가 최신 `output_total/total_full_YYYYMMDD.json`에 존재, 웹 뷰어 상단 총건수와 최신 JSON 게시글 수가 일치, 그리고 실제 뷰어 화면에서 대상 게시글이 확인되는 것이다.
- 뷰어 결과가 사용자 제보와 다를 때는 최신 `output_total/total_full_YYYYMMDD.json` 경로·게시글 수, 웹 뷰어 상단 총건수, 실제 검색 화면의 표시 카드 수, 활성 플랫폼/태그/숨김 필터 상태를 함께 확인한다.
- Conventional Commits 사용 (`feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ui`)
- 커밋 제목·본문은 기본적으로 한국어로 작성하고, type/scope 토큰은 영어를 유지한다.
