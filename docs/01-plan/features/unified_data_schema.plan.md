---
title: "[Plan] 데이터 스키마 표준 규격 정의 및 에이전트 규칙 반영"
created: "2026-02-12 15:47"
---

# [Plan] 데이터 스키마 표준 규격 정의 및 에이전트 규칙 반영

## 1. 개요 (Overview)
현재 SNS 크롤링 데이터의 필드 순서가 플랫폼마다 상이하고, 중복 데이터 처리 방식이 파편화되어 있습니다. 이를 해결하기 위해 표준 데이터 스키마 규격을 정의하고, 이를 에이전트가 코딩 시 항상 준수할 수 있도록 `.agent/rules/data-schema.md` 파일에 명문화합니다.

## 2. 참고 자료 (References)
- `docs/01-plan/features/data_deduplication.plan.md`: 중복 제거 로직 원칙
- `docs/01-plan/features/field_order_unification.plan.md`: 필드 순서 통일 원칙

## 3. 해결 방안 (Proposed Solution)

### 3.1 표준 필드 순서 및 명칭 확정
모든 게시물(Post) 객체는 아래 순서와 명칭을 따릅니다.
1. `sequence_id`: (Integer) 전역 정렬 순번
2. `platform_id`: (String) 플랫폼 원본 고유 ID (Twitter ID, LinkedIn ID 등)
3. `sns_platform`: (String) 플랫폼 구분 (twitter, threads, linkedin, substack)
4. `username`: (String) 사용자 핸들 (@id)
5. `display_name`: (String) 사용자 실제 이름
6. `full_text`: (String) 본문 내용
7. `media`: (Array) 미디어 URL 배열
8. `url`: (String) 게시물 원본 링크
9. `created_at`: (String) 작성 일시 (ISO 8601 권장)
10. `date`: (String) 작성 날짜 (YYYY-MM-DD)
11. `crawled_at`: (String) 수집 시점 (YYYY-MM-DD HH:MM:SS)
12. `source`: (String) 수집 경로 (python, browser_console 등)
13. `local_images`: (Array) 로컬 저장 이미지 경로 배열
14. (확장 필드): 플랫폼별 특수 필드 (like_count, reply_count, profile_slogan 등)

### 3.2 중복 제거 기준 정의
- **기준 필드**: `platform_id` 또는 `url`(또는 Threads의 경우 `code`)을 고유 키로 사용하여 병합 시 중복을 제거함.
- **처리 방식**: 새로운 데이터 수집 시 기존 `total_full_*.json` 데이터를 로드하여 고유 키가 존재하지 않는 경우에만 추가함.

### 3.3 에이전트 규칙(Rule) 반영
- `.agent/rules/data-schema.md` 파일을 생성하여 위 규격을 명시함.
- `trigger: always_on` 설정을 통해 에이전트가 코드를 작성하거나 수정할 때 이 규격을 참조하도록 강제함.

## 4. 상세 계획 (Tasks)
1. [ ] 표준 데이터 스키마 상세 명세 작성 (디자인 단계에서 구체화).
2. [ ] `.agent/rules/data-schema.md` 파일 생성 및 내용 작성.
3. [ ] `coding-style.md`에 `data-schema.md` 참조 규칙 추가 여부 검토.
4. [ ] 기존 스크래퍼 코드(`twitter_scrap.py`, `thread_scrap.py` 등)에 이 규격이 반영되어 있는지 확인 (향후 구현 과제).

## 5. 기대 효과
- 에이전트가 생성하는 코드가 일관된 데이터 구조를 보장함.
- 데이터 병합 및 웹 뷰어 로딩 시의 오류 가능성 감소.
- 데이터 가독성 및 유지보수성 향상.
