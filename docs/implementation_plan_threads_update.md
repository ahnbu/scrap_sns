# Threads 스크래핑 및 통합 수집 로직 개선 계획

Threads 스크래퍼가 `update` 모드에서 중복 수집을 수행하는 문제와, 통합 수집기(`total_scrap.py`)에서 상세 수집 및 병합이 원활하지 않은 문제를 해결합니다.

## Proposed Changes

### [Component] Threads 스크래퍼 (`thread_scrap.py`)

수집 중단 로직을 강화하여 불필요한 네트워크 패킷 처리와 스크롤을 방지합니다.

- **[MODIFY] thread_scrap.py**
  - `process_network_post` 함수 시작 부분에 `if stop_code_found: return` 추가.
  - `handle_response` 내 루프에서 `stop_code_found` 체크 추가.
  - `update only` 모드에서 기존 데이터의 `is_detail_collected` 상태를 보존하도록 수정.

### [Component] 통합 수집기 (`total_scrap.py`)

병합 로직의 파일 패턴을 유연하게 조정하고, 상세 수집기 실행 판단 기준을 정교화합니다.

- **[MODIFY] total_scrap.py**
  - `merge_results` 함수에서 `threads_py_full_*.json`이 없을 경우 `threads_py_simple_*.json`을 대체재로 사용하도록 수정. (필수 파일 차단 완화)
  - `should_run_consumer`에서 수집 완료 여부를 판단할 때, 상세 수집기가 필요함에도 판단이 누락되는 경우가 있는지 재검토 및 수정.
  - `merge_results`에서 사용하는 ID 추출 방식(`platform_id` vs `id` vs `code`)을 Threads 데이터 구조에 맞게 통일.

### [Component] 상세 수집기 (`thread_scrap_single.py`)

- **[MODIFY] thread_scrap_single.py**
  - 수집된 데이터 저장 시 `is_detail_collected: true` 마킹이 Simple Full 파일에 정확히 반영되는지 확인 및 보강.

## Verification Plan

### Automated Tests

- `python thread_scrap.py --mode update` 실행 후, 콘솔 로그에서 "기준 게시물 발견! (크롤링 중단)" 메시지가 뜨고 즉시 종료되는지 확인.
- `python total_scrap.py --mode update` 실행 후, `thread_scrap_single.py`가 연달아 실행되는지 확인 (신규 항목 있을 경우).
- 최종적으로 `output_total/total_full_YYYYMMDD.json`에 Threads 데이터가 포함되어 병합되는지 확인.

### Manual Verification

- `output_threads/python` 디렉토리에서 오늘 날짜의 `full` 파일이 생성되지 않은 상태에서 `total_scrap.py`를 실행하여 "필수 Full 파일" 오류가 더 이상 발생하지 않는지 확인.
