# tests 지침

## 범위

- Python unit/integration/e2e/smoke, Node 기반 viewer/CLI 테스트, fixture와 golden sample을 다룬다.
- 테스트는 운영 JSON과 브라우저 뷰어 계약을 보호하는 역할이다.

## 구조

- `unit/`: parser, schema, viewer helper, utility 단위 테스트
- `integration/`: 서버 API, 수집 파이프라인, 런처, 태그 관리 연동 테스트
- `contract/`: 표준 schema 계약 테스트
- `e2e/`: Flask 서버와 Playwright 기반 실제 화면 테스트
- `smoke/`: 플랫폼 수집 smoke 테스트
- `fixtures/golden/`: git에 포함해도 되는 승격 샘플
- `fixtures/snapshots/`: 자동 생성 HTML 스냅샷, 직접 테스트 기준으로 사용하지 않음

## 변경 규칙

- 새 샘플이 필요하면 `fixtures/snapshots/`를 직접 참조하지 말고 필요한 최소 샘플을 `fixtures/golden/<platform>/`로 승격한다.
- 웹 뷰어 테스트는 API만 확인하는 테스트와 실제 DOM/Playwright 테스트를 구분한다.
- 서버 테스트는 가능한 한 fixture server나 Flask app test client를 사용하고, 5000번 운영 서버에 의존하지 않는다.
- 수집 smoke 테스트는 외부 인증과 네트워크 상태 영향을 받으므로 일반 unit 검증과 같은 안정성으로 취급하지 않는다.
- 테스트가 현재 제품 계약을 틀리게 표현하면 테스트만 고치지 말고 문서와 코드 계약을 함께 확인한다.

## 검증 선택 기준

- schema/parser/normalization 변경: `pytest tests/unit tests/contract`
- 서버 API 변경: `pytest tests/integration tests/e2e/test_api_security.py`
- 뷰어 DOM/상호작용 변경: 관련 `tests/unit/test_web_viewer_*.py`와 `pytest tests/e2e/test_core_ui.py`
- 수집 파이프라인 변경: 관련 플랫폼 integration/smoke 테스트와 최신 output/viewer 반영 확인

## 금지

- 실패하는 테스트를 삭제하거나 기대값을 낮춰서 통과시키지 않는다.
- `tests/fixtures/snapshots/`의 대형 HTML을 새 테스트의 직접 입력으로 추가하지 않는다.
- 외부 서비스 인증이 필요한 테스트를 기본 빠른 검증 경로로 끌어올리지 않는다.
