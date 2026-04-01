---
title: "Design: P1_Maintenance_and_Test_Framework"
created: "2026-03-10 17:34"
---

# Design: P1_Maintenance_and_Test_Framework

## 1. Overview
- **Feature Name**: P1 단계: 문서 최신화 및 자동 테스트 체계 구축
- **Plan Reference**: `docs/01-plan/features/p1_maintenance_test.plan.md`
- **Status**: Design

## 2. Technical Architecture

### 2.1 Documentation Structure (README.md)
새로운 `README.md`는 다음 섹션을 포함하도록 설계합니다.
1. **프로젝트 소개**: 스크랩 SNS 허브의 목적 및 주요 플랫폼(Threads, LinkedIn, Twitter) 설명.
2. **설치 가이드**: Python 환경 구성, Playwright 브라우저 설치, `.env` 설정.
3. **실행 명령어**:
   - 개별 스크래퍼 실행 (`python thread_scrap.py` 등)
   - 통합 스크래퍼 실행 (`python total_scrap.py`)
   - 웹 뷰어 실행 (`run_viewer.bat`)
4. **파일 구조**: 현재 프로젝트의 주요 파일 및 디렉토리 역할 설명.
5. **테스트 및 검증**: 새롭게 도입되는 `pytest` 실행 방법 안내.

### 2.2 Test Framework (pytest)
- **Directory**: `tests/` 폴더를 루트에 생성.
- **Organization**:
  - `tests/unit/`: 순수 로직(파싱, 정제, 정렬) 단위 테스트.
  - `tests/contract/`: API 응답 및 JSON 파일 스키마 검증.
  - `tests/fixtures/`: 테스트에 사용될 샘플 JSON 데이터.

### 2.3 JSON Schema Validation
산출물 JSON의 무결성을 검증하기 위한 필수 필드 규격입니다.
- **Threads**: `id`, `text`, `user_name`, `created_at` (ISO8601), `media` (list).
- **LinkedIn**: `id`, `text`, `author_name`, `published_at`, `images` (list).
- **Total**: `platform`, `id`, `text`, `timestamp`, `original_url`.

## 3. Implementation Details

### 3.1 README.md Update Strategy
- `list_directory`와 `glob`을 사용하여 실제 파일 목록을 추출하고, `README.md`의 기존 내용을 현재 상태에 맞게 교체함.
- 절대 경로 대신 상대 경로 및 환경 변수(`%USERPROFILE%` 등) 사용 가이드 제공.

### 3.2 Automated Test Cases
- **Test 1: Threads Parsing**: `thread_scrap.py`의 `clean_text` 함수가 HTML 태그를 올바르게 제거하는지 검증.
- **Test 2: LinkedIn ID Extraction**: URL에서 URN ID를 정확히 추출하는지 검증.
- **Test 3: Date Normalization**: 서로 다른 형식의 날짜 문자열이 표준 ISO 형식으로 변환되는지 검증.
- **Test 4: Metadata Matching**: 스크래퍼가 생성한 `total_count` 등이 `server.py`가 기대하는 키와 일치하는지 검증.

## 4. Acceptance Criteria (Design Verification)
- [ ] `README.md`에 기재된 모든 명령어가 실제 환경에서 에러 없이 실행 가능한가?
- [ ] `tests/` 구조가 기존 코드의 import 문제를 일으키지 않는가?
- [ ] 정의된 JSON 스키마가 기존의 성공적인 산출물과 호환되는가?

## 5. Risks & Mitigations
- **Risk**: SNS 레이아웃 변경으로 인한 파싱 로직 실패.
- **Mitigation**: 테스트 케이스에 실제 실패 사례(Snapshot)를 추가하여 레이아웃 변경 시 즉각 감지하도록 구성.
