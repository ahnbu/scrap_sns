---
title: "Detailed Design: X(Twitter) 타래 수집 시스템 및 통합 스키마 설계"
created: "2026-02-12 13:34"
---

# Detailed Design: X(Twitter) 타래 수집 시스템 및 통합 스키마 설계

이 문서는 X(Twitter)의 목록 수집과 상세 타래 수집을 분리하고, Threads 시스템과 동일한 데이터 구조 및 파이프라인을 구축하기 위한 상세 설계 내용을 담고 있습니다.

## 1. 파이프라인 구조 (Producer-Consumer)

### 1.1 twitter_scrap.py (Producer)

- **역할**: 북마크 목록 스캔 및 URL 확보.
- **입력**: X 북마크 페이지 (`https://x.com/i/bookmarks`).
- **출력**: `output_twitter/python/twitter_py_simple_full_{YYYYMMDD}.json`.
- **필드 특징**: `is_detail_collected: false` 플래그를 기본값으로 설정.

### 1.2 twitter_scrap_single.py (Consumer) - _신규_

- **역할**: 각 트윗의 상세 페이지를 방문하여 전체 타래 병합.
- **입력**: `twitter_py_simple_full_{YYYYMMDD}.json`.
- **출력**: `output_twitter/python/twitter_py_full_{YYYYMMDD}.json`.
- **병합 로직**:
  - 동일 작성자의 연속된 답글을 `---`로 구분하여 `full_text`에 병합.
  - 타래에 포함된 모든 미디어(이미지, 영상)를 `media` 리스트에 통합.

## 2. 데이터 스키마 (Standard Schema v1.1)

Threads 및 LinkedIn과의 호환성을 위해 아래 필드명을 엄격히 준수합니다.

| 필드명         | 타입   | 설명                                          |
| :------------- | :----- | :-------------------------------------------- |
| `id`           | String | 플랫폼 고유 ID (Twitter rest_id)              |
| `user`         | String | 사용자 핸들 (@username)                       |
| `display_name` | String | 사용자 표시 이름                              |
| `full_text`    | String | 병합된 전체 본문                              |
| `media`        | Array  | 전체 이미지/영상 URL 리스트                   |
| `timestamp`    | String | YYYY-MM-DD HH:MM:SS                           |
| `date`         | String | YYYY-MM-DD                                    |
| `url`          | String | 원본 게시글 주소                              |
| `sns_platform` | String | 'x'                                           |
| `source`       | String | 'initial_dom', 'network', 'full_twitter_scan' |

## 3. 상세 구현 전략

### 3.1 타래 추적 알고리즘

1. 메인 트윗(`article`)의 작성자 정보를 획득.
2. 하단으로 스크롤하며 나타나는 `article` 요소들을 순회.
3. 작성자가 메인 트윗 작성자와 일치하는 동안 텍스트와 미디어를 누적.
4. "Show more" 버튼 발견 시 자동 클릭.
5. 다른 작성자의 댓글이나 광고가 나타나면 해당 타래 수집 종료.

### 3.2 세션 관리

- `auth/x_user_data` (Chrome Persistent Context)를 공유하여 별도의 로그인 과정 없이 즉시 수집 진행.

### 3.3 통합 병합 (total_scrap.py)

- `twitter_py_full_*.json` 데이터를 최종 소스로 사용하여 통합 DB 갱신.
- X 브랜드 명칭을 'twitter'에서 'x'로 최종 변환 처리.
