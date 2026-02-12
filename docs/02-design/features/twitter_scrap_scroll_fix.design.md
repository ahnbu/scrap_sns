# PDCA 설계: Twitter 수집기 스크롤 로직 최적화

## 1. 개요 (Overview)
네트워크 응답 수집과 DOM 스캔 수집이 동시에 이루어지는 환경에서, 새로운 데이터 발견 여부를 통합적으로 판단하여 스크롤 중단을 방지합니다.

## 2. 설계 변경 사항 (Design Changes)

### 2.1. 신규 데이터 감지 방식 개선
- **기존**: `extract_from_html`(DOM)에서 발견된 개수만으로 `consecutive_no_new` 판단.
- **변경**: 루프 시작 시점의 `len(all_posts_map)`과 종료 시점의 개수를 비교하여, 소스에 상관없이 하나라도 추가되었다면 카운터를 초기화함.

### 2.2. 스크롤 및 대기 제어
- 스크롤 직후 네트워크 응답이 도착할 시간을 충분히 주기 위해 `time.sleep` 위치와 시간을 조정.
- Twitter의 동적 로딩 특성을 고려하여, 스크롤 후 즉시 DOM을 체크하기보다 약간의 간격을 둠.

### 2.3. 로그 출력 개선
- 어떤 경로(Network vs DOM)로 데이터가 추가되었는지 명확히 알 수 있도록 로그 메시지 정돈.
- 중복 발견 시 무시하되, 전체 수집 개수는 정확히 출력.

## 3. 구현 세부 사항 (Implementation Details)
- `while True` 루프 내부에 `before_count = len(all_posts_map)` 추가.
- 루프 끝에서 `if len(all_posts_map) > before_count: consecutive_no_new = 0` 적용.
- `update` 모드에서 `stop_ids` 도달 시점을 더 명확히 기록.

---
작성일: 2026-02-12
작성자: Gemini CLI Agent
