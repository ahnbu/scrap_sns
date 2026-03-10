# SNS Scrap 프로젝트 운영 규칙 (GEMINI.md)

## 🎯 핵심 원칙
- **파싱과 제어의 분리**: 브라우저 제어(Playwright)와 데이터 추출(Parser) 로직은 엄격히 분리한다. 모든 추출 로직은 `utils/*_parser.py`에 위치시킨다.
- **TDD(Test-Driven Development) 필수 적용**: 파싱 로직 수정 시 반드시 `tests/unit/test_*_parser.py`를 먼저 실행하여 검증한다.
- **데이터 정합성 유지**: 모든 플랫폼 파서는 Web Viewer 호환을 위해 다음 표준 필드를 반드시 포함해야 한다:
  - `sequence_id`, `platform_id`, `sns_platform`, `username`, `full_text`, `media` (URL 리스트), `url`, `created_at`, `crawled_at`.

## 🛠️ 개발 및 운영 워크플로우
1. **TDD 사이클**: Red(Fixture 준비/실패 확인) → Green(로직 수정/성공 확인) → Refactor(통합).
2. **스냅샷 디버깅**: 스크랩 실패 시 `tests/fixtures/snapshots/`의 데이터를 Fixture로 활용한다.
3. **인코딩 안전**: JSON/MD 저장 시 반드시 `utf-8-sig` 인코딩을 사용하고, JSON 저장 시 `ensure_ascii=False`를 설정하여 이모지 및 다국어 유실을 방지한다.

## 📂 파일 및 경로 규칙
- **Parser**: `utils/{platform}_parser.py`
- **Tests**: `tests/unit/test_{platform}_parser.py`
- **Auth**: `auth/auth_{platform}.json` (세션 정보 포함, 외부에 노출 금지)
- **Snapshots**: `tests/fixtures/snapshots/{platform}/` (최신 10개 유지)

## ⚠️ 보안 및 안정성 (Anti-Ban)
- **계정 보호**: 파싱 로직 수정 시 브라우저를 반복 실행하지 말고 Snapshot 파일을 활용한다.
- **속도 제한**: 실제 스크랩 시 요청 간 최소 3~5초의 `asyncio.sleep` 또는 `time.sleep`을 부여하여 IP/계정 차단을 예방한다.
- **인증 갱신**: 세션 만료 시 `renew_auth.py` 등 지정된 스크립트를 통해 인증 정보를 수동 갱신하며, `auth/` 폴더 내 파일을 직접 수정하는 것을 지양한다.
