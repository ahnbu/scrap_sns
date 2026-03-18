
## [2026-03-18]

### Added
- **보안 테스트(S1~S10)**: Flask API Path Traversal 차단, mode 검증, save-tags 입력 검증, 에러 정보 노출 차단 테스트 10건
- **웹 뷰어 E2E(U1~U5)**: XSS 방어, 검색 필터링, 즐겨찾기 지속성, 콘솔 에러, 플랫폼 필터 cross-check 5건
- **파서 통합 테스트(P1~P4)**: Threads/LinkedIn/Twitter 전체 파이프라인 + 이모지 안전 검증 4건
- **테스트 인프라**: conftest.py (Flask test client + console 수집 fixture), XSS payload fixture, integration 폴더

### Changed
- **CORS 전체 허용 롤백**: 로컬 전용 도구 + file:// 사용 환경에서 CORS 제한이 불필요하므로 `CORS(app)`으로 단순화
- **pytest.ini**: `security`, `integration` 마커 추가

## [2026-03-10]

### Changed
- **Remote Repository**: 원격 저장소 URL을 새 주소(https://github.com/ahnbu/scrap_sns.git)로 업데이트 및 동기화

### Added
- **통합 테스트 체계**: Playwright 기반 전 플랫폼(Threads, LinkedIn, X) Smoke Test 및 Single Scrap 검증 코드 도입
- **인증 가이드**: SNS 세션 인증정보(Auth) 수동 갱신 가이드 문서(docs/auth_renewal_guide.md) 및 전용 스크립트 추가
- **Twitter Smoke Test**: Persistent Context 기반 트위터 세션 유효성 자동 검증 추가

### Fixed
- **LinkedIn Locator**: 최신 레이아웃에 맞춰 게시물 목록 로케이터(.entity-result__content-container) 수정
- **Server Routing**: Flask 서버의 정적 파일 서빙 경로 오류 및 Python 소스 BOM 인코딩 문제 해결

## [2026-03-10]

### Changed
- **Remote Repository**: 원격 저장소 URL을 새 주소(https://github.com/ahnbu/scrap_sns.git)로 업데이트 및 동기화
### Refactor
- **common**: 공통 유틸리티 함수 통합 (utils/common.py 생성)
- **scrapers**: 핵심 스크래퍼 중복 로직 제거 (	otal, 	hread, linkedin, 	witter)
- **config**: package.json 오타 수정 (playwriter -> playwright-core)
# CHANGELOG

모든 Git 커밋 이력을 최신순으로 기록합니다. 새 커밋은 표 최상단에 추가합니다.

| 일시 | 유형 | 범위 | 변경내용 (목적 포함) |
|---|---|---|---|
| 2026-03-10 | docs | docs/rules | 프로젝트 운영 규칙(`GEMINI.md`) 및 TDD 실전 활용 가이드 생성 |
| 2026-03-10 | docs | docs/viewer | Web Viewer 10대 사용자 시나리오 테스트 완료 및 통합 보고서 작성 |
| 2026-03-10 | refactor | scrapers | LinkedIn, Twitter 파싱 로직 분리 및 TDD(Pytest) 아키텍처 전면 도입 |
| 2026-03-10 | feat | ui/server | Web Viewer UI 자동화 테스트(`tests/ui_verification.py`) 추가 및 Flask 서버 라우팅 고도화 |
| 2026-03-10 | refactor | threads | Threads 파싱 로직 모듈화(`utils/threads_parser.py`) 및 단위 테스트 적용 |
| 2026-03-10 | docs | docs | 핵심 기능 통합 테스트 보고서 최종 업데이트(`05_핵심_기능_테스트_통합_보고서.md`) |
| 2026-03-10 | refactor | root | 프로젝트 클린업 완료 — 18개 이상의 레거시 파일 및 폴더를 _backup_20260310/으로 이동하여 루트 디렉토리 슬림화 |
| 2026-03-10 | docs | docs/plans | P0 수정 구현 계획서(2026-03-10-p0-fixes.md) 추가 및 진단 보고서에 P0 수정 이력 업데이트 |
| 2026-03-10 | fix | scraper | argparse 전역 실행 제거 — parse_args()를 __main__ 블록으로 이동해 import 시 SystemExit 방지 |
| 2026-03-10 17:09 | chore | output-linkedin-twitter | 20260213 LinkedIn/Twitter 수집 산출물을 추가해 수집 결과를 저장소 이력으로 보존 |
| 2026-03-10 17:08 | chore | gitignore | 로컬 세션 상태 파일과 handoff 경로를 ignore에 추가하고 기존 tracked 개인 상태 파일을 저장소 추적에서 제거 |
| 2026-03-10 17:08 | docs | docs | 프로젝트 진단 및 검수 보고서를 추가해 현재 코드베이스의 P0 이슈와 검증 결과를 기록 |


