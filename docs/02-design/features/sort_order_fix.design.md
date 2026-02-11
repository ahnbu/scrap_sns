# [Design] 전역 Sequence ID 및 플랫폼 ID 분리 설계

## 1. 데이터 구조 변경 (Schema)
통합 데이터(`total_full_*.json`) 내의 각 `post` 객체는 다음과 같은 ID 체계를 가집니다.

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `sequence_id` | integer | **통합 피드 전역 ID**. 수집 시점에 따라 증가하며 "저장순" 정렬의 기준이 됨. |
| `platform_sequence_id` | integer | **플랫폼별 로컬 ID**. 각 스크래퍼가 부여한 원래의 순서 번호. |

## 2. 통합 로직 (total_scrap.py)

### 2.1 플랫폼 데이터 전처리 (`merge_results`)
- `threads_posts`와 `linkedin_posts`를 합칠 때, 각 객체의 기존 `sequence_id` 필드를 `platform_sequence_id`로 변경함.
- 예: `p['platform_sequence_id'] = p.pop('sequence_id', 0)`

### 2.2 전역 ID 부여 (`save_total`)
1. **기존 데이터 분석**:
   - 가장 최근의 `total_full_*.json`을 로드.
   - `prev_id_map = { code: sequence_id }`를 생성하여 기존 게시물의 통합 ID를 추적.
   - `max_id = max(prev_id_map.values())`를 통해 현재까지의 최대 번호 파악.
2. **신규 데이터 처리**:
   - `new_items = [p for p in posts if p['code'] not in prev_id_map]`
   - **중요**: `new_items`를 `created_at` (또는 수집 순서) 기준 **오름차순**으로 정렬.
   - 정렬된 `new_items`에 대해 `max_id + 1`부터 1씩 증가시키며 `sequence_id` 부여.
3. **기존 데이터 유지**:
   - 이미 존재하는 게시물은 `prev_id_map`에 저장된 원래의 `sequence_id`를 그대로 할당하여 정렬 순서 유지.

## 3. UI 연동 (web_viewer/script.js)
- 웹 뷰어는 이미 `sequence_id`를 기준으로 정렬하고 있으므로, 필드명만 유지된다면 별도의 정렬 로직 수정은 불필요.
- 다만, 데이터 로드 시 `_seqId` 프로퍼티에 할당되는 값이 전역 ID임을 확인.

## 4. 예외 케이스 처리
- **ID 중복 방지**: `code`를 키로 사용하여 중복 체크 및 ID 매핑.
- **날짜 데이터 부재**: `created_at`이 없는 경우 `crawled_at`을 보조 기준으로 사용.
