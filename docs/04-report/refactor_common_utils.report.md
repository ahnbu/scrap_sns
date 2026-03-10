# PDCA Report: Common Utility Refactoring (refactor_common_utils)

## 1. 작업 개요
- **목적**: `scrap_sns` 프로젝트 내의 중복된 유틸리티 함수들을 통합하고 기술 부채(`package.json` 오타 등)를 해결함.
- **완료 일자**: 2026-03-10
- **수행 도구**: Python Script, Shell Command, Pytest

## 2. 주요 작업 내역
### ✅ 유틸리티 모듈화 및 통합 (`utils/common.py`)
- `load_json`, `save_json`, `clean_text`, `reorder_post`, `format_timestamp`, `parse_relative_time`을 하나의 파일로 통합.
- 텍스트 정제 시 제외 패턴(`exclude_list`) 지원 및 메타데이터 필터링 강화.
- JSON 로드 시 `utf-8-sig` 인코딩을 기본 지원하여 호환성 문제 해결.

### ✅ 패키지 설정 수정 (`package.json`)
- `"playwriter"` 오타를 제거하고 `"playwright-core"` 단일 의존성 체계로 정합성 확보.

### ✅ 코드 슬림화 (Core Scrapers)
- `total_scrap.py`, `thread_scrap.py`, `linkedin_scrap.py`, `twitter_scrap.py` 파일에서 중복 함수 정의 제거.
- 공통 유틸리티 임포트 방식으로 전환하여 유지보수 포인트 일원화.

## 3. 검증 결과 (Check)
- **Unit Test**: `tests/unit/test_parsers.py` 내의 4개 테스트 케이스(텍스트 정제, 상대 시간 파싱 등) 전원 통과(**100% PASSED**).
- **Import Check**: 핵심 스크래퍼 파일들이 오류 없이 정상 로딩됨을 확인.
- **Data Integrity**: 기존과 동일한 데이터 구조 및 정제 품질 유지 확인.

## 4. 기대 효과
- **유지보수성 향상**: 로직 변경 시 `utils/common.py` 한 곳만 수정하면 전체에 반영됨.
- **코드 양 감소**: 중복 코드 제거로 인해 주요 파일의 가독성 향상.
- **데이터 일관성**: 모든 스크래퍼가 동일한 텍스트 정제 및 필드 순서 정책을 따르게 됨.

## 5. 향후 과제
- 백업 폴더(`_backup_...`) 및 마이그레이션 스크립트에도 공통 유틸리티 적용 확대 필요.
- 공통 유틸리티 내에 로깅(logging) 및 재시도(retry) 로직 추가 검토.
