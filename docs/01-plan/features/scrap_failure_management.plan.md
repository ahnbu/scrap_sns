---
title: "Plan: Scraping Failure Management & Retry Limit"
created: "2026-02-11 15:32"
---

# Plan: Scraping Failure Management & Retry Limit

계속해서 수집에 실패하는 항목들(Fail/Empty)로 인해 발생하는 리소스 낭비를 방지하기 위해, 실패 이력을 관리하고 재시도 횟수를 제한하는 로직을 도입합니다.

## 1. 목적
- 반복적으로 실패하는 URL에 대한 무의미한 시도 차단
- 전체 스크래핑 시간 단축 및 리소스 최적화
- 실패 원인 분석을 위한 이력 관리

## 2. 핵심 설계 (Core Design)
- **실패 관리 파일**: `scrap_failures.json` (새로 생성)
- **데이터 구조**:
  ```json
  {
    "CODE_HERE": {
      "username": "user",
      "fail_count": 3,
      "last_attempt": "2026-02-11T...",
      "last_error": "No data found in HTML",
      "status": "ignored" 
    }
  }
  ```
- **동작 규칙**:
  1. 스크래핑 전 `scrap_failures.json`을 로드하여 `fail_count >= 3`인 항목은 스캔 대상에서 제외.
  2. 스크래핑 실패 시(Fail/Empty) 해당 항목의 `fail_count`를 1 증가시키고 저장.
  3. 스크래핑 성공 시 해당 항목이 실패 리스트에 있다면 삭제(초기화).

## 3. 실행 단계
1. **파일 관리 로직 추가**: `scrap_single_post.py`에 실패 이력을 로드/저장하는 함수 구현.
2. **필터링 로직 수정**: `run()` 함수 내 대상 식별 단계에서 실패 횟수 기반 필터링 적용.
3. **결과 반영 로직 수정**: `worker` 종료 후 결과에 따라 실패 횟수 업데이트.

## 4. 기대 결과
- 3회 이상 실패한 12개 항목이 다음 실행부터 스캔 대상에서 자동 제외됨.
- 신규 데이터가 없을 경우 실행 시간이 수 초 내로 단축됨.
