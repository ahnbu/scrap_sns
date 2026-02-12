# PDCA 계획: '최초 수집 시점' 기반 저장순 정렬 완전 구현

## 1. 개요 (Plan)
- **목표**: 모든 SNS 플랫폼의 수집기에 '최초 인지 시점(`crawled_at`) 기록' 및 'ID 보존' 로직을 도입하여, 통합 피드에서 완벽한 저장순 정렬을 실현한다.
- **핵심 원칙**: 
    1. 한번 부여된 `crawled_at`과 `sequence_id`는 수정되지 않는다.
    2. `all` 모드 크롤링 시에도 기존 데이터의 메타데이터는 보존한다.

## 2. 현재 상태 분석
- **공통**: '저장순' 정렬이 게시글 작성 시간이 아닌 시스템 유입 시간(`crawled_at`)을 따라야 하나, 일부 스크래퍼에서 이 필드가 누락되거나 업데이트 시 갱신되는 문제가 있음.
- **Twitter**: `crawled_at` 및 `sequence_id` 필드 누락.
- **Threads**: `sequence_id`가 0으로 고정되어 있으며, `all` 모드 시 `crawled_at`이 현재 시간으로 덮어씌워질 위험이 있음.
- **LinkedIn**: `max_sequence_id` 관리는 잘 되고 있으나, `all` 모드 시 기존 데이터 보존 여부 확인 필요.

## 3. 개선 계획
- **Task 1: 모든 스크래퍼(`twitter`, `thread`, `linkedin`) 공통 로직 수정**
    - `all_posts_map` 로드 시 기존 `crawled_at`, `sequence_id`를 보존하는 `merge` 로직 강화.
    - 신규 게시물에 대해서만 현재 시간(`ISO 8601`)과 증분 ID 부여.
- **Task 2: `total_scrap.py` 정렬 키 변경**
    - 정렬 기준: `(crawled_at, platform_sequence_id)`
    - 통합 피드의 전역 `sequence_id`는 위 정렬 결과를 바탕으로 1부터 재부여.
- **Task 3: 마이그레이션**
    - `crawled_at`이 없는 기존 데이터에 대해 `timestamp` 또는 파일 수정 시간을 기준으로 최소한의 값 부여.

## 4. 기대 효과
- 사용자가 웹 뷰어에서 '저장순' 정렬을 선택했을 때, 플랫폼에 상관없이 내가 이 시스템에 추가한 순서대로 게시물을 볼 수 있음.
