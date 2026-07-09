# scripts 지침

## 범위

- 운영 보조 스크립트, 진단 스크립트, 인증 런타임 보조 도구, 일회성 migration/복구 도구를 다룬다.
- 반복 실행되는 결정적 로직은 자연어 절차보다 스크립트로 남긴다.

## 구조

- `auth_runtime/`: X/LinkedIn/Threads 인증 런타임 보조와 검증
- `diagnostics/`: LinkedIn 등 특정 문제 재현용 probe
- `cleanup_old_output_json.mjs`: 운영 JSON 정리 dry-run/apply
- `fix_threads_redirect_alias.mjs`, `diagnose_threads_redirect_alias.mjs`: Threads alias 진단과 보정
- `linkedin_*`: OpenCLI/shadow 수집, 비교, media audit 보조
- `verify_*`: headless UI/API 확인 스크립트

## 변경 규칙

- 삭제나 정리 스크립트는 dry-run을 기본값으로 두고, 적용 모드는 명시 플래그로 분리한다.
- `.sh`를 새로 만들지 않는다. 기본은 `.mjs`, Windows 시스템 API가 필요하면 `.ps1`, CommonJS가 필요하면 `.js`를 사용한다.
- 인증 런타임 경로는 `utils/auth_paths.py`와 문서의 `AUTH_HOME` 계약을 따른다.
- output JSON을 바꾸는 스크립트는 영향 대상, 재실행 방법, 검증 방법을 문서나 출력에 남긴다.
- 진단용 스크립트는 성공/실패 기준을 stdout에 명확히 남기고, 비밀값은 출력하지 않는다.

## 검증

- Node 스크립트 변경: 관련 `tests/unit/*.mjs` 또는 스크립트 자체 `--dry-run` 실행
- 인증 런타임 변경: 해당 `tests/integration/test_auth_runtime_sync.py`와 관련 probe 실행
- Threads alias 보정 변경: `pytest tests/unit/test_migrate_threads_domain.py tests/unit/test_total_scrap_redirect_alias.py`
- UI 확인 스크립트 변경: headless 실행 후 결과 로그와 필요 시 화면 캡처 확인

## 금지

- raw 삭제 명령이나 recursive delete를 스크립트에 직접 넣지 않는다. 안전한 삭제 도구나 명시 dry-run 경로를 둔다.
- 수집 output 정리 스크립트가 현재 날짜 파일이나 최신 통합본을 암묵적으로 삭제하게 만들지 않는다.
- 진단 스크립트에 계정 토큰, 쿠키, 개인 경로 값을 출력하지 않는다.
