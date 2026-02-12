# Plan: SNS 플랫폼 데이터 필드 구조 통합 및 표준화 (Unified SNS Data Schema)

## 1. 개요 (Overview)
현재 수집 중인 각 SNS 플랫폼(X/Twitter, Threads, LinkedIn)의 데이터 필드명이 서로 달라 `data.js` 및 웹 뷰어에서 데이터를 처리하는 데 복잡성이 발생하고 있습니다. 특히 사용자 식별자(`user` vs `username`), 미디어 필드(`media` vs `images`) 등이 혼용되고 있어 이를 하나로 통합하여 데이터 일관성을 확보하고 유지보수 효율을 높이고자 합니다.

## 2. 현상 분석 및 원인 진단 (Analysis & Diagnosis)

### 2.1 플랫폼별 핵심 필드 매핑 및 통합 규격
| 항목 (Category) | **통합 표준 필드** | **X (Twitter)** | **Threads** | **LinkedIn** | **설명** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **게시물 고유 ID** | `platform_id` | `id` | `code` | `id` / `code` | 플랫폼에서 부여한 원본 ID |
| **사용자 핸들** | `username` | `user` | `username` | `user` | 계정 식별 ID (@id) |
| **사용자 노출명** | `display_name` | `display_name` | `display_name` | `username` | 화면에 표시되는 이름 |
| **게시물 본문** | `full_text` | `full_text` | `full_text` | `full_text` | 전체 텍스트 내용 |
| **미디어 URL** | `media` | `media` | `images` | `media` / `images` | 이미지/영상 URL 배열 |
| **작성 일시** | `created_at` | `timestamp` | `created_at` | `created_at` | YYYY-MM-DD HH:MM:SS |
| **작성 날짜** | `date` | `date` | `date` | `date` | YYYY-MM-DD (필터용) |
| **원본 주소** | `url` | `url` | `post_url` | `url` / `post_url` | 게시물 원본 링크 |

### 2.2 플랫폼별 사용 중인 전체 변수 리스트 (누락 방지용)
기존 시스템에서 수집 및 활용 중인 모든 변수를 나열합니다. 통합 스키마 적용 시 해당 데이터들이 표준 필드에 흡수되거나, 필요한 경우 메타데이터로 보존되어야 합니다.

| 플랫폼 | 사용 중인 전체 변수 (All Current Fields) |
| :--- | :--- |
| **X (Twitter)** | `id`, `user`, `display_name`, `full_text`, `media`, `timestamp`, `date`, `url`, `sns_platform`, `source`, `is_detail_collected`, `sequence_id`, `crawled_at`, `platform_sequence_id`, `local_images` |
| **Threads** | `id` (code), `code`, `root_code`, `pk`, `user` (username), `username`, `display_name`, `user_link`, `full_text`, `like_count`, `reply_count`, `repost_count`, `quote_count`, `timestamp`, `created_at`, `time_text`, `date`, `url`, `post_url`, `media` (images), `images`, `media_type`, `content_type`, `sns_platform`, `source`, `crawled_at`, `sequence_id`, `is_merged_thread`, `original_item_count`, `platform_sequence_id` |
| **LinkedIn** | `id`, `code`, `user`, `username`, `display_name`, `timestamp`, `created_at`, `date`, `time_text`, `full_text`, `url`, `post_url`, `profile_slogan`, `media`, `images`, `user_link`, `sns_platform`, `content_type`, `source`, `crawled_at`, `sequence_id` |

### 2.3 원인 진단
1.  **플랫폼별 API/DOM 구조 차이**: 크롤링 대상인 각 SNS 웹사이트의 API 응답이나 HTML 구조가 다르기 때문에 최초 개발 시 해당 구조를 그대로 반영함.
2.  **독립적인 스크래퍼 개발**: 각 플랫폼 스크래퍼가 서로 다른 시점에 독립적으로 개발되면서 공통된 인터페이스 규격(Schema)이 정의되지 않음.
3.  **병합 로직의 한계**: `total_scrap.py` 등에서 데이터를 합칠 때 필드명을 통일하지 않고 원본 데이터를 그대로 유지한 채 뷰어에서 대응하도록 함.

### 3.4 Simple(목록) 및 Full(상세) 버전 일관성 전략
- **필드 단일화 원칙**: 수집 단계(목록 스캔 vs 상세 크롤링)나 출력 파일 형태(Simple Update vs Platform Full vs Total Full)에 관계없이 모든 게시물 객체는 동일한 **표준 코어 필드명**을 사용함.
- **계층적 데이터 구조**:
    - **Core Fields (공통)**: `platform_id`, `username`, `display_name`, `full_text`, `media`, `created_at`, `date`, `url`
    - **Extended Fields (Full 전용)**: 상세 수집 시에만 추가되는 필드(`like_count`, `reply_count` 등)는 선택적 속성으로 유지하되, 핵심 식별자와 본문 필드는 표준을 따름.
- **스크래퍼 수정**: `extract_from_json`, `process_network_post` 등 데이터를 최초 생성하는 모든 함수에서 표준 규격을 즉시 적용하도록 수정함.

## 4. 단계별 실행 계획
1.  **[분석]** 각 스크래퍼의 Simple/Full 출력부 및 `total_scrap.py`의 병합 로직 분석.
2.  **[설계]** 모든 출력 단계에서 적용할 `Unified Schema Wrapper` 함수 설계.
3.  **[구현]** 
    - 각 플랫폼별 스크래퍼(`simple` 및 `full` 수집 로직) 수정.
    - `total_scrap.py`의 병합 시 필드 보정 로직 제거 (입력 데이터가 이미 표준화되었음을 전제).
4.  **[변환]** 기존 모든 JSON(Simple, Full 포함) 데이터 마이그레이션.
5.  **[검증]** 웹 뷰어에서 Simple 데이터와 Full 데이터가 섞여 있어도 UI가 깨지지 않는지 최종 확인.

## 4. 기대 효과 (Expected Benefits)
-   **코드 단순화**: 웹 뷰어에서 `post.user || post.username` 같은 예외 처리가 사라져 로직이 간결해짐.
-   **확장성 확보**: 새로운 플랫폼(예: Instagram, Facebook) 추가 시 표준 규격만 따르면 즉시 통합 가능.
-   **데이터 분석 용이**: 모든 플랫폼 데이터가 동일한 형식을 가지므로 통계 및 분석 처리가 쉬워짐.

## 5. 주의 사항 (Cautions)
-   **하위 호환성**: `data.js` 변경 시 기존 뷰어가 깨지지 않도록 한시적으로 기존 필드와 신규 필드를 병행하거나, 전체 데이터 변환을 우선 완료해야 함.
-   **데이터 손실 방지**: 필드명 통합 과정에서 미디어 개수나 본문 텍스트가 누락되지 않도록 꼼꼼한 검증 필요.
