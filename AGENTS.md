# 레포지토리 가이드라인

## 프로젝트 구조 및 모듈 구성

- 핵심 스크립트는 레포 루트에 위치: `thread_scrap.py`, `thread_scrap_single.py`, `linkedin_scrap.py`, `twitter_scrap.py`, `twitter_scrap_single.py`, `total_scrap.py`
- 런처와 API: `sns_hub.vbs`, `run_viewer.bat`, `stop_viewer.bat`, `server.py`, `index.html`, `web_viewer/`
- 출력 디렉토리: `output_threads/`, `output_twitter/`, `output_linkedin/`, `output_total/`

## 빌드·테스트·개발 명령어

- 런타임 설치: `pip install -r requirements.txt`
- Playwright 브라우저 설치: `playwright install chromium`
- 필요 시 프런트엔드 자산용 의존성 설치: `npm install`
- 로컬 실행:
  - `npm run start` → `python server.py`
  - `npm run view` → `wscript sns_hub.vbs`
  - `npm run stop` → `stop_viewer.bat`
- 크롤링:
  - `npm run scrap:threads`
  - `npm run scrap:linkedin`
  - `npm run scrap:all`
  - 예시: `python total_scrap.py --mode update`
- 유틸리티:
  - `node utils/query-sns.mjs --help`
  - `python migrate_threads_domain.py --dry-run`

## 에이전트 관련 메모

- 이 저장소는 더 이상 repo-local `.agent/` 플러그인 자산을 포함하지 않는다.
- 일부 Codex 클라이언트는 일부 슬래시 커맨드를 거부할 수 있다.
- `/commit`이 지원되지 않으면 자연어로 대체: `commit changes using the commit skill workflow`

## 참조 문서

- `README.md` — 현재 실행 진입점, 설치, 태그 동기화 개요
- `docs/development.md` — 플랫폼별 데이터 구조·URL 형식, 표준 스키마
- `docs/crawling_logic.md` — Producer/Consumer 흐름, 병합, 뷰어 연동

## 코딩·테스트·PR 기준

- Python: 4칸 들여쓰기, `snake_case`; JS: `camelCase`
- 데이터 순서·타입은 `utils/post_schema.py` 기준으로 유지
- JSON 편집 시 UTF-8 안전 워크플로우를 사용
- 검증은 변경 범위에 맞는 현재 테스트로 수행한다. 예:
  - `pytest tests/unit`
  - `pytest tests/contract`
  - `pytest tests/e2e/test_api_security.py`
  - `pytest tests/smoke`
- UI/태그/URL 정규화 변경 시 `node utils/query-sns.mjs --help`와 관련 unit test를 함께 확인한다.
- Conventional Commits 사용 (`feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ui`)
- 커밋 제목·본문은 기본적으로 한국어로 작성하고, type/scope 토큰은 영어를 유지한다.
