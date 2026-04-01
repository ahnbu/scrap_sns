---
title: "linkedin_user_data_path_refinement 완료 보고서"
created: "2026-02-08 00:00"
template: report
version: 1.0
description: linkedin_user_data_path_refinement 최종 완료 보고서
---

# linkedin_user_data_path_refinement 완료 보고서

> **요약**: 링크드인 사용자 데이터의 저장 구조를 간소화하고 파일명에 사용자 ID를 포함하는 작업을 완료하였습니다. 기존 데이터에 대한 자동 마이그레이션도 성공적으로 수행되었습니다.
>
> **프로젝트**: scrap_sns
> **날짜**: 2026-02-08
> **상태**: 완료 (Match Rate 100%)

---

## 1. 개요

`linkedin_scrap_by_user.py`에서 생성되는 데이터의 관리 효율성을 높이기 위해 저장 경로를 최적화하고 명명 규칙을 개선하였습니다.

---

## 2. 주요 변경 사항

### 2.1 저장 경로 최적화
- 기존: `output_linkedin_user/{user_id}/python/`
- 변경: `output_linkedin_user/{user_id}/` (불필요한 `python` 서브 디렉토리 제거)

### 2.2 파일명 규칙 개선
- **Full 데이터**: `linkedin_{user_id}_full_YYYYMMDD.json`
- **Update 데이터**: `linkedin_{user_id}_update_YYYYMMDD_HHMMSS.json`

### 2.3 자동 마이그레이션 기능 추가
- 스크립트 실행 시 이전 규칙(`python/` 폴더 내 `linkedin_python_...`)의 파일들을 자동으로 검색하여 새 규칙에 맞춰 이동 및 이름을 변경합니다.
- 이동 완료 후 빈 `python` 폴더는 자동으로 삭제됩니다.

---

## 3. 검증 결과

- `gb-jeong`, `zoon-chang` 사용자에 대해 테스트 실행.
- 기존 파일들이 성공적으로 상위 폴더로 이동되고 이름이 변경됨을 확인.
- 이후 새로운 수집 데이터가 새 규칙에 따라 정확한 위치에 저장됨을 확인.

---

## 4. 향후 유지보수 참고사항

- 현재 마이그레이션 로직은 `.json` 파일만을 대상으로 합니다. 폴더 내에 `.md` 등 다른 확장자의 파일이 있을 경우 `python` 폴더가 삭제되지 않고 남을 수 있습니다.
- 모든 사용자 데이터가 일관된 규칙을 갖게 되었으므로, 이후 웹 뷰어 등에서 데이터 로드 경로를 수정할 때 이 변경된 규칙을 참고하시기 바랍니다.
