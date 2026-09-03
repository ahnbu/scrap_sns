# elegant-beaming-scott plan 검수보고서

판정: 목적 달성은 가능하지만, 현재 plan 그대로는 중복 스크랩 실행 방지 누락 때문에 안전한 구현 계획이라고 보기 어렵다.

검수 대상: `C:\Users\ahnbu\.claude\plans\elegant-beaming-scott.md`  
대상 레포: `D:\vibe-coding\scrap_sns`  
검수일: 2026-04-23 KST

## 결론

이 plan의 큰 방향은 타당하다. `refreshBtn` 제거, 업데이트 1단 버튼화, 전체 크롤링을 Settings 안으로 낮추는 정보 구조는 사용 빈도와 위험도에 맞다.

다만 `runFullScrapBtn`을 새로 만들면서 실행 버튼이 2개가 되는데, plan은 전역 실행 잠금이나 양쪽 버튼 동시 비활성화를 명시하지 않는다. 현재 서버도 `/api/run-scrap` 요청을 별도 lock 없이 `subprocess.Popen()`으로 실행하므로, UI에서 다른 버튼을 누르면 중복 스크랩이 발생할 수 있다.

## 크리티컬 결함

1. 중복 스크랩 실행 방지 설계가 빠져 있다.

현재 구현은 스크랩 실행 중 `runScrapBtn` 하나만 비활성화한다. plan의 `executeScrap(mode, triggerBtn)` 설계도 "Running 상태 UI를 입힐 버튼"만 받도록 되어 있어, Settings의 전체 재크롤링 버튼을 눌렀을 때 헤더 업데이트 버튼은 계속 활성 상태로 남을 가능성이 높다.

근거:
- `web_viewer/script.js:563`에서 원래 콘텐츠를 `runScrapBtn` 기준으로 저장한다.
- `web_viewer/script.js:564-568`에서 `runScrapBtn`만 disabled/Running 처리한다.
- `web_viewer/script.js:626-628`에서 `runScrapBtn`만 복구한다.
- `server.py:383-396`은 `/api/run-scrap` 요청마다 `total_scrap.py`를 실행하고 `wait()`한다. 스크랩 실행 전역 lock은 확인되지 않았다.

권장 수정:
- `let scrapRunInProgress = false` 같은 전역 UI lock을 두고, `executeScrap()` 시작 시 guard한다.
- 실행 중에는 `runScrapBtn`과 `runFullScrapBtn`을 모두 disable한다.
- 필요하면 서버에도 scrap lock을 추가한다. UI lock만으로는 브라우저 중복 탭이나 직접 API 호출을 막지 못한다.

2. `runFullScrapBtn` 이벤트 바인딩 위치가 모호하다.

plan은 바인딩을 "`openManagementModal` 근처 또는 DOMContentLoaded 시점"이라고 적는다. 실제로 `openManagementModal()` 내부에 넣으면 Settings를 열 때마다 listener가 누적되어 클릭 1회에 여러 번 실행될 수 있다.

근거:
- `web_viewer/script.js:1953-1968`의 `openManagementModal()`은 모달을 열 때마다 실행된다.
- `web_viewer/script.js:2272`에서 Settings 버튼 클릭 시 `openManagementModal`이 호출된다.

권장 수정:
- `runFullScrapBtn` listener는 DOMContentLoaded 스코프에서 1회만 등록한다.
- `openManagementModal()` 내부에는 렌더링·탭 초기화만 둔다.

## 중요한 부정확성

1. `runScrapBtn` 초기 disabled 제거 항목은 현재 코드와 맞지 않는다.

plan은 `opacity-50 cursor-not-allowed`, `disabled=""` 제거가 필요하다고 쓰지만, 현재 `index.html:272-284`의 `runScrapBtn`에는 해당 class나 disabled 속성이 없다. 이 항목은 불필요한 작업이다.

2. plan의 라인번호는 대체로 맞지만 일부 설명이 부정확하다.

정확한 항목:
- `index.html:272-284` `runScrapBtn`
- `index.html:285-313` `scrapDropdown`
- `index.html:316-325` `refreshBtn`
- `index.html:463-482` Settings 탭 네비게이션
- `web_viewer/script.js:20` `refreshBtn`
- `web_viewer/script.js:151` refresh 바인딩
- `web_viewer/script.js:513-632` scraper UI 블록
- `web_viewer/script.js:1979-1998` `switchTab()`
- `server.py:362-373` 허용 모드 검증

부정확한 항목:
- plan은 `script.js:617`의 `fetchData()`를 스크랩 완료 후 자동 호출 근거로 든다. 현재는 맞다.
- 그러나 `tests/contract`가 `/api/run-scrap` 계약 테스트라는 설명은 틀렸다. `tests/contract/test_schemas.py`는 통합 JSON 스키마 검증이다.
- `tests/e2e/test_api_security.py:48-59`는 valid mode를 `update`만 확인한다. `all` 모드 UI/API 회귀를 직접 보장하지 않는다.

## 트레이드오프

얻는 것:
- 헤더 액션 수가 줄어 시각 노이즈가 감소한다.
- 매일 쓰는 업데이트가 클릭 1회 동작이 되어 사용성이 좋아진다.
- 전체 재크롤링을 Settings 안으로 이동해 위험한 작업의 노출을 낮춘다.

잃는 것:
- 수동 새로고침 버튼이 사라져, 스크랩 없이 데이터만 다시 불러오는 명시적 경로가 없어진다. 브라우저 F5가 대체 수단이지만 앱 내부 액션은 아니다.
- 전체 재크롤링 접근성이 낮아진다. 의도한 변화이지만, 실제로 자주 쓰는 사용자가 있으면 발견성이 떨어진다.
- 버튼이 2개로 분리되면서 실행 상태 관리 복잡도가 증가한다.

## 과최적화 여부

큰 과최적화는 아니다. 사용 빈도에 맞춰 UI 위계를 재배치하는 변경이므로 목적은 분명하다.

다만 작은 헤더 정리 작업이 실행 상태 관리 문제를 새로 만들 수 있다. `executeScrap(triggerBtn)`로 버튼별 UI 상태만 일반화하면 겉보기에는 깔끔하지만, 실제로 필요한 것은 버튼 추상화보다 "스크랩 작업은 동시에 1개만 실행"이라는 상태 모델이다.

## 검증 계획 평가

현재 검증 계획은 부족하다.

문제:
- Playwright 자동 검증이 선택 사항으로 되어 있다. UI 재배치 작업이므로 최소 DOM 확인과 confirm dialog 확인은 필수로 올리는 편이 맞다.
- `tests/contract`는 `/api/run-scrap`을 검증하지 않는다.
- `mode=all`에 대한 회귀 테스트가 명시되어 있지만 실제 기존 테스트에는 없다.

권장 검증:
- `pytest tests/e2e/test_api_security.py`
- `pytest tests/integration/test_run_scrap_stats.py`
- `node utils/query-sns.mjs --help`
- headless Playwright로 `refreshBtn` 부재, `scrapDropdown` 부재, `runScrapBtn` 클릭 시 confirm, Settings 유지보수 탭과 `runFullScrapBtn` 존재를 확인한다.
- 가능하면 mock 기반으로 `mode=all` 요청이 `/api/run-scrap`에 전달되는 UI 테스트를 추가한다.

## 검증 불가

- 실제 브라우저 렌더링에서 헤더 버튼 폭, 모바일 줄바꿈, Settings 탭 overflow가 안정적인지는 코드 정적 검토만으로 검증 불가.
- 실제 스크랩 실행 시간, 인증 만료 플랫폼에서 `authRequiredPanel`이 정상 노출되는지는 현재 검토만으로 검증 불가.
- 사용자가 `refreshBtn`을 실제로 거의 쓰지 않는다는 사용성 전제는 검증 불가.

## 최종 권고

이 plan은 "방향은 승인, 그대로 실행은 보류"가 맞다. 실행 전 최소한 다음 2가지를 plan에 반영해야 한다.

1. `executeScrap()`에 전역 실행 잠금과 양쪽 버튼 비활성화를 명시한다.
2. `runFullScrapBtn` 이벤트 바인딩은 DOMContentLoaded에서 1회만 등록한다고 명시한다.

이 두 항목을 보완하면 목적 달성 가능성은 높다.
