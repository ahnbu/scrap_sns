# [Design] 데이터 중복 제거 로직 및 정제 프로세스 설계

## 1. 시스템 아키텍처 및 로직 변경

### 1.1. 통합 스크립트 수정 (`total_scrap.py`)
- **함수**: `merge_results()`
- **기존 방식**:
  ```python
  all_posts = threads_posts + linkedin_posts
  ```
- **변경 방식**:
  - 고유한 `code`를 키로 하는 Dictionary(`unique_posts`)를 사용하여 중복 제거.
  - 중복 발생 시, 메타데이터가 더 풍부하거나 최신인 데이터를 우선적으로 선택(또는 먼저 발견된 항목 유지).
  ```python
  seen_codes = set()
  unique_posts = []
  for p in threads_posts + linkedin_posts:
      code = str(p.get('code'))
      if code not in seen_codes:
          unique_posts.append(p)
          seen_codes.add(code)
  ```

### 1.2. 과거 데이터 정제 스크립트 설계 (`cleanup_threads_history.py`)
- `output_threads/python/` 폴더 내의 모든 JSON 파일을 스캔.
- 각 파일 내의 `posts` 리스트에서 `code` 기준 중복 항목 제거.
- 정제된 데이터를 동일한 파일명으로 덮어쓰기 (또는 백업 후 저장).

## 2. 중복 데이터 백업 및 제공 계획
- 로직 수정 및 정제 전, 현재 `output_total/total_full_20260211.json`에서 중복된 항목들만 따로 추출하여 `output_total/duplicated_items_backup.json`으로 저장.
- 사용자가 어떤 데이터가 중복되었었는지 사후 검증 가능하도록 함.

## 3. 작업 순서 (Implementation Sequence)
1. **[Back-up]** 현재 중복된 항목 추출 및 저장.
2. **[Refactor]** `total_scrap.py`의 병합 로직 수정.
3. **[Cleanup]** 과거 오염된 Threads JSON 파일들 정제.
4. **[Execute]** 통합 스크립트 실행하여 `data.js` 갱신.
5. **[Verify]** 최종 결과물의 중복 여부 재체크.

## 4. 데이터 구조 변경 사항
- `total_full_*.json`의 `metadata`에 `duplicates_removed` 필드 추가 (정수형).
