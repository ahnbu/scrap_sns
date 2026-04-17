# 레포지토리 가이드라인

## 프로젝트 구조 및 모듈 구성
- 핵심 크롤러는 레포 루트에 위치: `thread_scrap.py`, `twitter_scrap.py`, `linkedin_scrap.py`, `substack_scrap_by_user.py`, `total_scrap.py`.
- 뷰어/백엔드: `server.py`, `index.html`, `web_viewer/`.
- 출력 디렉토리: `output_threads/`, `output_twitter/`, `output_linkedin/`, `output_total/`.
- 에이전트 시스템은 `.agent/` 하위에 위치:
  - `skills/` — 도메인 스킬·서브에이전트
  - `workflows/` — 실행 흐름 (`plan`, `coordinate`, `orchestrate`, `debug`, `review`, `tools`, `setup`)
  - `rules/` — 상시 적용 제약 규칙
  - `mcp.json` — MCP 도구·메모리 매핑

## 빌드·테스트·개발 명령어
- 런타임 설치: `pip install playwright python-dotenv` 및 `playwright install chromium`.
- 로컬 실행:
  - `npm run start` → `python server.py`
  - `npm run view` → `run_viewer.bat`
  - `npm run stop` → `stop_viewer.bat`
- 크롤링:
  - `npm run scrap:threads`
  - `npm run scrap:linkedin`
  - `npm run scrap:all`
  - 예시: `python total_scrap.py --mode update`
- 에이전트 설정 점검: `python .agent/scripts/validate_agent_config.py`.

## 에이전트 라우팅 우선순위
- 우선순위 엄격 적용: `rules` > `workflows` > `skills`.
- `rules/*.md` — 코딩 스타일·데이터 스키마·인코딩 안전·테스트·보안·mermaid 등 전역 제약.
- `workflows/*.md` — 멀티스텝·MCP 작업용 프로세스 계약.
- `skills/*/SKILL.md` — 집중 실행용 기능 팩.
- 일부 Codex 클라이언트는 슬래시 커맨드를 거부할 수 있다. 그 경우 텍스트 트리거를 사용한다.
- 권장 텍스트 트리거:
  - `omg-plan: <요청>`
  - `omg-review: <범위>`
  - `omg-coordinate: <요청>`
  - `omg-orchestrate: <요청>`
  - `omg-debug: <오류/컨텍스트>`
- 슬래시 커맨드가 지원되는 클라이언트에서는 `/omg-*`, `/prompts:*`를 선택적 별칭으로 사용 가능.
- `/commit`이 지원되지 않으면 자연어로 대체: `commit changes using the commit skill workflow`.
- 상세 운영 가이드: `.agent/README.md`.

## `omg` / `oh-my-ag` 트리거 규칙
- `omg`는 `oh-my-ag`의 별칭으로 처리한다.
- `omg-*:` 텍스트 트리거는 `oh-my-ag` 워크플로우 명시 호출로 처리한다.
- `omg` 또는 `oh-my-ag` 언급 시 에이전트 오케스트레이션 작업으로 해석하고 `.agent` 에셋을 활성화:
  - `.agent/skills/` 하위에서 매칭 스킬 선택
  - 멀티스텝·계획·리뷰·디버그·오케스트레이션 작업은 `.agent/workflows/` 사용
  - `.agent/rules/` 규칙을 상시 제약으로 적용
- 슬래시 커맨드 미지원 시 동일 의도를 자연어 워크플로우 호출로 실행한다.
- 모든 `omg`/`oh-my-ag` 요청에 대해 실행 전 사용자에게 다음을 명시 보고한다:
  - 선택된 `skill(s)` (없으면 `none`)
  - 선택된 `workflow` (없으면 `none`)
  - 적용된 핵심 `rule` 세트
- 실행 후 선택한 워크플로우·스킬이 실제 적용됐는지 확인하고, 미적용 시 이유를 설명한다.

## 참조 문서 (관련 코드 수정 시 함께 현행화)
- `docs/development.md` — 플랫폼별 데이터 구조·URL 형식 (Threads canonical: `www.threads.com`)
- `docs/crawling_logic.md` — 크롤링 필드 정의 및 흐름 상세

## 코딩·테스트·PR 기준
- Python: 4칸 들여쓰기, `snake_case`; JS: `camelCase`.
- 데이터 순서·타입은 `.agent/rules/data-schema.md` 준수.
- JSON 편집 시 `.agent/rules/encoding-safety.md` 준수 (UTF-8 안전 워크플로우만 허용).
- 테스트는 대상 테스트로 검증 (예: `python test_logic_refinement.py`, `python test_linkedin_image.py`) 후 스크래퍼 스모크 실행.
- Conventional Commits 사용 (`feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ui`). PR 설명에 검증 단계 포함, UI/데이터 변경 시 증거 첨부.
- 커밋 메시지 언어 정책:
  - 커밋 제목·본문은 기본적으로 한국어로 작성.
  - Conventional Commit type/scope 토큰은 영어 유지 (예: `fix`, `chore`, `feat`).
  - 기술 용어·제품명·라이브러리명·코드 식별자는 영어 허용.
