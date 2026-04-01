---
title: "Design: X(Twitter) 저장 게시글(Bookmarks) 크롤링 및 타래글 통합"
created: "2026-02-12 11:40"
---

# Design: X(Twitter) 저장 게시글(Bookmarks) 크롤링 및 타래글 통합

이 문서는 X(Twitter)의 북마크 API를 활용하여 저장된 게시글을 수집하고, 타래글을 병합하여 `total_scrap.py`에 통합하기 위한 상세 설계를 담고 있습니다.

## 1. 시스템 아키텍처 및 흐름

### 1.1 데이터 수집 흐름
1.  **Auth**: `auth/auth_twitter.json`에서 세션 정보를 로드하거나 Playwright를 통해 로그인 수행.
2.  **Request**: X GraphQL Bookmarks API 호출 (`Bookmarks?variables={"count":20,...}`).
3.  **Parsing**: API 응답(JSON)에서 트윗 데이터 추출.
4.  **Threading**: `conversation_id_str`을 기준으로 타래글 여부 판단 및 병합.
5.  **Normalization**: 프로젝트 표준 스키마로 변환.
6.  **Storage**: `output_twitter/python/update/` 폴더에 증분 데이터 저장 및 Full 버전 업데이트.

## 2. 주요 로직 설계

### 2.1 API 요청 및 세션 관리
- **URL**: `https://x.com/i/api/graphql/.../Bookmarks`
- **Headers**: `authorization`, `x-csrf-token`, `cookie` 필수 포함.
- **Pagination**: 응답 내 `cursor` 값을 사용하여 다음 페이지 요청.

### 2.2 타래글(Thread) 병합 로직
- X 북마크 API는 저장된 트윗 하나만 반환하므로, 해당 트윗이 타래의 일부인 경우 전체 맥락을 파악하기 위해 다음 두 가지 방식을 혼합함:
    1.  **간이 방식**: 응답 내에 인접한 트윗이 포함되어 있는지 확인.
    2.  **심화 방식 (선택)**: `conversation_id_str`을 통해 상세 조회 API (`TweetDetail`) 호출 (Rate Limit 주의 필요).
- **병합 규칙**: 동일 작성자의 연속된 트윗일 경우 `

---

` 구분자로 본문 결합.

### 2.3 데이터 매핑 (Normalization)
| 필드명 | 설명 | X 데이터 매핑 경로 |
| :--- | :--- | :--- |
| `id` | 고유 ID | `rest_id` |
| `user` | 작성자 | `core.user_results.result.legacy.screen_name` |
| `body` | 본문 | `note_tweet...text` 또는 `legacy.full_text` |
| `media` | 이미지/동영상 | `legacy.entities.media` -> `media_url_https` |
| `timestamp` | 작성 시간 | `legacy.created_at` (ISO 변환 필요) |
| `url` | 원본 링크 | `https://x.com/{user}/status/{id}` |
| `sns_platform`| 플랫폼 구분 | `"twitter"` |

## 3. 파일 구성 계획
- `twitter_scrap.py`: 메인 스크래퍼 스크립트.
- `output_twitter/python/`: 데이터 저장 디렉토리.
- `total_scrap.py`: X 플랫폼 수집 루틴 추가.

## 4. 예외 처리 및 보안
- **Rate Limit**: API 요청 간 `random.uniform(2, 5)` 초 대기 적용.
- **Encoding**: 텍스트 저장 시 `utf-8-sig` 적용으로 한글 깨짐 방지.
- **Private Content**: 비공개 계정의 트윗 처리 예외 로직.
