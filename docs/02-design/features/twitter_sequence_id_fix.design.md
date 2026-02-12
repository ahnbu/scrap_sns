# PDCA 설계: '최초 수집 시점' 기반 저장순 정렬 완전 구현

## 1. 목적 (Design)
- 모든 플랫폼 데이터에 고정된 `crawled_at`과 `sequence_id`를 부여하여 시스템 유입 순서를 영구적으로 기록한다.

## 2. 세부 설계 사항

### A. 스크래퍼 공통 데이터 병합 로직 (Update/All 모드 공통)
1. **데이터 로드**: 최신 Full JSON 파일을 읽어 `all_posts_map`과 `max_sequence_id`를 확보한다.
2. **게시물 처리 루프**:
    - **Existing Post**: 수집된 `id`가 이미 `all_posts_map`에 있다면, 텍스트나 미디어 정보는 업데이트할 수 있으나 **`crawled_at`과 `sequence_id`는 기존 값을 절대 유지한다.**
    - **New Post**: 새로 발견된 `id`라면:
        - `crawled_at = datetime.now().isoformat(timespec='milliseconds')`
        - `sequence_id = ++max_sequence_id`
3. **정렬 및 저장**: 
    - 플랫폼 파일 내부 저장은 `sequence_id` 내림차순(최신 수집순)으로 유지하되, 메타데이터에 `max_sequence_id`를 반드시 기록한다.

### B. `total_scrap.py` 병합 및 정렬 로직
1. **플랫폼 ID 보존**: 병합 시 원본의 `sequence_id`를 `platform_sequence_id`로 복사한다.
2. **정렬 알고리즘**:
    ```python
    def sort_key(post):
        # 1순위: 최초 수집 시점 (ISO 문자열 정렬)
        c_at = post.get('crawled_at') or '0000-00-00T00:00:00.000'
        # 2순위: 플랫폼 내 증분 번호 (동시 수집 시 선후 관계)
        psid = post.get('platform_sequence_id', 0)
        return (c_at, psid)
    
    unique_posts.sort(key=sort_key)
    ```
3. **전역 ID 부여**: 정렬된 결과에 대해 `sequence_id`를 1부터 다시 부여하여 웹 뷰어에서 정렬 기준으로 사용하게 한다.

## 3. 예외 및 마이그레이션
- `crawled_at`이 없는 과거 데이터: `timestamp` 값을 `crawled_at`의 기본값으로 차용하여 논리적 모순을 최소화한다.
