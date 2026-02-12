# PDCA 설계: Threads 스크래퍼 진단 및 구조 최적화

## 1. 개요 (Overview)
`thread_scrap.py`의 네트워크 데이터 추출 로직을 투명하게 하고, 변경된 Threads API 구조에 대응할 수 있도록 설계를 개선합니다.

## 2. 진단 도구 설계 (Diagnosis Tools)
### 2.1. 상세 로깅 추가
- `handle_response` 내부의 `except: pass`를 제거하고 구체적인 에러 내용을 출력하도록 변경.
- 처리 중인 응답의 URL과 상위 키 구조를 출력하여 어떤 데이터가 들어오는지 확인.

### 2.2. 응답 덤프 기능 (Debug Dump)
- `DEBUG_SAVE = True` 설정 시 수신되는 모든 GraphQL 응답을 `docs/thread_saved_html/debug_response_{ts}.json`으로 저장.
- 이를 통해 수동으로 JSON 구조를 분석할 수 있게 함.

## 3. 로직 개선 설계 (Logic Improvements)
### 3.1. 추출 경로 확장
- 기존: `xdt_text_app_viewer` 또는 `text_post_app_user_saved_posts`
- 추가 검토: `xdt_text_app_viewer_saved_media` 등 다른 명칭이 쓰이는지 확인하고 대응.

### 3.2. 필터링 완화 및 로깅
- `process_network_post`에서 왜 게시물이 스킵되는지 이유를 출력 (예: "작성자 불일치", "텍스트/이미지 없음").
- `stop_codes`에 의해 중단되는 경우 해당 코드를 명확히 출력.

### 3.3. DOM 스캔 로직 보강
- 셀렉터가 변경되었을 가능성에 대비하여 `div[role="article"]` 또는 다른 공통 속성을 탐색하도록 유연성 확보.

## 4. 데이터 병합 로직 검증
- `update_simple_version`에서 중복 제거 및 `sequence_id` 부여 로직이 올바르게 작동하는지 확인.
- `max_sequence_id`가 작게 나오는 이유가 실제 데이터가 없어서인지, 병합 과정의 오류인지 확인.

## 5. 수행 계획 (Implementation Plan)
1. `thread_scrap.py`에 디버그 로그 및 응답 저장 로직 추가.
2. 스크립트 실행 및 로그 확인.
3. 수집된 JSON 분석 후 `handle_response` 수정.
4. 최종 테스트 및 디버그 코드 제거.

---
작성일: 2026-02-12
작성자: Gemini CLI Agent
