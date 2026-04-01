---
title: "Plan: X(Twitter) 스크래퍼 중복 데이터 및 필드 불일치 해결"
created: "2026-02-12 13:28"
---

# Plan: X(Twitter) 스크래퍼 중복 데이터 및 필드 불일치 해결

이 문서는 X(Twitter) 스크래핑 과정에서 발생하는 동일 게시물의 중복 생성 및 필드명/데이터 정보 누락 문제를 해결하기 위한 계획을 담고 있습니다.

## 1. 현상 분석
- **중복 발생**: 동일한 URL의 게시물이 JSON(네트워크)과 HTML(DOM) 두 경로에서 각각 수집됨.
- **필드 불일치**: 일부 데이터는 `full_text` 대신 `body` 필드를 사용함.
- **정보 누락**: 네트워크 패킷 수집 시 사용자 이름(`display_name`)이나 아이디(`user`)가 누락되는 경우가 발생하며, 이후 DOM 수집 데이터가 이를 덮어씌우는 과정에서 데이터 정합성이 깨짐.

## 2. 근본 원인
- `all_posts_map` 업데이트 시 단순 덮어쓰기 로직(`all_posts_map[url] = post`) 사용.
- 네트워크(Full 버전) 데이터와 DOM(축약 버전) 데이터의 우선순위가 정립되지 않음.
- `extract_from_json` 함수 내 일부 코드 경로에서 표준 스키마 외의 필드명이 사용될 가능성 존재.

## 3. 해결 전략
### 3.1 정보 보존형 병합 로직 도입
- 게시물 업데이트 시 다음 우선순위를 적용하는 `merge_post_data(existing, new)` 함수 구현:
    1. 본문(`full_text`): 더 긴 문자열을 가진 데이터를 유지.
    2. 미디어(`media`): 두 리스트를 합친 후 중복 제거.
    3. 사용자 정보: 비어있는 경우 새로 들어온 정보로 보완.

### 3.2 스키마 강제 적용
- 모든 추출 함수(`extract_from_json`, `extract_from_html`)의 반환 객체에서 `body` 필드를 완전히 배제하고 `full_text`로 통일.

### 3.3 사용자 정보 추출 보강
- `extract_from_json`에서 `core`, `user_results` 경로 외에도 `unmention_info`나 `author` 등 대체 경로 확인 로직 추가.

## 4. 진행 단계 (PDCA)
1. **[Plan]**: (현재) 문제 원인 분석 및 해결 전략 수립.
2. **[Design]**: 병합 로직 및 보강된 추출 경로 상세 설계.
3. **[Do]**: `twitter_scrap.py` 코드 수정 및 로컬 테스트.
4. **[Check]**: `twitter_py_full_*.json` 결과물 검증.
5. **[Act]**: 최종 통합 DB(`total_scrap.py`)와 동기화.
