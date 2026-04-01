---
title: "substack_scraper 기획서"
created: "2026-02-08 00:00"
template: plan
version: 1.0
description: Substack 아카이브 게시글 스크래퍼 기획
---

# substack_scraper 기획서

> **요약**: 특정 Substack 사용자의 아카이브 페이지에서 게시글 목록을 추출하여 JSON 형식으로 저장하는 스크래퍼를 구현합니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.0.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-08
> **상태**: 진행 중

---

## 1. 개요

### 1.1 목적

Substack 아카이브 페이지(`https://{user_name}.substack.com/archive`)에 게시된 모든 글의 제목, 날짜, 요약, 링크 등을 수집하여 체계적으로 저장합니다.

### 1.2 배경

- 사용자가 Substack의 고유 콘텐츠를 로컬에 보관하고 검색하거나 분석하기를 원함.
- 기존 링크드인 스크래퍼와 유사한 저장 구조 및 관리 방식을 유지하여 프로젝트의 일관성을 확보함.

---

## 2. 범위

### 2.1 대상 범위

- [ ] CLI 인자로 `user_name`을 입력받아 타겟 URL 생성
- [ ] Substack 아카이브 페이지(`list.html` 구조)의 무한 스크롤 처리 및 게시글 URL 목록 수집
- [ ] **개별 게시글 상세 수집 및 정제** (`each_article.html` 구조):
    - 본문 전체 내용 추출 및 **HTML 정제 (Cleanup)**:
        - `header-anchor-parent` 등 UI/기능성 요소 제거
        - 불필요한 속성(`data-*`, `tabindex`, `class` 등) 정리
        - 빈 태그(`<p></p>`) 및 중복 헤더 처리
    - 제목, 부제목, 작성자, 정확한 작성 일자 추출 및 검증
    - 본문 내 포함된 모든 이미지 및 미디어 링크 리스트업
- [ ] 데이터 저장:
    - 기본 경로: `output_substack/{user_name}/`
    - 업데이트 경로: `output_substack/{user_name}/update/`
    - 파일명 규칙: `substack_{user_name}_full_YYYYMMDD.json`, `substack_{user_name}_update_YYYYMMDD_HHMMSS.json`

### 2.2 제외 범위

- 하단 추천 게시글, 댓글, 사이드바 요소
- **UI 컨트롤 요소** (공유 버튼, 좋아요 버튼, 앵커 링크 버튼 등)

---

## 3. 요구사항

### 3.1 기능적 요구사항

| ID | 요구사항 | 우선순위 | 상태 |
|----|----------|----------|------|
| FR-01 | `user_name` 기반 동적 URL 생성 (`https://{user_name}.substack.com/archive`) | 높음 | 대기 |
| FR-02 | Playwright를 이용한 아카이브 페이지 스크롤 및 링크 추출 | 높음 | 대기 |
| FR-03 | **BeautifulSoup을 활용한 본문 HTML 정제**: 텍스트와 핵심 구조만 남기고 UI 코드 제거 | 높음 | 대기 |
| FR-04 | 수집된 데이터의 중복 체크 및 `sequence_id` 부여 | 높음 | 대기 |
| FR-05 | `created_at` 정보의 무결성 확보 (목록과 상세 페이지 상호 보완) | 보통 | 대기 |

### 3.2 비기능적 요구사항

| 카테고리 | 기준 | 측정 방법 |
|----------|------|-----------|
| 일관성 | `output_substack` 구조가 `output_linkedin_user`와 동일해야 함 | 폴더 구조 확인 |
| 안정성 | 페이지 로딩 대기 및 에러 핸들링 로직 포함 | 테스트 실행 |

---

## 4. 성공 기준

### 4.1 완료 정의 (Definition of Done)

- [ ] `substack_scrap_by_user.py` 실행 시 지정된 폴더에 JSON 파일이 정상 생성됨.
- [ ] 파일명 및 폴더명에 `user_name`이 정확히 반영됨.
- [ ] 최신순 정렬 및 Full/Update 버전 분리 저장이 정상 작동함.

---

## 5. 아키텍처 고려 사항

### 5.1 주요 설계 결정

- **기술 스택**: Playwright (Python)
- **데이터 구조**: `metadata`와 `posts` 배열을 포함하는 JSON 객체.
- **정렬**: 게시글 날짜 기준 내림차순 정렬.

---

## 6. 향후 단계

1. [ ] 디자인 문서 작성 (`substack_scraper.design.md`)
2. [ ] 초기 프로토타입 구현 및 `edwardhan99` 계정 테스트
3. [ ] 결과 검증 및 보고서 작성
