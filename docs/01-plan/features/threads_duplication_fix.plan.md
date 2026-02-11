# Plan: Threads Scraper Duplication Fix & Data Cleanup

`scrap_single_post.py`에서 발생하는 게시글 중복 수집 및 병합 로직의 결함을 수정하고, 오염된 데이터를 정리합니다.

## 1. 문제 분석 (Root Cause)
- **ID 불일치**: `scrap_single_post.py`가 타래글을 병합할 때, 병합된 결과물의 `code`(ID)를 타래의 첫 번째 항목(종종 답글)의 것으로 설정합니다.
- **중복 체크 실패**: `import_from_simple_database`는 메인 게시글 ID를 기준으로 중복을 체크하는데, Full DB에는 답글 ID로 저장되어 있어 중복으로 인식하지 못하고 매번 새로 추가합니다.
- **무한 증식**: 추가된 항목은 매번 '미수집' 상태로 인식되어 다시 스캔되고, 병합 시 또 다른 ID(혹은 동일한 잘못된 ID)로 저장되면서 데이터가 기하급수적으로 늘어납니다.

## 2. 해결 방안
- **병합 로직 수정**: `merge_thread_items` 함수에서 병합된 포스트의 `code`를 반드시 `root_code`(메인 게시글 ID)로 강제 설정합니다.
- **데이터 정제**: 
    - `output_threads/python/threads_py_full_20260205.json`에서 중복된 `code`를 제거합니다.
    - 잘못된 `code`로 저장된 항목들을 올바른 `root_code`로 복구하거나 정리합니다.
- **Import 로직 보완**: `code`뿐만 아니라 `root_code`도 체크하여 중복 방지를 이중으로 수행합니다.

## 3. 실행 단계
1.  `scrap_single_post.py`의 `merge_thread_items` 함수를 수정합니다.
2.  기존 Full DB의 중복을 제거하는 정제 스크립트를 실행합니다.
3.  `total_scrap.py`를 실행하여 스캔 대상이 12개(실패 항목)로 줄어드는지 확인합니다.

## 4. 기대 결과
- 스캔 대상이 신규 데이터가 없을 경우 0개(혹은 실패한 항목만)로 유지됨.
- 데이터베이스 용량 최적화 및 무결성 확보.
- 실행 시간 단축.
