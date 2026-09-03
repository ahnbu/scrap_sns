# 결론

이 plan은 **목적 달성 가능성이 낮다.**

조회 전용 CLI까지는 비교적 빨리 만들 수 있지만, plan이 함께 약속하는 `태그 추가/삭제`와 `분석 리포트`는 현재 설계대로면 정확성과 일관성을 보장하지 못한다. 특히 **태그 key 정규화 부재**, **브라우저와 CLI의 동시 수정 충돌**, **리포트용 `--limit 100` 샘플링 편향**이 크리티컬하다.

---

## 확인한 근거

- plan 원문: `C:\Users\ahnbu\.claude\plans\atomic-soaring-thacker.md`
- 실제 태그 저장/조회: `server.py:19-45`
- 실제 태그 소비/URL 정규화: `web_viewer/script.js:395-443`, `web_viewer/script.js:567-583`, `web_viewer/script.js:1216-1243`
- 현재 데이터/태그 실측:
  - `output_total/total_full_20260412.json` posts `982`
  - `web_viewer/sns_tags.json` keys `912`
  - 현재 tags 중 canonical URL 일치 `659`, `https://www.threads.net/t/<code>` legacy key `9`, `code-only` key `0`
- 검증 실행:
  - `pytest tests/unit/test_web_viewer_auto_tagging.py tests/unit/test_web_viewer_resolve_post_url.py -q` → `4 passed`
  - JSON 로드 실측(20회 평균): 약 `0.03s`

---

## 크리티컬 이슈

### 1. `tag add/remove/list [url]`가 raw URL 기준이라 현재 viewer key 체계와 충돌한다

plan은 `tag list [url]`, `tag add <url>`, `tag remove <url>`만 정의하고 URL canonicalization을 전혀 정의하지 않는다 (`plan:62-64`).

그런데 실제 viewer는 태그를 `resolvePostUrl(post)` 기준 key로 읽는다 (`web_viewer/script.js:567-583`). Threads의 canonical key는 `https://www.threads.net/@user/post/<code>`이고, plan의 테스트 예시는 오히려 legacy short URL인 `https://www.threads.net/t/DT8EUxBic2M`를 그대로 사용한다 (`plan:88-89`).

현재 `web_viewer/sns_tags.json`에도 `/t/<code>` key가 9개 남아 있는데, 이 9개는 현재 `output_total/total_full_20260412.json`의 어떤 post `url`과도 일치하지 않는다. 즉 **plan 예시대로 태그를 추가하면 viewer에 안 보이는 태그를 더 쌓을 가능성이 높다.**

이건 문서 표현 문제가 아니라 핵심 기능 실패다. 태그 CRUD를 하려면 최소한:

- 입력으로 받은 URL을 canonical post record로 역해결하거나
- `platform_id` 기반으로 먼저 post를 찾고
- 저장 key는 항상 canonical `post.url`로 강제해야 한다.

현 plan에는 그 계약이 없다.

### 2. CLI와 브라우저가 같은 `sns_tags.json`을 마지막 작성자 기준으로 덮어쓴다

plan은 태그 CRUD를 CLI에서 직접 수행하겠다고 하지만 (`plan:63-64`), 동시성 모델이 없다. `server.py`는 `web_viewer/sns_tags.json`을 그대로 읽고/쓴다 (`server.py:19-45`). 브라우저는 로드 시 server tags를 localStorage로 병합한 뒤 (`web_viewer/script.js:467-480`), 관리 모달을 열면 localStorage 전체를 다시 서버에 POST한다 (`web_viewer/script.js:1216-1243`).

즉 사용자가 viewer를 켜둔 상태에서 CLI가 `sns_tags.json`을 수정하면, **브라우저의 stale localStorage가 나중에 서버 파일을 다시 덮어써 CLI 변경을 날릴 수 있다.** plan의 "동기화는 별도 안내" (`plan:107`)는 이 문제를 피하지 못한다.

태그 수정까지 목적에 포함한다면 최소한:

- viewer 종료 전제,
- 파일 lock/mtime check,
- 또는 서버 API를 통한 단일 write path

중 하나가 필요하다. 지금 plan은 read path와 write path를 둘 다 만들지만, 정합성 책임은 비워 둔다.

### 3. 분석 리포트에서 `search(--limit 100)`은 작은 편의 대신 결과 왜곡을 만든다

plan은 분석 리포트 workflow를 `search(--limit 100) → 범위 확인 → AI 분석`으로 고정한다 (`plan:106`, `plan:119`). 이건 전형적인 과최적화다.

실데이터 기준으로 `"클로드"` 매치는 이미 `429`건이다. 이 상태에서 상위 `100`건만 분석하면 전체 경향이 아니라 **임의의 23% 샘플**을 분석하는 셈이다. 사용자는 "클로드 관련 SNS 분석 리포트"를 요청했는데, plan은 조용히 "최근/일부 샘플 분석"으로 바꿔버린다.

토큰 절약은 얻지만, 분석 목적의 정확성을 잃는다. 이건 작은 비용 최적화가 더 큰 품질 손실을 만든 사례다.

---

## 중요한 설계 결함

### 4. 출력 스키마가 실제 데이터와 완전히 맞물리지 않는다

plan의 `postToResult`는 `media_count`를 반환 필드로 적었지만 (`plan:48`), 현재 실제 데이터에는 `media_count` 필드가 없고 `media` 배열이 있다. 실데이터 샘플 키 확인 결과 공통적으로 `media`는 있으나 `media_count`는 없다.

물론 구현에서 `media.length`를 계산하면 해결 가능하다. 다만 plan이 현재 schema를 정확히 읽고 있지 않다는 신호다. 태그 key처럼 이미 민감한 부분이 있는 상황에서 이런 작은 schema drift도 무시하면 안 된다.

### 5. 자동 검증이 수동 커맨드 나열 수준에 머문다

plan의 테스트는 전부 수동 CLI 예시다 (`plan:78-92`). 통합 검증도 `"태그 CRUD 후 웹 뷰어에서 반영 확인"` 수준이다 (`plan:118-120`).

하지만 이 기능의 리스크는 대부분 write-path에 있다. 최소한 아래 테스트가 plan에 있어야 한다.

- canonical URL 저장 테스트
- `/t/<code>` 입력을 canonical URL로 승격하는 테스트
- 존재하지 않는/stale tag key 처리 테스트
- temp tags 파일 대상 read-modify-write 회귀 테스트

현재 plan은 "동작해 보이는가"만 보지 "데이터를 망가뜨리지 않는가"를 검증하지 않는다.

---

## 트레이드오프

### 얻는 것

- SQLite 없이도 빠르게 붙일 수 있다. 실제 JSON 로드는 평균 약 `0.03s`라서 현재 규모에서는 충분히 가볍다.
- `query-sns.mjs` + skill 조합은 Claude/Codex에서 재사용하기 쉬운 인터페이스다.
- 조회 전용 기능(`recent`, `search`, `by-platform`, `stats`)은 구현 대비 효용이 크다.

### 잃는 것

- Node CLI를 새로 만들면 Python 중심 코드베이스(`server.py`, `build_data_js.py`, `post_schema.py`)와 URL/tag 규칙이 분리된다.
- viewer가 이미 갖고 있는 canonicalization/migration 규칙을 복제하게 되어 drift 위험이 커진다.
- 태그 write path를 CLI로 추가하는 순간, 단순 조회 도구가 아니라 데이터 정합성 책임을 지는 도구가 된다.

요약하면, **조회 전용이면 단순함을 얻지만, 태그 수정까지 넣는 순간 지금 구조의 약점이 바로 드러난다.**

---

## 과최적화 포인트

### 1. `search --limit 100`으로 분석 리포트를 고정한 것

토큰/응답속도를 줄이려다 분석 정확성을 희생했다. 이건 현재 데이터에서 이미 실제 왜곡으로 이어진다.

### 2. SQLite를 피한 것은 과최적화가 아니다

이 부분은 오히려 맞다. 현재 데이터 크기와 로드 시간 기준으로 JSON 유지 판단은 타당하다.

### 3. 쓰기 안전장치 없이 태그 CRUD를 먼저 넣는 것이 과최적화다

"AI가 태그도 바로 붙이게 하자"는 편의 최적화가, 실제로는 태그 key 분열과 last-writer-wins 문제를 만든다. 작은 UX 개선 욕심이 데이터 정합성 문제로 번지는 패턴이다.

---

## 권장 수정 방향

### 권장안

plan을 두 단계로 쪼개는 편이 안전하다.

1. **Phase A: 조회 전용 CLI + skill**
   - `recent`, `get`, `search`, `by-platform`, `by-user`, `stats`
   - 분석 리포트는 기본 전체 집합 또는 page-by-page
2. **Phase B: 태그 수정**
   - canonical key contract 먼저 문서화
   - 입력 URL/ID 정규화 로직 추가
   - browser/CLI 동시성 규칙 정의
   - write-path 테스트 추가

### 최소 보완 없이는 진행하면 안 되는 항목

- `tag add/remove/list`에 canonicalization 규칙 명시
- `search --limit 100` 기본값 제거 또는 "샘플 분석"으로 명시
- 브라우저 open 상태에서의 write conflict 처리 방안 명시

---

## 검증 불가

- 구현 전이므로 `sns-query` skill이 실제 Claude runtime에서 원하는 트리거 정확도로 자동 발동할지는 검증 불가
- 사용자의 실제 운영 흐름에서 viewer와 CLI를 얼마나 동시에 열어 두는지는 검증 불가
- 현재 `web_viewer/sns_tags.json`의 `/t/<code>` 9건이 단순 stale data인지, 향후 다시 수집될 post의 legacy key인지 완전 확정은 검증 불가
