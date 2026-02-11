# [Plan] 데이터 중복 제거 로직 구현 (Threads 기반 중복 해결)

## 1. 개요
현재 통합 데이터(`total_full_*.json`) 및 웹 뷰어(`web_viewer/data.js`)에서 동일한 게시글이 여러 번 표시되는 중복 문제가 발생하고 있습니다. 조사 결과, Threads 플랫폼 데이터 수집 및 병합 과정에서 과거 파일(`threads_py_full_20260205.json`)의 중복 항목이 최신 통합본까지 유지되고 있는 것으로 확인되었습니다.

## 2. 조사 결과 (Analysis)
- **발생 위치**: `output_total/total_full_20260211.json` 및 `web_viewer/data.js`
- **주요 원인**: 
    - `output_threads/python/threads_py_full_20260205.json` 파일 내에 동일한 `code`를 가진 항목이 최대 7개까지 중복 저장되어 있음.
    - `total_scrap.py`의 `merge_results()` 및 `save_total()` 로직에서 플랫폼별 Full 파일을 읽어올 때, 개별 항목의 고유성(ID/Code)을 검증하여 중복을 제거하는 단계가 누락됨.
    - 단순히 두 플랫폼의 리스트를 합치는(`threads_posts + linkedin_posts`) 방식이 사용됨.
- **플랫폼별 현황**:
    - **Threads**: 316개 항목 중 20개의 URL/Code가 중복됨 (과거 full 파일 오염).
    - **LinkedIn**: 중복 없음.

## 3. 해결 방안 (Proposed Solution)
### 3.1. 통합 로직 개선 (`total_scrap.py` 수정)
- `merge_results()` 함수에서 게시글들을 합칠 때, `code` 필드를 기준으로 중복을 제거하는 로직 추가.
- `dict` 또는 `set`을 사용하여 이미 처리된 `code`는 제외.

### 3.2. 기존 데이터 정제
- 이미 중복이 포함된 `output_threads/python/threads_py_full_20260205.json` 등의 파일을 수동 또는 스크립트로 정제하여 향후 발생할 수 있는 오염 방지.

### 3.3. 검증 단계 추가
- 데이터 병합 완료 후, 메타데이터에 `duplicates_removed_count`와 같은 필드를 추가하여 투명성 확보.

## 4. 상세 계획 (Tasks)
1. [ ] `total_scrap.py`의 `merge_results` 함수 수정: `code` 기반 중복 제거 로직 삽입.
2. [ ] `total_scrap.py`의 `save_total` 함수 확인: `new_items` 계산 로직이 중복 제거된 리스트를 기반으로 하도록 보장.
3. [ ] 기존 오염된 Threads Full 데이터 파일 정제 스크립트 실행 및 결과 확인.
4. [ ] `total_scrap.py` 재실행을 통해 `total_full_20260211.json` 및 `web_viewer/data.js` 갱신.
5. [ ] 웹 뷰어에서 중복 표시 여부 최종 확인.

## 5. 기대 효과
- 사용자에게 깨끗하고 정확한 데이터 제공.
- 데이터 파일 용량 최적화 및 시스템 신뢰도 향상.
