---
title: "Plan: P1_Maintenance_and_Test_Framework"
created: "2026-03-10 17:34"
---

# Plan: P1_Maintenance_and_Test_Framework

## 1. Overview
- **Feature Name**: P1 단계: 문서 최신화 및 자동 테스트 체계 구축
- **Description**: 진단 보고서에서 식별된 P1 과업을 수행하여 프로젝트의 운영 가시성을 높이고 회귀 테스트 가능성을 확보함.
- **Priority**: High (P1)
- **Status**: Planning

## 2. Goals
- [ ] **문서 동기화**: `README.md`를 현재의 파일 구조 및 실행 방식에 맞게 전면 수정.
- [ ] **테스트 자동화**: `assertion`이 포함된 `pytest` 기반의 단위 테스트(Unit Test) 초기 세트 구축.
- [ ] **검증 체계**: 스크래핑 산출물(JSON)의 스키마 및 필수 필드 존재 여부를 자동으로 검증하는 로직 도입.

## 3. Scope
### Included
- `README.md` 최신화 (설치 방법, 실행 명령어, 파일 구조 설명)
- `tests/` 디렉토리 신설 및 기본 단위 테스트 작성
  - Threads/LinkedIn/Twitter 파싱 로직 검증 (Mock 데이터 사용)
  - JSON 산출물 스키마 검증 (Schema Validation)
- `server.py` API 응답 규격 정의 및 테스트

### Excluded
- 브라우저 연동 실시간 스크래핑 전체 테스트 (P2 단계 Smoke Test로 이월)
- CI/CD 파이프라인 연동 (인프라 환경 구축 필요)

## 4. Tasks (Checklist)
- [ ] **Task 1: README.md 현행화**
  - 현재 파일 구조 조사
  - 실행 옵션 및 환경 변수 설정 가이드 업데이트
- [ ] **Task 2: 테스트 환경 설정**
  - `pytest` 및 필요한 라이브러리 설치/확인
  - 테스트용 Fixture 데이터(JSON) 준비
- [ ] **Task 3: 핵심 로직 단위 테스트 구현**
  - `thread_scrap.py`, `linkedin_scrap.py` 등의 파싱/정제 함수 테스트
- [ ] **Task 4: 산출물 스키마 검증 도구 작성**
  - 생성된 JSON 파일의 무결성 검사 스크립트 작성

## 5. Success Criteria
- [ ] `README.md`에 기술된 설치/실행 가이드가 실제 환경과 100% 일치함.
- [ ] `pytest` 실행 시 최소 5개 이상의 핵심 로직 테스트 케이스가 통과함.
- [ ] 잘못된 형식의 JSON 산출물을 감지하는 검증 스크립트가 정상 작동함.

## 6. Assumptions & Constraints
- 기존에 작성된 `test_logic_refinement.py` 등은 참고용으로 사용하며, 새로운 테스트 구조로 점진적 이관함.
- SNS 인증 문제로 인해 실제 네트워크 호출이 아닌 로컬 JSON 파일을 이용한 Mock 테스트를 우선함.
