---
title: "threads_update_mode_logic_fix Plan Document"
created: "2026-02-13 00:00"
---

# threads_update_mode_logic_fix Plan Document

> Version: 1.0.0 | Created: 2026-02-13 | Status: Draft

## 1. Executive Summary
Threads 스크래핑의 `update` 모드에서 중복 체크(Stop Code)가 제대로 작동하지 않고 전체 데이터를 다시 수집하는 문제를 해결하기 위한 계획입니다.

## 2. Goals and Objectives
- `update` 모드 실행 시, 기존 데이터의 최상단(가장 최근 저장된 항목)을 정확히 인식하여 중복 수집 없이 즉시 중단되도록 로직 수정.
- JSON 저장 시 항상 가장 최근에 저장/수집된 항목이 상단(`posts[0]`)에 오도록 정합성 유지.
- `stop_codes` 추출 기준을 `sequence_id`가 아닌 실제 리스트 순서(물리적 최신순)로 고정.

## 3. Scope
### In Scope
- `thread_scrap.py`의 `stop_codes` 추출 로직 수정.
- 수집 및 병합 시의 리스트 순서 처리(Reverse/Sort) 로직 검증 및 수정.
- 기존 JSON 파일의 데이터 순서가 뒤집혀 있는 경우에 대한 대응.

### Out of Scope
- 타 플랫폼 스크래퍼 수정.
- 데이터베이스 스키마 변경.

## 4. Success Criteria
- `update` 모드 실행 시, 신규 게시물이 없을 경우 첫 페이지 스캔 후 즉시 "기준 게시물 발견" 메시지와 함께 종료됨.
- 로그에 찍히는 수집 순서와 JSON 파일의 상단 항목 순서가 일치함.

## 5. Timeline
- Plan: 2026-02-13
- Design & Implementation: 2026-02-13
- Verification: 2026-02-13
