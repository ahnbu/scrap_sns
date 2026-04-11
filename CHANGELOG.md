# CHANGELOG

모든 Git 커밋 이력을 최신순으로 기록합니다. 새 커밋은 표 최상단에 추가합니다.

| 일시 | 유형 | 범위 | 변경내용 (목적 포함) |
|---|---|---|---|
| 2026-04-11 18:36 | fix | threads | 3층 스키마 게이트 적용 — extract_posts_from_node 표준 키 작성, merge_thread_items normalize, write 직전 _assert_threads_schema |
| 2026-04-11 18:35 | feat | schema | utils/post_schema.py + build_data_js.py + migrate_schema.py 복구 — Post 표준 스키마 단일 진실 원천과 재현 가능한 마이그레이션 스크립트 확립 |
| 2026-04-11 18:26 | chore | threads-schema | Threads 스키마 정비 문서·테스트·뷰어 데이터·스냅샷을 현재 상태로 반영 |
| 2026-04-01 18:49 | docs | frontmatter | - |
| 2026-04-01 18:07 | docs | CLAUDE.md | - |
| 2026-03-19 | chore | data | 수집 데이터 업데이트 — Threads 실패 이력 22건 추가, 웹 뷰어 데이터 631건으로 갱신 |
| 2026-03-19 | docs | docs | TDD E2E 테스트 구현 문서 추가 — 보안·품질 수정 검증 테스트 전략 기록 |
| 2026-03-19 | test | fixtures/snapshots | Threads 페이지 HTML 스냅샷 11건 추가 — E2E 파서 테스트용 고정 데이터 |
| 2026-03-19 | fix | inject_x_cookies | X(Twitter) 쿠키 주입 스크립트 추가 — persistent context에 세션 주입하여 비대화형 인증 갱신 지원 |
| 2026-03-19 | docs | guide | Codex CLI 커스텀 명령어·Oh My Ag 설정·Playwright 샌드박스 가이드 4건 추가 |
| 2026-03-19 | chore | gitignore | output_*, .pdca-status.json, .playwright-cli/ 추가 — 날짜별 산출물·런타임 상태·Playwright CLI 캐시 추적 제외 |
| 2026-03-18 | test | tests/e2e, tests/integration | 보안 수정 검증 + 웹 뷰어 기능 + 파서 통합 테스트 19건 추가 — 이전 세션 보안/품질 수정의 TDD Gap 해소 (S1~S10 API 보안, U1~U5 웹 뷰어, P1~P4 파서 파이프라인) |
| 2026-03-18 | fix | server | CORS 전체 허용 롤백 — 로컬 전용 도구 + file:// 사용 환경에서 CORS 제한 불필요 |
| 2026-03-18 | chore | pytest.ini | security, integration 마커 추가 — 테스트 카테고리 분류 체계화 |
| 2026-03-10 | chore | config | 프로젝트 설정 보완 — gitignore/pytest 마커/CLAUDE.md 필드 동기화/requirements.txt 생성 |
| 2026-03-10 | fix | viewer | XSS 취약점 수정 — escapeHtml 유틸 추가 및 inline handler 제거 |
| 2026-03-10 | fix | scrapers | 코드 품질 수정 — bare except 제거, 죽은 코드 정리, 브라우저 try/finally, input 가드 |
| 2026-03-10 | fix | server | 보안 전면 수정 — Path Traversal/CORS/Host/mode 검증/에러 노출 차단 |
| 2026-03-10 | docs | docs/rules | 프로젝트 운영 규칙(`GEMINI.md`) 및 TDD 실전 활용 가이드 생성 |
| 2026-03-10 | docs | docs/viewer | Web Viewer 10대 사용자 시나리오 테스트 완료 및 통합 보고서 작성 |
| 2026-03-10 | refactor | scrapers | LinkedIn, Twitter 파싱 로직 분리 및 TDD(Pytest) 아키텍처 전면 도입 |
| 2026-03-10 | feat | ui/server | Web Viewer UI 자동화 테스트(`tests/ui_verification.py`) 추가 및 Flask 서버 라우팅 고도화 |
| 2026-03-10 | refactor | threads | Threads 파싱 로직 모듈화(`utils/threads_parser.py`) 및 단위 테스트 적용 |
| 2026-03-10 | docs | docs | 핵심 기능 통합 테스트 보고서 최종 업데이트(`05_핵심_기능_테스트_통합_보고서.md`) |
| 2026-03-10 | refactor | root | 프로젝트 클린업 완료 — 18개 이상의 레거시 파일 및 폴더를 _backup_20260310/으로 이동 |
| 2026-03-10 | docs | docs/plans | P0 수정 구현 계획서(2026-03-10-p0-fixes.md) 추가 및 진단 보고서에 P0 수정 이력 업데이트 |
| 2026-03-10 | fix | scraper | argparse 전역 실행 제거 — parse_args()를 __main__ 블록으로 이동해 import 시 SystemExit 방지 |
| 2026-03-10 17:09 | chore | output-linkedin-twitter | 20260213 LinkedIn/Twitter 수집 산출물을 추가해 수집 결과를 저장소 이력으로 보존 |
| 2026-03-10 17:08 | chore | gitignore | 로컬 세션 상태 파일과 handoff 경로를 ignore에 추가하고 기존 tracked 개인 상태 파일을 추적에서 제거 |
| 2026-03-10 17:08 | docs | docs | 프로젝트 진단 및 검수 보고서를 추가해 현재 코드베이스의 P0 이슈와 검증 결과를 기록 |
| 2026-03-10 | chore | remote | 원격 저장소 URL을 새 주소(https://github.com/ahnbu/scrap_sns.git)로 업데이트 및 동기화 |
| 2026-03-10 | feat | tests | Playwright 기반 전 플랫폼 Smoke Test 및 Single Scrap 검증 코드 도입 |
| 2026-03-10 | docs | auth | SNS 세션 인증정보(Auth) 수동 갱신 가이드 문서 및 전용 스크립트 추가 |
| 2026-03-10 | fix | linkedin | 최신 레이아웃에 맞춰 게시물 목록 로케이터 수정 |
| 2026-03-10 | fix | server | Flask 서버의 정적 파일 서빙 경로 오류 및 Python 소스 BOM 인코딩 문제 해결 |
| 2026-03-10 | refactor | common | 공통 유틸리티 함수 통합 (utils/common.py 생성) |
| 2026-03-10 | refactor | scrapers | 핵심 스크래퍼 중복 로직 제거 (total, thread, linkedin, twitter) |
| 2026-03-10 | fix | config | package.json 오타 수정 (playwriter -> playwright-core) |
