# [Plan] 저장순 정렬 로직 및 전역 Sequence ID 개선

## 1. 배경 및 문제 정의
- **현상**: 새로 스크랩한 링크드인 게시물이 "저장순" 정렬 시 최상단이 아닌 하단(혹은 쓰레드 게시물 뒤)에 위치함.
- **원인 분석**: 
    1. **개별 플랫폼 ID 관리**: LinkedIn 스크래퍼가 자체적으로 `sequence_id`를 1부터 다시 부여하거나 작은 값으로 관리하고 있음.
    2. **통합 ID 부재**: `total_scrap.py`가 데이터를 합칠 때 전역적인 시퀀스 번호를 새로 매기지 않고, 각 플랫폼의 ID를 그대로 사용함.
    3. **정렬 기준 불일치**: 웹 뷰어는 `sequence_id` 내림차순을 "저장순"으로 정의하는데, Threads 데이터는 ID가 400번대인 반면 최신 LinkedIn 데이터는 1~100번대 ID를 가져서 뒤로 밀림.
- **필드 구조 개선 제안 (Traceability)**:
    1. **`sequence_id`**: 통합 피드 기준의 전역 고유 ID (정렬용).
    2. **`platform_sequence_id`**: 각 플랫폼 스크래퍼가 부여한 원래의 순서 번호 (추적용).

## 2. 목표
- 모든 플랫폼의 데이터를 통합할 때, 수집된 시점을 기준으로 유일하고 연속적인 전역 `sequence_id`를 부여함.
- 플랫폼별 원래의 ID는 `platform_sequence_id`로 보존하여 데이터 추적성 확보.
- 새로 수집된 데이터가 항상 가장 큰 `sequence_id`를 갖도록 하여 "저장순" 정렬 시 최상단에 노출되도록 개선.

## 3. 해결 방안 (Implementation Plan)
- **total_scrap.py 수정**:
    1. `merge_results` 단계에서 각 플랫폼의 `sequence_id`를 `platform_sequence_id` 필드로 이동.
    2. `save_total` 함수에서 기존 `total_full_*.json` 파일을 로드하여 현재까지의 `max_sequence_id`를 파악.
    3. 이번에 새로 추가된 게시물(`new_items`)들에 대해 `max_sequence_id + 1`부터 순차적으로 전역 `sequence_id`를 부여.
    4. 중복된 게시물은 기존 통합 `sequence_id`를 유지.
- **검증**:
    1. 수정 후 `total_scrap.py`를 실행하여 `total_full_20260211.json`의 `sequence_id`가 연속적으로 증가하는지 확인.
    2. 웹 뷰어에서 "저장순" 정렬 시 오늘 스크랩한 링크드인 게시물이 맨 위에 나오는지 확인.

## 4. 기대 효과
- 플랫폼(Threads, LinkedIn, Substack 등)에 상관없이 스크랩한 순서대로 정확한 "저장순" 정렬 제공.
- 데이터 무결성 및 정렬 신뢰도 향상.
