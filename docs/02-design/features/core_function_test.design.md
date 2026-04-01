---
title: "core function test.design"
created: "2026-03-10 00:00"
---

﻿# 핵심 기능 Playwright 자동화 테스트 설계 (v1.1)

> Version: 1.1.0 | Created: 2026-03-10 | Status: In Progress

## 1. Overview
통합 스크래핑 시스템의 모든 경로(Full/Update/Single)와 UI/API 레이어를 검증합니다.

## 2. Architecture (Updated)
### Components
- **Full Scrapers**: 	hread_scrap.py, linkedin_scrap.py, 	witter_scrap.py
- **Single Scrapers**: 	hread_scrap_single.py, 	witter_scrap_single.py
- **Auth Manager**: uth/ 폴더 내 JSON 세션 파일 관리
- **Viewer Engine**: server.py + index.html

## 3. Test Cases (Expansion)
| Category | Test Case | Target Scripts/Routes |
|----------|-----------|------------------------|
| **Smoke** | Session Validity | 	ests/smoke/test_*_smoke.py |
| **Unit** | Parser Logic | 	ests/unit/test_parsers.py |
| **Contract** | Metadata Schema | 	ests/contract/test_schemas.py |
| **E2E (New)** | Single Scrap Execution | 	hread_scrap_single.py, 	witter_scrap_single.py |
| **E2E (UI)** | Unified View | index.html Masonry Grid |

## 4. Single Scrap Test Plan
- **Threads**: 임의의 타래글 URL 입력 -> 수집 결과 JSON 확인
- **Twitter(X)**: 임의의 트윗 URL 입력 -> 수집 결과 JSON 확인

## 5. Auth Renewal Strategy
- Playwright headless=False 모드로 각 SNS 로그인 페이지를 띄워 사용자 로그인을 유도하고, 완료 후 storage_state를 저장하는 유틸리티 제공
