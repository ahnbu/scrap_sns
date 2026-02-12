---
trigger: always_on
glob: "**/*.{py,js,json}"
description: SNS 데이터 스키마 표준 규격 및 필드 순서 준수 규칙
---

# SNS Data Schema Rules

이 프로젝트에서 생성되거나 처리되는 모든 SNS 데이터 객체는 아래의 표준 규격과 필드 순서를 엄격히 준수해야 합니다.

## 1. 표준 필드 및 정렬 순서 (Strict Order)

데이터 객체(JSON/Dict) 저장 시 반드시 아래 순서대로 필드를 배치하십시오.

1.  `sequence_id`: (Integer) 전역 정렬 순번
2.  `platform_id`: (String) 플랫폼 고유 ID
3.  `sns_platform`: (String) 플랫폼 구분 (twitter, threads, linkedin, substack)
4.  `username`: (String) 사용자 핸들
5.  `display_name`: (String) 사용자 실제 성함
6.  `full_text`: (String) 본문 내용
7.  `media`: (Array) 미디어 URL 배열 (데이터 없어도 `[]` 필수)
8.  `url`: (String) 원본 게시물 링크
9.  `created_at`: (String) 작성 일시
10. `date`: (String) 작성 날짜 (YYYY-MM-DD)
11. `crawled_at`: (String) 수집 시점 (YYYY-MM-DD HH:MM:SS)
12. `source`: (String) 수집 경로 (python, browser 등)
13. `local_images`: (Array) 로컬 이미지 경로 (데이터 없어도 `[]` 필수)

## 2. 준수 사항

- **불변성 및 정렬**: 데이터를 병합하거나 수정할 때 위 순서가 깨지지 않도록 하십시오. 파이썬의 경우 `dict` 생성 시 순서를 지키거나 `OrderedDict`를 고려하십시오.
- **중복 제거**: 새로운 데이터를 추가할 때 `platform_id` 또는 `url`을 기준으로 기존 데이터와의 중복 여부를 반드시 체크하십시오.
- **타입 엄격성**: 배열 형태의 필드(`media`, `local_images`)는 절대 `null`이나 `None`이 되어서는 안 되며, 데이터가 없으면 빈 배열(`[]`)로 초기화해야 합니다.
