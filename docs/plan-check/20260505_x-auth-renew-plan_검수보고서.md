# X 인증 갱신 개선계획 검수보고서

검수 대상: 2026-05-05 대화 중 작성된 "X 인증 갱신은 `user_data`를 정본으로 하고 `cookies.json`은 파생물로 다룬다" 계획

## 총평

방향은 맞지만, 직전 계획은 그대로 실행하기에는 부족하다. 핵심 결함은 `renew.py x`의 성공 기준을 강화한다고 하면서도, 실제로는 `export_x_artifacts.py`가 `user_data`를 headless Chrome으로 다시 여는 현재 구조의 실패 가능성을 충분히 제거하지 못했다는 점이다.

수정계획은 "쿠키를 더 잘 갱신한다"가 아니라 "`user_data`를 정본으로 갱신하고, 같은 로그인 context 또는 검증된 export 경로에서만 파생물을 만들며, producer 검증은 비파괴 probe로 한다"로 바뀌어야 한다.

## 크리티컬 피드백

### 1. `export_x_artifacts.py`의 headless 재오픈 문제를 먼저 해결해야 한다

현재 `renew.py x`는 로그인 후 `export_x_artifacts()`를 호출한다. 그런데 `export_x_artifacts()`는 `AUTH_HOME/x/user_data`를 다시 `headless=True` persistent context로 연다.

오늘 관찰된 `Browser window not found` 계열 오류는 이 구조에서 재발할 수 있다. 따라서 export는 가능하면 `renew_x_profile()`이 이미 열고 있는 live context에서 바로 수행해야 한다.

개선안:

- `export_x_artifacts_from_context(context, stamp=None)`를 추가한다.
- `renew_x_profile()`과 `renew_x_profile_web()`은 로그인 완료 후 같은 context에서 `storage_state`, `cookies("https://x.com")`, dated cookie, stable link를 만든다.
- 외부에서 이미 Chrome을 직접 열고 닫은 수동 fallback만 별도의 headed export 명령으로 둔다.

### 2. producer 검증을 `twitter_scrap.py --mode update`로 하면 안 된다

직전 계획은 검증 명령에 `python twitter_scrap.py --mode update`를 넣었다. 이 명령은 인증 검증이 아니라 실제 목록 수집이며, `output_twitter/python/*.json`을 변경할 수 있다.

인증 갱신 성공 검증은 비파괴 probe여야 한다.

개선안:

- `scripts/auth_runtime/verify_x_auth.py`를 추가한다.
- producer probe는 `AUTH_HOME/x/user_data`로 `https://x.com/i/bookmarks`에 접근하되 output JSON을 쓰지 않는다.
- 성공 조건은 `Bookmarks?variables=` 응답 수신 또는 `article[data-testid="tweet"]` 확인으로 둔다.
- 실패 조건은 login/signup/auth challenge URL 또는 둘 다 미검출이다.

### 3. `twitter_scrap.py`의 false positive 판정은 별도 수정해야 한다

현재 producer는 북마크 페이지 진입 후 `article[data-testid="tweet"]`가 없으면 인증 필요로 판단한다. 하지만 2026-05-04 23:05 로그에서는 네트워크로 1건을 이미 잡은 뒤에도 `login_required`를 냈다.

개선안:

- `bookmark_response_seen` 또는 `parsed_bookmark_count` 상태를 둔다.
- `article`이 없어도 북마크 응답에서 게시글을 파싱했으면 인증 실패로 처리하지 않는다.
- 이 수정은 `twitter_scrap_single.py`와 무관하며, consumer는 건드리지 않는다.

### 4. consumer 변경은 범위에서 제외해야 한다

`twitter_scrap_single.py`는 2026-04-18에 `twitter-cli` 기반 focal tweet collector로 전환됐고, 현재 사용자가 문제 삼은 대상이 아니다. 개별 글/타래 수집 회귀 위험이 있으므로 이 작업에서는 consumer 로직을 수정하지 않는다.

단, consumer가 읽는 `cookies.json`이 `user_data`에서 파생된 최신 파일인지 검증하는 테스트는 추가한다.

### 5. README 성공 기준이 운영 사고를 유발했다

현재 README는 X 수동 갱신 성공 기준을 `cookies.json` 최신 링크, `auth_token`/`ct0`, `twitter-cli` 상세 조회 중심으로 적고 있다. producer가 쓰는 `user_data`로 북마크 목록 접근이 되는지는 성공 기준에 없다.

개선안:

- README의 X 성공 기준을 `user_data producer probe + cookies export + consumer token check` 3단계로 바꾼다.
- "쿠키만 갱신"을 성공으로 보지 않는다고 명시한다.
- 직접 Chrome으로 수동 로그인한 경우에도 export와 producer probe를 실행해야 완료라고 적는다.

## 개선된 실행계획

### Task 1. X artifact export를 context 기반으로 분리

수정 파일:

- `scripts/auth_runtime/export_x_artifacts.py`
- `tests/unit/test_export_x_artifacts.py`

작업:

1. 쿠키 배열과 storage_state 저장을 받아 dated cookie와 stable link를 갱신하는 pure helper를 만든다.
2. `export_x_artifacts_from_context(context, stamp=None)`를 추가한다.
3. 기존 `export_x_artifacts()`는 fallback으로 유지하되, headless 실패 시 stale link를 남기지 않고 실패한다.

검증:

```powershell
pytest tests/unit/test_export_x_artifacts.py -q
```

### Task 2. `renew.py x`를 같은 context export로 변경

수정 파일:

- `scripts/auth_runtime/renew.py`
- `tests/unit/test_auth_paths.py`
- 필요 시 신규 `tests/unit/test_x_auth_renew_flow.py`

작업:

1. `renew_x_profile()`에서 로그인 완료 후 context를 닫기 전에 export한다.
2. `renew_x_profile_web()`도 `context.storage_state()` 후 별도 headless 재오픈을 하지 않는다.
3. 성공 출력에 `USER_DATA_OK`, `EXPORTED_COOKIE_FILE`, `VALIDATED_COOKIE_TARGET`를 포함한다.

검증:

```powershell
python "$env:USERPROFILE\.config\auth\renew.py" x
```

기대 출력:

```text
USER_DATA_OK
EXPORTED_COOKIE_FILE=cookies_YYYYMMDD_HHmm.json
VALIDATED_COOKIE_TARGET=cookies_YYYYMMDD_HHmm.json
```

### Task 3. 비파괴 X 인증 probe 추가

생성 파일:

- `scripts/auth_runtime/verify_x_auth.py`
- `tests/unit/test_x_auth_probe.py`

작업:

1. producer probe: `AUTH_HOME/x/user_data`로 북마크 페이지 접근, output 파일 쓰기 금지.
2. consumer probe: `AUTH_HOME/x/cookies.json`에서 `auth_token`, `ct0` 존재 확인.
3. JSON 출력: `{"producer_ok": true, "consumer_ok": true}` 형식.

검증:

```powershell
python scripts\auth_runtime\verify_x_auth.py
```

기대 출력:

```json
{"producer_ok":true,"consumer_ok":true}
```

### Task 4. X producer 로그인 판정 false positive 수정

수정 파일:

- `twitter_scrap.py`
- 신규 또는 기존 unit test

작업:

1. `handle_response()`에서 북마크 응답 수신 여부와 파싱 개수를 기록한다.
2. `article`이 없어도 파싱된 북마크가 있으면 인증 실패로 보지 않는다.
3. 로그인 URL 또는 auth challenge가 명확할 때만 `SNS_AUTH_REQUIRED`를 낸다.

검증:

```powershell
pytest tests/unit -q
python twitter_scrap.py --mode update
```

주의: 두 번째 명령은 실제 수집 검증 단계에서만 실행한다. 인증 갱신 검증에는 Task 3 probe를 사용한다.

### Task 5. README와 운영 문구 수정

수정 파일:

- `README.md`
- 필요 시 `docs/crawling_logic.md`
- `CHANGELOG.md`

작업:

1. X 인증 정본: `AUTH_HOME/x/user_data`.
2. X 파생물: `AUTH_HOME/x/cookies.json`, `AUTH_HOME/x/storage_state.json`.
3. 갱신 완료 기준: producer probe, cookie export, consumer token check 모두 통과.
4. consumer 상세 수집 로직은 이번 범위에서 수정하지 않는다고 명시.

검증:

```powershell
rg -n "user_data|cookies.json|producer probe|consumer" README.md docs/crawling_logic.md
```

## 영구화 surface와 마이그레이션 판단

영향 surface:

- `C:\Users\ahnbu\.config\auth\x\user_data\`
- `C:\Users\ahnbu\.config\auth\x\cookies_YYYYMMDD_HHmm.json`
- `C:\Users\ahnbu\.config\auth\x\cookies.json`
- `C:\Users\ahnbu\.config\auth\x\storage_state.json`
- `C:\Users\ahnbu\.config\auth\x_cookies_current.json`
- `C:\Users\ahnbu\.config\auth\x_storage_state_current.json`

기존 게시글 데이터 마이그레이션:

- 불필요.

근거:

- `output_twitter/python/*.json`, `output_total/*.json` 스키마를 바꾸지 않는다.
- 인증 갱신과 검증 흐름만 수정한다.

마이그레이션/검증 명령:

```powershell
python "$env:USERPROFILE\.config\auth\renew.py" x
python scripts\auth_runtime\verify_x_auth.py
```

기대 출력:

```text
USER_DATA_OK
VALIDATED_COOKIE_TARGET=cookies_YYYYMMDD_HHmm.json
{"producer_ok":true,"consumer_ok":true}
```

## 최종 판정

직전 계획은 방향은 맞지만, `export_x_artifacts()`의 headless 재오픈 문제와 비파괴 producer probe 누락 때문에 그대로 실행하면 같은 문제가 반복될 수 있다.

개선된 계획은 `user_data` 정본 원칙을 코드로 강제하고, producer와 consumer 검증을 분리하되 같은 인증 상태에서 나온 결과만 성공으로 인정하도록 바꾼다.
