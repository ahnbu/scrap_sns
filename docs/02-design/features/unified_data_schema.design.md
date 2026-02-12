# [Design] 데이터 스키마 표준 규격 상세 설계

## 1. 표준 데이터 스키마 상세 명세 (JSON)

모든 SNS 포스트 데이터는 다음의 필드 구조와 순서를 엄격히 준수해야 합니다.

| 순번 | 필드명 | 타입 | 필수 | 설명 |
| :--- | :--- | :---: | :---: | :--- |
| 1 | `sequence_id` | Integer | O | 전체 데이터 내의 고유 정렬 순번 |
| 2 | `platform_id` | String | O | 플랫폼 제공 고유 ID (Twitter ID, Threads Code 등) |
| 3 | `sns_platform` | String | O | 플랫폼 식별자 (twitter, threads, linkedin, substack) |
| 4 | `username` | String | O | 사용자 핸들/아이디 |
| 5 | `display_name` | String | O | 사용자 표시 이름 |
| 6 | `full_text` | String | O | 게시글 전체 본문 |
| 7 | `media` | Array | O | 이미지/영상 URL 배열 (없을 시 `[]`) |
| 8 | `url` | String | O | 게시글 원본 접근 경로 |
| 9 | `created_at` | String | O | 게시글 작성 일시 |
| 10 | `date` | String | O | 게시글 작성 날짜 (YYYY-MM-DD) |
| 11 | `crawled_at` | String | O | 데이터 수집 일시 (YYYY-MM-DD HH:MM:SS) |
| 12 | `source` | String | O | 수집 엔진/경로 (python, js_console 등) |
| 13 | `local_images` | Array | O | 로컬 저장 이미지 경로 배열 (없을 시 `[]`) |

## 2. 에이전트 규칙 반영 설계

`.agent/rules/data-schema.md` 파일을 생성하여 에이전트가 코딩 시 위 규격을 강제로 참조하도록 설정합니다.

## 3. 갭 분석 대상
- **대상 파일**: `output_linkedin/python/linkedin_python_full_20260212.json`
- **분석 항목**: 필드 존재 여부, 필드 순서 일치 여부, 데이터 타입(특히 배열 필드)의 적절성.
