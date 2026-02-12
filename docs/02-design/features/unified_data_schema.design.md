# Design: SNS 플랫폼 데이터 필드 구조 통합 및 표준화

## 1. 표준 데이터 스키마 (Standard Schema)
모든 플랫폼 데이터는 수집 즉시 아래의 필드명으로 변환되어 저장됩니다.

| 표준 필드명 | 설명 | 데이터 타입 |
| :--- | :--- | :--- |
| `platform_id` | 플랫폼 원본 고유 ID | String |
| `username` | 사용자 핸들 (예: @id) | String |
| `display_name` | 사용자 노출 이름 | String |
| `full_text` | 게시물 본문 | String |
| `media` | 미디어(이미지/영상) URL 배열 | Array (String) |
| `created_at` | 작성 일시 (YYYY-MM-DD HH:MM:SS) | String |
| `date` | 작성 날짜 (YYYY-MM-DD) | String |
| `url` | 원본 게시물 URL | String |
| `sns_platform` | 플랫폼 구분 (x, threads, linkedin) | String |

## 2. 플랫폼별 매핑 상세 (Mapping Logic)

### 2.1 X (Twitter) - `twitter_scrap.py`
- `id` -> `platform_id`
- `user` -> `username`
- `timestamp` -> `created_at`
- 나머지 필드(`display_name`, `full_text`, `media`, `date`, `url`, `sns_platform`)는 이름 유지

### 2.2 Threads - `thread_scrap.py`
- `code` -> `platform_id`
- `username` -> `username` (유지)
- `images` -> `media` (통합)
- `created_at` -> `created_at` (유지)
- `post_url` -> `url`
- 상세 필드(`like_count`, `reply_count` 등)는 메타데이터로 보존

### 2.3 LinkedIn - `linkedin_scrap.py`
- `id` -> `platform_id`
- `user` -> `username`
- `username` -> `display_name` (LinkedIn은 `username` 필드에 실제 이름을 담고 있었음)
- `images` -> 삭제 (`media`만 사용)
- `created_at` -> `created_at` (유지)

## 3. 구현 및 마이그레이션 전략

### 3.1 스크래퍼 코드 수정
- 각 스크래퍼의 `extract_from_json`, `process_network_post` 등 `dict` 생성 부위에서 위 매핑을 즉시 적용.

### 3.2 데이터 마이그레이션 (`migrate_schema.py`)
- `output_twitter`, `output_threads`, `output_linkedin` 폴더 내의 모든 기존 JSON 파일을 순회하며 필드명을 표준으로 변경하여 덮어쓰기.

### 3.3 통합 스크립트 (`total_scrap.py`)
- 입력되는 모든 플랫폼 데이터가 표준 규격임을 전제하므로, 병합 시 존재하던 조건부 필드 로직(`post.get('user') or post.get('username')`)을 제거하고 단순 병합으로 최적화.
