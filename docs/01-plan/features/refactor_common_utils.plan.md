# PDCA Plan: Common Utility Refactoring (refactor_common_utils)

## 1. 개요
`scrap_sns` 프로젝트 내의 중복된 유틸리티 함수들을 `utils/common.py`로 통합하고, `package.json`의 오타를 수정하여 프로젝트의 유지보수성을 높이고 기술 부채를 해결합니다.

## 2. 현재 문제점 (As-Is)
- **중복 로직**: `reorder_post`, `clean_text`, `load_json`, `save_json`, `parse_relative_time`, `format_timestamp` 등이 최소 4개 이상의 파일에 중복 구현됨.
- **파편화된 정책**: 텍스트 정제 및 필드 순서 정책이 파일마다 미세하게 달라 데이터 일관성 부족.
- **잘못된 의존성**: `package.json`에 `playwriter`라는 오타가 포함되어 설치 시 혼선 발생.
- **비대한 파일**: 개별 스크래퍼 파일에 유틸리티 로직이 포함되어 가독성 저해.

## 3. 목표 (To-Be)
- **모듈화**: 모든 공통 기능을 `utils/common.py` 단일 지점으로 통합.
- **슬림화**: 각 스크래퍼 파일의 중복 코드를 제거하여 코드 양 30% 이상 감소.
- **정규화**: 일관된 텍스트 정제 및 데이터 스키마 정렬 보장.
- **안정성**: 중앙 집중식 에러 핸들링 및 로깅 적용 기반 마련.

## 4. 실행 계획 (Tasks)
- [ ] **Step 1: 유틸리티 통합 구현**
    - `utils/common.py` 생성
    - `reorder_post`, `clean_text`, `load_json`, `save_json`, `parse_relative_time`, `format_timestamp` 통합 구현
    - `utils/__init__.py`에서 공통 함수 익스포트 처리
- [ ] **Step 2: 의존성 및 설정 수정**
    - `package.json`의 `playwriter` 오타 수정 및 불필요한 의존성 제거
- [ ] **Step 3: 스크래퍼 리팩토링 (Surgical Updates)**
    - `linkedin_scrap.py` 적용
    - `thread_scrap.py` 적용
    - `twitter_scrap.py` 적용
    - `total_scrap.py` 및 기타 스크립트 적용
- [ ] **Step 4: 검증 및 테스트**
    - `tests/unit/test_parsers.py` 등 기존 테스트 실행
    - 공통 유틸리티용 신규 유닛 테스트 추가
    - 전체 스크래핑 파이프라인 동작 확인

## 5. 예상 결과
- 코드 중복 제거로 인한 유지보수 비용 급감.
- 신규 스크래퍼 추가 시 개발 속도 향상.
- 데이터 스키마 및 정제 로직의 강력한 일관성 확보.
