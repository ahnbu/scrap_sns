---
title: "Plan: P2_Browser_Smoke_Testing"
created: "2026-03-10 17:42"
---

# Plan: P2_Browser_Smoke_Testing

## 1. Overview
- **Feature Name**: P2 단계: 브라우저 기반 Smoke 테스트 및 환경 분리
- **Description**: 실제 브라우저를 구동하여 SNS 플랫폼의 인증 상태와 수집 가능 여부를 검증하는 Smoke 테스트를 구축함. 일반 단위 테스트와 분리하여 효율적인 검증 환경을 제공함.
- **Priority**: Normal (P2)
- **Status**: Planning

## 2. Goals
- [ ] **인증 검증**: `auth/` 폴더에 저장된 세션 파일이 실제 유효한지(로그인 화면으로 리다이렉트되지 않는지) 자동 확인.
- [ ] **E2E Smoke Test**: 최소한의 데이터(1개)를 실제로 스크래핑하여 전체 파이프라인(브라우저 -> 네트워크 -> 파싱 -> 저장) 작동 여부 확인.
- [ ] **환경 분리**: `pytest -m smoke`와 같이 마커를 사용하여 로컬 로직 테스트와 브라우저 의존 테스트를 분리 실행.

## 3. Scope
### Included
- `tests/smoke/` 디렉토리 신설
- Threads/LinkedIn 브라우저 Smoke 테스트 구현 (`--limit 1` 모드 활용)
- `pytest.ini`에 `smoke` 마커 정의 및 설정
- 세션 만료 시 경고 또는 실패 처리 로직

### Excluded
- 전체 데이터 수집 성능 테스트 (P2 범위를 벗어남)
- 새로운 SNS 플랫폼 추가 (기존 플랫폼 안정화 우선)

## 4. Tasks (Checklist)
- [ ] **Task 1: Smoke 테스트 디렉토리 및 마커 설정**
  - `tests/smoke/` 생성 및 `pytest.ini` 업데이트
- [ ] **Task 2: Threads Smoke 테스트 구현**
  - `thread_scrap.py`의 진입점을 활용하여 1개 게시물 수집 성공 여부 확인
- [ ] **Task 3: LinkedIn Smoke 테스트 구현**
  - `linkedin_scrap.py`를 활용하여 세션 유효성 및 첫 게시물 감지 확인
- [ ] **Task 4: 통합 Smoke 런타임 최적화**
  - 헤드리스(Headless) 모드 지원 및 실행 시간 단축 설정

## 5. Success Criteria
- [ ] `pytest -m smoke` 실행 시 실제 브라우저가 구동되어 1분 내외로 모든 플랫폼의 상태를 보고함.
- [ ] 세션이 만료된 경우 테스트가 명확하게 실패하며, 원인(Authentication Required)을 명시함.
- [ ] 일반 `pytest` 실행 시(마커 미지정 시) 브라우저 테스트를 건너뛰어 실행 속도를 유지함.

## 6. Assumptions & Constraints
- 사용자의 `.env.local` 및 `auth/*.json` 파일이 로컬 환경에 존재해야 함.
- 네트워크 상태에 따라 타임아웃이 발생할 수 있으므로 적절한 retry 로직 고려.
