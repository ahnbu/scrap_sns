# Plan: Threads 상세 수집 연동 오류 수정 및 Full 파일 생성 복구

이 문서는 Threads의 상세 수집 결과물(`full_*.json`)이 생성되지 않는 문제를 해결하고, 전체 수집 파이프라인을 정상화하기 위한 계획을 담고 있습니다.

## 1. 현상 및 원인
- **현상**: `total_scrap.py`를 실행해도 Threads의 `full_20260212.json` 파일이 생성되지 않음. (목록 파일인 `simple_full`만 생성됨)
- **원인**: `total_scrap.py`에서 상세 수집기 호출 시 `thread_scrap_single.py`가 아닌 존재하지 않는 파일명(`scrap_single_post.py`)을 사용함.

## 2. 해결 전략
### 2.1 파일명 정규화
- `total_scrap.py` 내의 Threads Consumer 실행 명령어를 `thread_scrap_single.py`로 즉시 교체.
- 향후 혼동을 방지하기 위해 파일명 명칭 규칙을 'x' 플랫폼과 동일하게 `thread_scrap_single.py`로 확정.

### 2.2 입출력 파일 정합성 확인
- `thread_scrap_single.py`가 `output_threads/python` 내의 최신 `simple_full` 파일을 읽어오는지 확인.
- 결과 저장 시 `threads_py_full_{date}.json` 형식을 준수하는지 점검.

## 3. 진행 단계 (PDCA)
1. **[Plan]**: (현재) 파일명 불일치 원인 파악 및 해결 전략 수립.
2. **[Design]**: 파이프라인 명령어 및 내부 파일 경로 상수 설계.
3. **[Do]**: `total_scrap.py` 및 `thread_scrap_single.py` 코드 수정.
4. **[Check]**: 수집 재시작 후 오늘자 `full` 파일 생성 및 데이터 포함 여부 검증.
5. **[Act]**: 최종 통합 DB와 연동 확인.
