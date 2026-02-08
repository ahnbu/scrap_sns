---
template: report
version: 1.0
description: LinkedIn JSON to Markdown 변환 작업 완료 보고서
---

# linkedin_json_to_markdown_conversion Completion Report

> **요약**: LinkedIn JSON 데이터를 Markdown 형식으로 변환하는 작업을 성공적으로 완료하였습니다.

---

## 1. 작업 개요

- **작업명**: LinkedIn JSON 데이터 Markdown 변환
- **대상 파일**:
    1. `output_linkedin_user/zoon-chang/python/linkedin_python_full_20260207.json`
    2. `output_linkedin_user/gb-jeong/python/linkedin_python_full_20260207_total.json`
- **수행 도구**: Python 3.12 (Custom Conversion Script)
- **완료 일시**: 2026-02-07

---

## 2. 주요 성과 및 결과물

### 2.1 결과 파일

- `output_linkedin_user/zoon-chang/python/linkedin_python_full_20260207.md`
- `output_linkedin_user/gb-jeong/python/linkedin_python_full_20260207_total.md`

### 2.2 주요 특징

- **가독성**: JSON 데이터를 Markdown 리스트 및 인용구 형식으로 변환하여 가독성 확보.
- **데이터 보존**: 작성자, 작성 시간, 본문, 원본 링크, 이미지가 모두 포함됨.
- **인코딩 최적화**: UTF-8 (No BOM) 인코딩을 적용하여 한글 깨짐 방지 및 호환성 유지.

---

## 3. 검증 결과 (Check)

- **데이터 일치율**: 100% (모든 JSON 포스트가 Markdown으로 누락 없이 변환됨)
- **인코딩 검증**: PowerShell을 통한 파일 내 한글 문자열 검색(`추출 일시`) 결과, 정상 포함 확인.
- **레이아웃**: Markdown 미리보기를 통해 포스트 구분 및 이미지 태그가 정상 작동함을 확인.

---

## 4. 이슈 및 해결 방법

- **이슈**: PowerShell `run_shell_command` 환경에서 한글 문자열이 포함된 Python 스크립트 생성 시 인코딩 충돌 발생.
- **해결**: PowerShell의 `Here-string`(@'')과 `[System.IO.File]::WriteAllText` 메서드를 사용하여 명시적으로 UTF-8 (No BOM) 형식으로 스크립트를 생성하여 해결.

---

## 5. 향후 제언

- 향후 대량의 데이터를 처리할 경우, Markdown 파일을 월별 또는 사용자별로 분할하여 관리하는 기능 추가 고려.
- 이미지 다운로드 및 로컬 경로 참조 기능을 추가하여 오프라인 가독성 강화 가능.
