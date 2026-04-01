---
title: "PDCA 계획: Twitter 수집 데이터 중분 발생 원인 분석 및 해결"
created: "2026-02-12 00:00"
---

# PDCA 계획: Twitter 수집 데이터 중분 발생 원인 분석 및 해결

## 1. 개요 (Overview)
- **대상**: `twitter_scrap.py`, `twitter_scrap_single.py`
- **문제**: `total_full_20260212.json` 및 `twitter_py_simple_20260212.json` 파일에서 13개의 게시물이 동일한 `full_text`를 가지고 있음. URL과 미디어 정보는 서로 다르지만, 본문 내용만 특정 AI 관련 텍스트로 중복되어 있음.
- **목표**: 중복 발생의 기술적 원인을 파악하고, 수집 로직을 개선하여 데이터 정합성을 확보함.

## 2. 현재 상황 및 가설 (Current Status & Hypotheses)
### 2.1. 현상 분석
- 중복된 텍스트: "이게 현실임 
미국은 거의 모든집이 수입이 들어오지않으면 3개월 버티기 힘듬..."
- 중복 횟수: 13회 (서로 다른 11개 이상의 계정)
- 특이사항: `source` 필드가 `"full_tweet_scan"`인 것으로 보아 `twitter_scrap_single.py`에 의해 업데이트된 기록이 있음. 그러나 사용자는 `twitter_scrap.py`(Producer) 단계의 `simple` 버전부터 이미 문제가 있다고 지적함.

### 2.2. 원인 가설
- **가설 1: DOM 선택자 오작동 (DOM Selection Error)**
    - `twitter_scrap.py`의 `extract_from_html` 또는 `twitter_scrap_single.py`의 `scrape_full_tweet`에서 `article` 내의 본문을 찾을 때, 현재 요소가 아닌 엉뚱한(예: 광고, 사이드바, 혹은 이전 루프의 잔상) `tweetText` 요소를 가져오고 있을 가능성.
- **가설 2: 인용 트윗(Quote Tweet) 오인식**
    - 수집 대상이 본문 없이 인용만 한 트윗인 경우, 작성자의 본문(비어있음) 대신 인용된 원본 트윗의 본문을 잘못 수집하고 있을 가능성.
- **가설 3: 네트워크 응답 파싱 및 상태 유지 오류**
    - `handle_response`에서 JSON 데이터를 처리할 때, 특정 루프에서 실패하거나 잘못된 매핑으로 인해 이전 성공 데이터가 현재 ID에 할당되는 로직상의 허점.

## 3. 해결 방향 (Proposed Actions)
- **정밀 분석**: 중복된 13개 항목의 원본 데이터(JSON 응답)를 덤프하여 실제 API가 어떤 데이터를 주는지 확인.
- **로직 수정**: 
    - `extract_from_html`에서 본문 추출 시 `article` 범위 내에서 가장 적절한 본문 요소만 선택하도록 강화.
    - 인용 트윗 여부를 판별하여 작성자 본문과 인용 본문을 구분.
    - `twitter_scrap_single.py`에서 `real_user` 필터링 로직을 더욱 엄격하게 적용.
- **검증**: 수정 후 재수집을 통해 동일한 `full_text`가 서로 다른 ID에 할당되지 않는지 확인.

## 4. 수행 단계 (Milestones)
1. **[Plan]**: 문제 원인 분석 및 계획 수립 (현재)
2. **[Design]**: 
    - 중복 방지를 위한 본문 추출 알고리즘 개선 설계.
    - 디버깅용 로그 및 데이터 덤프 로직 설계.
3. **[Do]**: 
    - `twitter_scrap.py` 및 `twitter_scrap_single.py` 코드 수정.
    - 수집 테스트 진행.
4. **[Check]**: 
    - 수집 결과의 본문 중복 여부 전수 검사.
    - Gap Analysis 수행.
5. **[Act]**: 최종 리포트 작성 및 코드 반영.

---
작성일: 2026-02-12
작성자: Gemini CLI Agent
