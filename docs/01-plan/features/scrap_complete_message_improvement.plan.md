# [Plan] 스크랩 완료 메시지 고도화 및 데이터 통계 제공

## 1. 개요
현재 웹사이트에서 스크랩 완료 후 표시되는 메시지가 단순하여, 어떤 데이터가 얼마나 추가되었는지 사용자가 즉각적으로 파악하기 어렵습니다. 이를 개선하기 위해 플랫폼별 신규 추가 건수를 포함한 상세 메시지를 출력하도록 변경합니다.

## 2. 조사 결과
- **현재 메시지 위치**: `web_viewer/script.js` (L163) - `alert(`${modeLabel}이 완료되었습니다! 데이터를 새로고침합니다.`);`
- **데이터 출처**: `total_scrap.py`에서 병합 및 저장 시 신규 항목을 계산하지만, 현재는 전체 건수 위주로 메타데이터가 구성되어 있습니다.
- **통신 흐름**: `script.js` (UI) -> `server.py` (API) -> `total_scrap.py` (Script)

## 3. 해결 방안
### 3.1. 백엔드 로직 개선 (`total_scrap.py`)
- `save_total()` 함수에서 신규 추가된 항목(`new_items`)을 플랫폼별(`threads`, `linkedin`)로 분류하여 카운트하도록 수정.
- 저장되는 JSON의 `metadata`에 `new_threads_count`, `new_linkedin_count` 필드 추가.

### 3.2. API 응답 개선 (`server.py`)
- `run_scrap` 엔드포인트에서 스크립트 실행 완료 후, 생성된 최신 JSON 파일을 읽어 `metadata` 정보를 추출.
- API 응답 객체에 `new_counts` 정보를 포함하여 반환.

### 3.3. 프론트엔드 UI 수정 (`web_viewer/script.js`)
- API 응답에서 받은 통계 데이터를 바탕으로 사용자 요청 메시지 구성.
- 변경된 형식: `"총 {total}건이 추가되었습니다. 데이터를 새로고침합니다.
쓰레드 - {threads}건 추가
링크드인 - {linkedin}건 추가"`

## 4. 상세 계획
1. [ ] `total_scrap.py`: `save_total` 함수 수정 (플랫폼별 신규 건수 계산 및 저장).
2. [ ] `server.py`: `run_scrap` 함수 수정 (최신 메타데이터 읽기 및 JSON 반환).
3. [ ] `web_viewer/script.js`: 알림 메시지 로직 수정.
4. [ ] 테스트 스크랩을 실행하여 메시지 정상 출력 확인.

## 5. 기대 효과
- 스크랩 결과에 대한 가시성 확보.
- 시스템의 동작 상태를 더 명확하게 사용자에게 전달.
