---
title: "core function test.plan"
created: "2026-03-10 00:00"
---

﻿# 핵심 기능 Playwright 자동화 테스트 계획 (v1.1)

> Version: 1.1.0 | Created: 2026-03-10 | Status: In Progress

## 1. Executive Summary
Threads, LinkedIn, Twitter(X)를 포함한 모든 SNS 플랫폼의 데이터 수집과 개별 타래글 수집(Single Scrap) 기능의 안정성을 Playwright를 활용하여 검증합니다.

## 2. Goals and Objectives
- **Threads/X/LinkedIn**: 전체 수집 및 증분 업데이트 기능 검증
- **Single Scrap**: 개별 URL 기반 타래글 수집 기능(Thread/X) 검증
- **Auth Persistence**: 각 플랫폼별 세션 유지 상태 확인 및 갱신 프로세스 확립
- **Unified Schema**: 수집된 데이터가 공통 JSON 스키마를 따르는지 검증

## 3. Scope
### In Scope
- Web Viewer UI 및 Backend API 연동 테스트
- SNS 플랫폼별 연기 테스트 (Smoke Test)
- 개별 수집 스크립트 (	hread_scrap_single.py, 	witter_scrap_single.py) 실행 검증
- 세션 갱신 자동화 가이드 제공

### Out of Scope
- 페이스북/서브스택 등 기타 플랫폼 (추후 확장 가능)

## 4. Success Criteria
| Criterion | Metric | Target |
|-----------|--------|--------|
| 전 플랫폼 Smoke 테스트 | 로그인 및 목록 로딩 성공 | 100% |
| Single Scrap 성공 | 지정된 URL 데이터 수집 완료 | 100% |
| 데이터 통합 무결성 | JSON 스키마 검증 통과 | 100% |

## 5. Timeline (Updated)
| Milestone | Date | Description |
|-----------|------|-------------|
| 세션 통합 갱신 | 2026-03-10 | Threads, LinkedIn, X 세션 수동 로그인 및 저장 |
| Single Scrap 테스트 | 2026-03-10 | 개별 수집 스크립트 단위 테스트 실행 |
| 통합 E2E 테스트 | 2026-03-10 | 전체 UI 및 API 연동 최종 확인 |

## 6. Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| SNS 봇 탐지 정책 | 계정 차단 | 수집 주기 조절 및 세션 갱신 빈도 관리 |
| 레이아웃 변경 | 파싱 실패 | 정기적인 Smoke 테스트로 조기 감지 |
