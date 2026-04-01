---
title: "threads_sequence_id_improvement Plan Document"
created: "2026-02-13 00:00"
---

# threads_sequence_id_improvement Plan Document

> Version: 1.1.0 | Updated: 2026-02-13 | Status: Approved

## 1. Executive Summary
Threads '저장됨' 목록의 실제 노출 순서(최근 저장순)를 웹 뷰어의 `sequence_id`에 정확히 반영하기 위한 개선 계획입니다.

## 2. Goals and Objectives
- **순서 정합성**: Threads '저장됨' 리스트 상단의 게시글(최신 저장)이 가장 큰 `sequence_id`를 갖도록 보장.
- **물리적 순서 신뢰**: API 응답 및 로그 출력 순서를 '저장 순서'의 절대적 기준으로 채택.
- **중복 제거 안정화**: DOM/Network 데이터 병합 시 수집 순서(Order)가 파괴되지 않도록 로직 강화.

## 3. Scope
### In Scope
- `thread_scrap.py`의 수집 데이터 병합(`unique_posts`) 로직 수정.
- 수집된 신규 리스트를 `reverse()` 처리한 후 `sequence_id`를 부여하는 프로세스 구현.
- 파이썬의 순서 보존 사전(Order-preserving Dict)을 활용한 데이터 정합성 유지.

## 4. Success Criteria
- 웹 뷰어에서 정렬했을 때 Threads 사이트의 '저장됨' 목록과 동일한 순서로 표시됨.
- `sequence_id`가 누락되거나 중복되지 않고 연속성을 유지함.

## 5. Timeline
- [Done] Plan (v1.1.0)
- [Next] Design & Implementation
- [Next] Report
