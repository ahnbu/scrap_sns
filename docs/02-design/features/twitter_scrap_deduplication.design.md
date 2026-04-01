---
title: "PDCA 설계: Twitter 수집 로직 개선 및 중복 방지 설계"
created: "2026-02-12 00:00"
---

# PDCA 설계: Twitter 수집 로직 개선 및 중복 방지 설계

## 1. 개요 (Overview)
중복된 `full_text` 수집 문제를 해결하기 위해 `twitter_scrap.py`와 `twitter_scrap_single.py`의 추출 로직을 강화합니다.

## 2. 주요 개선 설계 (Key Improvements)

### 2.1. 인용 트윗(Quote Tweet) 구분 로직 강화
- **문제**: 인용 트윗의 경우 `article` 내에 두 개의 `tweetText` 요소가 존재할 수 있으며, 이 중 인용된 원본의 텍스트를 작성자의 본문으로 오인할 가능성이 있음.
- **설계**:
    - DOM 기반 추출 시, `article` 바로 아래의 직계 자손 또는 특정 깊이 내의 `tweetText`만 선택하도록 함.
    - 인용된 트윗의 컨테이너(보통 테두리가 있는 별도 div) 내부의 `tweetText`는 제외함.

### 2.2. 네트워크 응답 파싱(JSON) 안정화
- **문제**: `note_tweet` 구조가 복잡하여 파싱 실패 시 `legacy.full_text`를 가져오는데, 이때 데이터가 꼬일 가능성 검토.
- **설계**:
    - `extract_from_json` 루프 내에서 변수 초기화를 명확히 하고, `rest_id`와 데이터의 매핑을 이중 확인.
    - 텍스트가 유독 길거나 반복되는 경우 로그를 남겨 이상 징후 포착.

### 2.3. 상세 수집(twitter_scrap_single.py) 필터링 강화
- **문제**: 타래글(스레드) 수집 시 작성자 아이디(`real_user`) 기반 필터링이 첫 번째 항목(`i=0`)에는 적용되지 않아 엉뚱한 텍스트가 섞일 수 있음.
- **설계**:
    - 첫 번째 `article`에 대해서도 작성자 아이디 검증 로직을 적용.
    - 만약 인용 트윗이라면 인용 주체의 아이디와 인용된 대상의 아이디를 구분하여 처리.

### 2.4. 디버그 및 검증 로직 추가
- **설계**:
    - 수집 과정에서 동일한 `full_text`가 서로 다른 `platform_id`에 할당되려고 할 때 경고 로그 출력.
    - `Simple` 파일 저장 전 본문 중복 여부를 체크하여 리포트 출력.

## 3. 상세 수정 계획 (Action Items)
1. **`twitter_scrap.py` 수정**:
    - `extract_from_html`에서 인용 트윗 텍스트 제외 로직 추가.
    - `handle_response`에서 데이터 덤프 옵션 추가 (진단용).
2. **`twitter_scrap_single.py` 수정**:
    - `scrape_full_tweet` 내 작성자 검증 강화.
    - 인용 트윗 본문 처리 방식 개선.

---
작성일: 2026-02-12
작성자: Gemini CLI Agent
