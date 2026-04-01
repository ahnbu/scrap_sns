---
title: "SNS 데이터 스키마 표준화 및 링크드인 스크래퍼 개선 보고서"
created: "2026-02-12 17:42"
---

# SNS 데이터 스키마 표준화 및 링크드인 스크래퍼 개선 보고서

**작성일**: 2026년 2월 12일
**대상**: SNS 데이터 수집 시스템 및 링크드인 스크래퍼 (`linkedin_scrap.py`)

## 1. 개요 (Background)
기존 SNS 수집 데이터는 플랫폼별로 필드 구조가 상이하고, 특히 링크드인의 경우 본문 이미지 누락 및 `username` 필드 부재 등의 데이터 무결성 문제가 발견됨. 이를 해결하기 위해 데이터 스키마를 표준화하고 수집 로직을 고도화함.

## 2. 데이터 스키마 표준화 (Standardization)
에이전트와 개발자가 준수해야 할 **표준 데이터 규격**을 정의하고 규칙 파일로 명문화함.

### 2.1 표준 필드 및 정렬 순서
1. `sequence_id`, 2. `platform_id`, 3. `sns_platform`, 4. `username`, 5. `display_name`, 6. `full_text`, 7. `media`, 8. `url`, 9. `created_at`, 10. `date`, 11. `crawled_at`, 12. `source`, 13. `local_images`

### 2.2 규칙 반영
- `.agent/rules/data-schema.md` 생성: AI 에이전트가 코딩 시 위 규격을 `always_on`으로 준수하도록 강제.
- `docs/01-plan/features/unified_data_schema.plan.md`: PDCA 기반의 표준화 계획 수립.

## 3. 링크드인 스크래퍼 개선 (Implementation)
`linkedin_scrap.py`의 고질적인 데이터 누락 문제를 해결하기 위해 수집 로직을 개선함.

### 3.1 이미지 추출 로직 고도화 (Recursive Search)
- **문제**: 링크드인 API(Voyager)의 응답 구조가 복잡하여 고정된 경로로는 이미지를 놓치는 현상 발생.
- **해결**: `find_images_recursively` 함수를 도입하여 JSON 내의 모든 `VectorImage` 및 `artifacts`를 재귀적으로 탐색. 가장 고해상도의 이미지 URL을 자동 조립하도록 구현.

### 3.2 URN 및 사용자 정보 개선
- `user_link`에서 실제 사용자의 고유 ID를 추출하여 `username` 필드에 자동 할당.
- `created_at` 정보에서 날짜(`date`)를 추출하는 로직 보강.

### 3.3 데이터 업데이트 정책
- 기존 데이터가 있더라도 `media` 필드가 비어있는 경우, 신규 수집 시 데이터를 업데이트하도록 허용하여 데이터 품질을 높임.

## 4. 검증 결과 (Verification)
실제 API 응답 데이터(`response.json`)를 대상으로 개선된 로직을 테스트함.

- **이미지 추출 성공**: 사용자가 지목한 게시글을 포함하여 다수의 포스트에서 고화질 이미지 URL 추출 성공.
- **로컬 저장 확인**: `docs/linkedin_saved/test_images/`에 실제 이미지를 다운로드하여 유효성 검증 완료.
- **데이터 마이그레이션**: 기존에 잘못 생성된 `linkedin_py_full_20260212.json` 파일을 표준 규격에 맞게 변환 완료.

## 5. 향후 과제 (Next Steps)
- 트위터, 스레드 등 타 플랫폼 스크래퍼에도 동일한 표준 규격 적용.
- `total_scrap.py`의 병합 로직에서 표준 필드 순서 강제 로직 내장.
- 이미지 로컬 다운로드(`local_images`) 기능의 안정화.
