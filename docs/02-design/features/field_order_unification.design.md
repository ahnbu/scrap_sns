---
title: "Design: SNS 플랫폼 데이터 필드 순서 통일"
created: "2026-02-12 16:39"
---

# Design: SNS 플랫폼 데이터 필드 순서 통일

## 1. 표준 필드 순서 정의 (Field Order List)
데이터 객체 생성 시 아래 리스트의 순서를 엄격히 준수합니다.

```python
STANDARD_FIELD_ORDER = [
    "sequence_id",
    "platform_id",
    "sns_platform",
    "username",
    "display_name",
    "full_text",
    "media",
    "url",
    "created_at",
    "date",
    "crawled_at",
    "source",
    "local_images"
]
```

## 2. 재정렬 로직 설계 (Implementation Logic)

### 2.1 Python 유틸리티 함수
모든 스크래퍼 및 마이그레이션 스크립트에서 공통으로 사용할 수 있는 정렬 로직입니다.

```python
def reorder_post(post):
    ordered_post = {}
    # 1. 표준 필드 순서대로 우선 배치
    for field in STANDARD_FIELD_ORDER:
        if field in post:
            ordered_post[field] = post[field]
    
    # 2. 리스트에 없는 나머지 필드(플랫폼 특수 필드)를 뒤에 배치
    for key, value in post.items():
        if key not in ordered_post:
            ordered_post[key] = value
            
    return ordered_post
```

## 3. 적용 대상 코드 및 파일

### 3.1 스크래퍼 (Scrapers)
- `twitter_scrap.py`: `extract_from_json`, `extract_from_html` 반환 직전 적용.
- `thread_scrap.py`: `process_network_post`, `run` (DOM) 내 객체 생성 시 적용.
- `linkedin_scrap.py`: `extract_post_from_view_model` 내 적용.
- `total_scrap.py`: `merge_results`, `save_total` 단계에서 최종 적용.

### 3.2 기존 데이터 마이그레이션
- `migrate_schema.py`를 수정하여 `Deep Cleaning` 시 `reorder_post` 함수를 호출하도록 함.

### 3.3 웹 뷰어 데이터
- `web_viewer/data.js` 내의 모든 게시물 객체도 재정렬된 상태로 저장.

## 4. 검증 계획 (Verification)
- `reorder_post`를 거친 후 `list(post.keys())[:5]`를 출력하여 `sequence_id`, `platform_id` 등이 상단에 위치하는지 확인.
