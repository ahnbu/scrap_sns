---
title: "threads_image_enrichment Planning Document"
created: "2026-02-12 00:00"
---

# threads_image_enrichment Planning Document

> **Summary**: 쓰레드 게시물의 누락된 이미지를 1회성 전체 재스크래핑을 통해 보강함.
>
> **Project**: scrap_sns
> **Version**: 1.0.0
> **Author**: Gemini CLI Agent
> **Date**: 2026-02-12
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

기존에 스크랩된 쓰레드(Threads) 게시물 중 이미지(`media`)가 누락된 항목들이 존재함. 이를 해결하기 위해 전체 게시물을 재스크랩하여 누락된 이미지 정보를 보강함.

### 1.2 Background

스크래핑 과정에서의 일시적인 네트워크 오류, DOM 로딩 지연 등으로 인해 일부 게시물의 이미지 URL이 수집되지 않은 채 저장됨. 중복 체크를 일시적으로 비활성화하거나 보강 로직을 추가하여 데이터의 완성도를 높일 필요가 있음.

### 1.3 Related Documents

- Requirements: 사용자의 이미지 보강 요청
- References: `thread_scrap.py`, `total_scrap.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] `thread_scrap.py`의 스크래핑 로직 검토 및 1회성 전체 수집 모드 추가
- [ ] 수집된 데이터와 기존 데이터 병합 시 이미지 누락 여부에 따른 업데이트 로직 구현
- [ ] 재스크래핑 실행 및 결과 검증

### 2.2 Out of Scope

- 타 플랫폼(LinkedIn, Twitter 등)의 이미지 보강
- 이미지 로컬 다운로드 로직 (URL 수집에 집중)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 중복 체크를 건너뛰고 모든 게시물을 다시 수집하는 기능 | High | Pending |
| FR-02 | 기존 데이터에 이미지가 없을 경우에만 새로운 이미지 정보를 보충하는 병합 로직 | High | Pending |
| FR-03 | 수집된 이미지 URL의 유효성 검증 (scontent 등 특정 패턴 확인) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Stability | 스크래핑 중 차단 방지를 위한 적절한 지연 시간 유지 | 실행 로그 확인 |
| Integrity | 기존 데이터의 다른 필드(텍스트, 날짜 등)가 훼손되지 않아야 함 | JSON 파일 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `thread_scrap.py` 실행 시 전체 수집 옵션이 정상 작동함
- [ ] 재스크랩 후 `output_threads/python/` 아래의 파일에서 누락되었던 `media` 필드가 채워짐
- [ ] 전체 병합 프로세스(`total_scrap.py`) 실행 후 최종 데이터에 반영됨

### 4.2 Quality Criteria

- [ ] 이미지 누락률 5% 이하로 감소 (수동 샘플링 검사)
- [ ] JSON 구조의 일관성 유지

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 계정 차단(Rate Limit) | High | Medium | 수집 속도 조절 및 세션 관리 |
| 데이터 중복 생성 | Medium | Low | `platform_id` 기반의 정밀한 병합 로직 사용 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Dynamic** | Feature-based modules, services layer | Web apps with backend, SaaS MVPs | ✅ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Implementation Mode | Script modification | Argument based | 기존 스크립트를 유지하면서 옵션으로 전체 수집 가능하게 함 |
| Data Storage | JSON files | JSON (Existing) | 기존 파이프라인과의 호환성 유지 |

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `GEMINI.md` 및 `.agent/rules/coding-style.md` 준수
- [x] `platform_id`를 기준으로 데이터 식별

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Image URL Filtering** | Partly exists | 정교한 이미지 소스 필터링 규칙 | Medium |

---

## 8. Next Steps

1. [ ] 디자인 문서 작성 (`threads_image_enrichment.design.md`)
2. [ ] `thread_scrap.py` 수정 및 테스트 실행
3. [ ] 병합 로직 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-12 | Initial draft | Gemini CLI Agent |
