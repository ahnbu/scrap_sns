---
title: "Plan: SNS 플랫폼 데이터 필드 순서 통일 (Field Order Unification)"
created: "2026-02-12 16:38"
---

# Plan: SNS 플랫폼 데이터 필드 순서 통일 (Field Order Unification)

## 1. 개요 (Overview)
현재 각 플랫폼별로 저장되는 JSON 데이터의 필드 순서가 일정하지 않아 가독성이 떨어지고 데이터 구조 파악이 어렵습니다. 모든 플랫폼 데이터에 공통적으로 존재하는 핵심 필드들을 상단으로 배치하고, 플랫폼별 특수 필드들을 하단으로 배치하여 일관된 데이터 구조를 확보하고자 합니다.

## 2. 현상 분석 및 원인 진단 (Analysis & Diagnosis)
- **현상**: `twitter_scrap.py`, `thread_scrap.py`, `linkedin_scrap.py` 등 각 스크래퍼에서 `dict`를 생성하는 순서가 제각각임.
- **원인**: 초기 개발 시 플랫폼별 응답 구조를 따라가거나, 기능 추가 과정에서 필드가 임의의 위치에 삽입되었기 때문임.
- **결과**: JSON 파일을 직접 열어보거나 디버깅할 때 핵심 정보(작성자, 본문 등)를 찾는 데 시간이 소요됨.

## 3. 개선 계획 (Proposed Plan)

### 3.1 표준 필드 순서 정의
모든 게시물 객체는 아래 순서로 필드를 정렬함을 원칙으로 합니다.

1.  `sequence_id`: 전역 정렬 순번
2.  `platform_id`: 플랫폼 원본 ID
3.  `sns_platform`: 플랫폼 구분
4.  `username`: 사용자 핸들 (@id)
5.  `display_name`: 사용자 실제 이름
6.  `full_text`: 본문 내용
7.  `media`: 미디어 URL 배열
8.  `url`: 게시물 원본 링크
9.  `created_at`: 작성 일시
10. `date`: 작성 날짜
11. `crawled_at`: 수집 시점
12. `source`: 수집 경로
13. `local_images`: 로컬 저장 이미지 경로
14. (기타 플랫폼별 확장 필드: `like_count`, `reply_count`, `profile_slogan` 등)

### 3.2 단계별 실행 계획
1.  **[Design]** 표준 필드 순서를 강제하는 정렬 함수(`reorder_post`) 설계.
2.  **[Do]** 
    - 모든 스크래퍼(`twitter_scrap.py`, `thread_scrap.py`, `linkedin_scrap.py`, `total_scrap.py`)의 데이터 생성/저장 부위에 정렬 로직 적용.
    - 기존 마이그레이션 스크립트(`migrate_schema.py`)를 확장하여 기존 파일 전수 재정렬 수행.
3.  **[Check]** 샘플 JSON 파일을 로드하여 필드 순서가 정의된 표준과 일치하는지 검증.

## 4. 기대 효과 (Expected Benefits)
- **가독성 향상**: 어떤 플랫폼 데이터든 동일한 위치에서 핵심 정보를 바로 확인 가능.
- **디버깅 효율화**: 데이터 일관성이 확보되어 필드 누락이나 오기입을 쉽게 발견 가능.
- **표준화 완성**: 앞서 수행한 필드명 통합 작업에 이어 데이터 구조의 물리적 순서까지 표준화 완료.
