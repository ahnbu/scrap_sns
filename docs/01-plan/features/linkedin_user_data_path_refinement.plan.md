---
template: plan
version: 1.0
description: 링크드인 사용자 데이터 저장 경로 및 파일명 규칙 개선
---

# linkedin_user_data_path_refinement 기획서

> **요약**: `linkedin_scrap_by_user.py`에서 생성되는 데이터 저장 경로를 간소화하고, 파일명에 사용자 ID를 포함하여 식별성을 높입니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.0.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-08
> **상태**: 진행 중

---

## 1. 개요

### 1.1 목적

현재 `output_linkedin_user/{user_id}/python/` 경로에 저장되는 데이터를 `output_linkedin_user/{user_id}/`로 상위 이동시키고, 파일명에 `{user_id}`를 포함하여 관리 편의성을 개선합니다.

### 1.2 배경

- 모든 작업을 Python으로 수행하므로 경로상에 `python` 폴더가 불필요함.
- 파일명만 보고도 어떤 사용자의 데이터인지 즉시 확인 가능해야 함.
- 업데이트(`update`) 폴더의 파일명 규칙도 일관성 있게 변경 필요.

### 1.3 관련 문서

- 참고 자료: `linkedin_scrap_by_user.py`

---

## 2. 범위

### 2.1 대상 범위

- [ ] `USER_DATA_DIR` 경로 변경: `{BASE_DATA_DIR}/{USER_ID}/python` -> `{BASE_DATA_DIR}/{USER_ID}`
- [ ] `full` 데이터 파일명 변경: `linkedin_python_full_{date}.json` -> `linkedin_{USER_ID}_full_{date}.json`
- [ ] `update` 데이터 파일명 변경: `linkedin_python_update_{timestamp}.json` -> `linkedin_{USER_ID}_update_{timestamp}.json`
- [ ] **기존 파일 마이그레이션 로직 추가**: `python/` 폴더 내의 기존 파일들을 새 규칙에 맞춰 이동 및 이름 변경
- [ ] `get_latest_full_file` 메서드의 파일 검색 패턴 업데이트
- [ ] `gb-jeong` 또는 `zoon-chang` 데이터를 통한 경로 및 파일명 생성 검증

### 2.2 제외 범위

- `output_linkedin` (전체 스크랩) 폴더 구조 변경
- 수동으로 직접 생성한 비규칙적 파일들의 처리

---

## 3. 요구사항

### 3.1 기능적 요구사항

| ID | 요구사항 | 우선순위 | 상태 |
|----|----------|----------|------|
| FR-01 | 저장 경로에서 `python` 서브 디렉토리 제거 | 높음 | 대기 |
| FR-02 | `full` 파일명에 `user_id` 포함 (`linkedin_{user_id}_full_YYYYMMDD.json`) | 높음 | 대기 |
| FR-03 | `update` 파일명에 `user_id` 포함 (`linkedin_{user_id}_update_YYYYMMDD_HHMMSS.json`) | 높음 | 대기 |
| FR-04 | 기존 파일 로드 로직(`get_latest_full_file`)이 변경된 명명 규칙을 지원하도록 수정 | 높음 | 대기 |
| FR-05 | **기존 파일 자동 마이그레이션**: 스크립트 실행 시 이전 규칙의 파일들을 새 위치/이름으로 자동 전환 | 높음 | 대기 |

### 3.2 비기능적 요구사항

| 카테고리 | 기준 | 측정 방법 |
|----------|------|-----------|
| 일관성 | 모든 사용자별 데이터가 동일한 구조와 명명 규칙을 따름 | 파일 탐색기 확인 |
| 호환성 | 이전 파일명 규칙으로 저장된 파일도 읽을 수 있도록 폴백(Fallback) 고려 여부 결정 | 코드 리뷰 |

---

## 4. 성공 기준

### 4.1 완료 정의 (Definition of Done)

- [ ] 실행 후 `output_linkedin_user/{user_id}/` 바로 아래에 JSON 파일이 생성됨.
- [ ] 파일명에 사용자 ID가 정확히 포함됨.
- [ ] 업데이트 파일도 변경된 규칙에 따라 `update/` 폴더 내에 저장됨.

---

## 5. 아키텍처 고려 사항

### 5.1 주요 설계 결정

- **경로 설정**: `USER_DATA_DIR` 변수 정의 부분을 수정합니다.
- **파일명 템플릿**: `f"linkedin_{USER_ID}_full_{date}.json"` 형태의 f-string을 사용합니다.
- **기존 데이터 호환성**: `get_latest_full_file`에서 새로운 패턴(`linkedin_{USER_ID}_full_*.json`)과 이전 패턴(`linkedin_python_full_*.json`)을 모두 검색할지, 아니면 깔끔하게 새 패턴만 지원할지 결정이 필요합니다. (사용자에게 질문 예정)

---

## 6. 향후 단계

1. [ ] 디자인 문서 작성 (`linkedin_user_data_path_refinement.design.md`)
2. [ ] 코드 수정 및 테스트
3. [ ] 결과 확인 및 보고서 작성
