# V6 뷰어 화면 검증 — X 커서 페이지네이션 전환

- 시각: 2026-08-26 11:0x (KST)
- 대상: http://localhost:5000/ (`wscript sns_hub.vbs` 로 재시작 후)
- 방식: 실제 화면을 브라우저로 열어 사용자 순서대로 클릭하고 상단 건수·카드 배지를 읽음

## 측정값

| 화면 상태 | 상단 건수 | 판정 |
|---|---|---|
| 초기(All) | `2109 / 2112 건` | 통합본 2,112건과 일치 (숨김 3건) |
| X 플랫폼 필터 | `95 / 2112 건` | X 저장분 95건과 일치 |
| X + 지표 보유만 | `94 / 2112 건` | V1(지표 보유 94건)과 일치 |

전환 전 같은 조합은 `20 / ...` 이었다.

## 카드 배지 표시 확인 (X 필터 상단 카드)

```
X  Yero        조회수 14.4만  favorite 2.1천  chat_bubble 28  repeat 519  format_quote 2  bookmark 3.5천
X  Movez       조회수 92.6만  favorite 3천    chat_bubble 74  repeat 521  format_quote 18 bookmark 7.4천
X  Codez       조회수 632.5만 favorite 2.5천  chat_bubble 64  repeat 401  format_quote 106 bookmark 8.1천
```

## 캡처 미첨부 사유

이 세션은 비대화형이라 브라우저 페인이 화면에 표시되지 않아 스크린샷 API 가 프레임을 합성하지 못한다
(`Screenshot timed out: the Browser pane is not displayed`). 대신 실제 페이지의 렌더링된 DOM 텍스트를
그대로 읽어 위 수치와 배지를 기록했다. API 응답이 아니라 화면에 그려진 결과다.
