---
title: "Detailed Design: X(Twitter) Producer Refinement & Precise Extraction"
created: "2026-02-12 14:06"
---

# Detailed Design: X(Twitter) Producer Refinement & Precise Extraction

이 문서는 `docs/twitter_saved` 샘플 데이터를 분석한 결과를 바탕으로 X 목록 수집기(`twitter_scrap.py`)를 고도화하기 위한 상세 설계 내용을 담고 있습니다.

## 1. 정밀 JSON 추출 경로 (사용자 정보 누락 방지)
X의 GraphQL 응답 구조에서 사용자 정보를 가져오기 위해 다음 계층을 순차적으로 탐색합니다.

- **Base Path**: `tweet_results -> result -> core -> user_results -> result`
- **Primary Info (Modern)**: `result.core.screen_name`, `result.core.name`
- **Secondary Info (Legacy)**: `result.legacy.screen_name`, `result.legacy.name`
- **ID Safety**: `user`를 찾지 못한 경우에만 `i/status/{rest_id}` 형식을 사용하고, `user` 필드에는 빈 문자열 대신 `"Unknown"`을 할당하여 이후 상세 수집기에서 교정하도록 유도.

## 2. Threads 스타일 상세 로그 인터페이스
가시성 확보를 위해 `threads_scrap.py`의 로그 패턴을 도입합니다.

### 2.1 콘솔 출력 예시
```text
🚀 X(Twitter) 목록 수집기 시작 (Mode: update)
📡 기존 데이터 34개 로드됨. (중단점: [ID1, ID2...])

🔍 [1단계] 초기 화면(DOM) 스캔 중...
   + [DOM] @godofprompt | OpenClaw hit 145K... (1/34)
   + [DOM] @aiwithmayank | Anthropic engineers... (2/34)

📜 [2단계] 스크롤 및 네트워크 패킷 캡처 시작
⬇️ 스크롤 1회차...
   + [Net] @GMB_Coinangel | 코인추천요정... (3/34)
   + [Net] @Hartdrawss | Anthropic release... (4/34)
   ✅ 신규 데이터 2개 추가됨! (누적 36개)

🏁 목록 수집 완료! 총 36개 항목이 확보되었습니다.
📂 저장 경로: output_twitter/python/twitter_py_simple_full_20260212.json
```

## 3. 데이터 무결성 보장 로직
- **중복 방지**: `all_posts_map`의 키를 `rest_id` (고유 숫자 ID)로 고정.
- **상태 관리**: 수집된 모든 신규 항목은 `is_detail_collected: false`를 기본값으로 가짐.
- **본문 정제**: `full_text` 필드명을 엄격히 준수하고 `body` 필드 발생 시 즉시 제거.

## 4. 구현 단계 (Do)
1. `extract_from_json` 함수의 경로 탐색 로직 보강.
2. `extract_from_html` 함수의 로그 출력 기능 추가.
3. `main` 루프 내 실시간 진행 상황 출력 로직 구현.
