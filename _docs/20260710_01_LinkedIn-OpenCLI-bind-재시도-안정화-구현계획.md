---
title: LinkedIn OpenCLI bind 재시도 안정화 구현계획
created: 2026-07-10 14:00
tags:
  - scrap_sns/linkedin
  - opencli
  - implementation-plan
session_id: codex:019f4a4f-567c-7ad3-b847-39f08ce8467e
session_path: C:/Users/ahnbu/.codex/sessions/2026/07/10/rollout-2026-07-10T13-35-46-019f4a4f-567c-7ad3-b847-39f08ce8467e.jsonl
updated_sessions:
  - codex:019f4a4f-567c-7ad3-b847-39f08ce8467e


ai: codex
---

# LinkedIn OpenCLI bind 재시도 안정화 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `omo:start-work` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LinkedIn 수집이 기존 로그인 Chrome 프로필과 OpenCLI를 그대로 쓰면서, bind 재시도마다 LinkedIn 전용창을 다시 활성화해 GitHub/로컬 탭에 잘못 붙는 실패를 줄인다.

**Architecture:** 수집 엔진, 로그인 방식, OpenCLI raw -> parse -> merge 파이프라인은 바꾸지 않는다. `linkedin_scrap.py`의 bind 절차만 `owned_hwnd` aware로 바꿔 각 bind 시도 직전에 전용 LinkedIn 창을 다시 focus하고, URL 불일치 bind는 즉시 `unbind` 후 재시도한다. 성공적으로 LinkedIn 저장글 URL에 bind된 뒤에만 기존 cleanup의 `unbind + close` 경로를 탄다.

**Tech Stack:** Python 3.13, OpenCLI 1.8.6, 기존 로그인 Chrome 프로필, pytest, `node --check`.

---

## 문제 요약

2026-07-10 13:31 KST 실행 로그 기준 LinkedIn 수집은 collector 단계까지 가지 못했다.

```markdown
OpenCLI browser bind URL 불일치: http://127.0.0.1:51981/
OpenCLI browser bind URL 불일치: https://github.com/
OpenCLI browser bind URL 불일치: https://github.com/
RuntimeError: OpenCLI browser bind attached to unexpected URL: https://github.com/
```

현재도 LinkedIn 전용 Chrome 창은 띄운다. 문제는 OpenCLI `browser bind`가 특정 HWND를 직접 지정하지 않고, bind 순간의 활성 Chrome 탭/창에 붙는다는 점이다. 현재 구현은 LinkedIn 창 focus를 bind 전에 한 번만 시도하고, 2번째/3번째 bind 재시도 직전에는 다시 focus하지 않는다.

## 현재 vs 개선

| 항목 | 현재 방식 | 개선 방식 |
|---|---|---|
| 기존 로그인 Chrome 프로필 | ✅ 그대로 사용 | ✅ 그대로 사용 |
| OpenCLI 수집 파이프라인 | ✅ 유지 | ✅ 유지 |
| LinkedIn 전용 창 생성 | ✅ `open_owned_chrome_window()` 사용 | ✅ 그대로 사용 |
| bind 대상 통제 | ❌ 최초 focus 이후 재시도는 활성 Chrome 상태에 맡김 | ✅ 매 bind 시도 직전 LinkedIn 전용창 재-focus |
| 잘못된 URL bind 처리 | ⚠️ 로그 후 재시도, 마지막에는 전체 cleanup | ✅ 잘못 붙은 세션은 즉시 `unbind` 후 재-focus 재시도 |
| 사용자 탭 닫힘 위험 | ⚠️ wrong-bind 후 cleanup이 `close`까지 갈 수 있음 | ✅ wrong-bind 재시도 중에는 `close` 금지, `unbind`만 수행 |
| 사용자 화면 방해 | ⚠️ 전용창이 전면에 올 수 있음 | ⚠️ bind 순간 focus는 유지. 지속 전면 점유는 하지 않음 |
| 실패 로그 | ⚠️ 실제 URL만 출력 | ✅ 시도 번호, 기대 URL, 실제 URL, refocus 결과 출력 |

## 범위

포함:

- `linkedin_scrap.py`의 bind 재시도 절차 안정화
- bind 시도마다 `owned_hwnd` LinkedIn 창 focus
- wrong URL bind 직후 `unbind` 수행
- wrong URL bind에서는 사용자 탭을 닫을 수 있는 `close` 호출 금지
- 관련 pytest 보강
- 실제 `python linkedin_scrap.py --mode update` 검증

제외:

- OpenCLI 제거 또는 Playwright 전환
- 별도 isolated/browser background session 전환
- Chrome 프로필 변경
- LinkedIn parser, GraphQL collector, merge logic 변경
- Threads/X 수집 변경
- `web_viewer/` UI 변경
- 기존 `output_linkedin/`, `output_total/` 파일의 수동 보정

## 영구 데이터 영향

이 계획은 수집 절차의 bind 안정화만 다룬다. 데이터 schema나 저장 규칙은 변경하지 않는다.

영향 가능 surface:

- 성공 QA를 실행하면 최신 `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`이 새로 생성 또는 갱신될 수 있다.
- `total_scrap.py --mode update`까지 실행하면 `output_total/total_full_YYYYMMDD.json`이 갱신될 수 있다.
- `logs/linkedin.log`, `logs/scrap_progress.log`는 QA 실행 로그로 갱신될 수 있다.

마이그레이션은 필요 없다.

백업/롤백 기준:

- 현재 `utils/common.py`의 `save_json()`은 대상 파일을 직접 쓰기 모드로 열어 덮어쓴다. 따라서 실제 QA 전에 최신 LinkedIn full 파일, 해당 `.md`, 최신 total full 파일을 local-only 백업한다.
- 백업은 `.omo/evidence/linkedin-opencli-bind-qa/backups/` 아래에 둔다.
- QA 중 실패하거나 JSON parse가 깨지면 백업 파일을 원래 위치로 `Copy-Item -Force` 복원한다.
- 백업과 로그 tail 증거는 local-only evidence로 보고 커밋하지 않는다.
- 실제 수집으로 갱신된 `output_linkedin/` 또는 `output_total/` 데이터는 사용자 요청이 있을 때만 별도 data 커밋으로 다룬다. 코드 수정 커밋에는 섞지 않는다.

## 파일 구조

- Modify: `linkedin_scrap.py`
  - `bind_opencli_browser_session()`에 `owned_hwnd` 인자 추가
  - bind 루프 안에서 시도마다 `prepare_owned_chrome_window_for_bind(owned_hwnd)` 실행
  - URL 불일치 시 `unbind`만 수행하고 재시도
  - `collect_opencli_posts()`의 cleanup flag를 `daemon_touched`와 `validated_bound_session`으로 분리
- Modify: `tests/integration/test_linkedin_opencli_pipeline.py`
  - wrong URL bind에서 focus가 매번 반복되는지 검증
  - wrong URL bind에서 `close`가 호출되지 않는지 검증
  - 성공 bind에서 기존 cleanup 순서가 유지되는지 검증
- No change: `scripts/linkedin_opencli_shadow_collect.mjs`
- No change: `total_scrap.py`
- No change: `web_viewer/`

실행 중 추가 변경:

- Modify: `scripts/linkedin_opencli_shadow_parse.py`
  - update 모드에서 raw 디렉터리에 함께 생성되는 `existing_ids.json`을 raw page로 오인하지 않도록 `linkedin_opencli_raw_*.json`만 파싱

---

## Task 1: wrong-bind 재시도 동작을 테스트로 고정

**Files:**

- Modify: `tests/integration/test_linkedin_opencli_pipeline.py`

- [x] **Step 1: 현재 실패를 재현하는 테스트 기대값을 먼저 바꾼다**

기존 `test_collect_opencli_posts_cleans_opencli_after_wrong_url_bind_failure`를 아래 의도로 수정한다.

```python
def test_collect_opencli_posts_refocuses_and_unbinds_between_wrong_url_bind_attempts(monkeypatch):
    import linkedin_scrap

    events = []

    class FakeCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    wrong_payloads = [
        '{"session":"linkedin_saved_production","url":"http://127.0.0.1:51981/","title":"Local"}',
        '{"session":"linkedin_saved_production","url":"https://github.com/","title":"GitHub"}',
        '{"session":"linkedin_saved_production","url":"https://github.com/","title":"GitHub"}',
    ]

    def fake_run(command, capture_output, text, encoding):
        if command[-2:] == ["daemon", "status"]:
            events.append(("daemon_status", None))
            return FakeCompletedProcess(stdout="Daemon: not running")
        if command[-2:] == ["daemon", "stop"]:
            events.append(("daemon_stop", None))
            return FakeCompletedProcess(stdout="Daemon stopped.")

        action = command[-1]
        if action == "bind":
            events.append(("bind", None))
            return FakeCompletedProcess(stdout=wrong_payloads.pop(0))
        if action == "unbind":
            events.append(("unbind", None))
            return FakeCompletedProcess(stdout="{}")
        if action == "close":
            events.append(("close", None))
            return FakeCompletedProcess(stdout="{}")

        pytest.fail(f"unexpected OpenCLI command: {command}")

    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 6161)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda hwnd: events.append(("focus", hwnd)) or True)
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)
    monkeypatch.setattr(linkedin_scrap.time, "sleep", lambda _interval: None)
    monkeypatch.setattr(linkedin_scrap, "validate_bound_opencli_session", lambda: pytest.fail("validation must not run"))
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time, existing_codes=None: pytest.fail("collector must not run"),
    )
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="OpenCLI browser bind attached to unexpected URL: https://github.com/"):
        linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 10, 13, 31, 37))

    assert events == [
        ("daemon_status", None),
        ("focus", 6161),
        ("bind", None),
        ("unbind", None),
        ("focus", 6161),
        ("bind", None),
        ("unbind", None),
        ("focus", 6161),
        ("bind", None),
        ("unbind", None),
        ("daemon_stop", None),
        ("wm_close", 6161),
    ]
```

완료 기준:

- 테스트가 현재 구현에서 실패한다.
- 실패 이유가 focus 1회만 발생하거나 wrong-bind 후 `close`가 호출되는 순서 차이로 나타난다.

검증:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_collect_opencli_posts_refocuses_and_unbinds_between_wrong_url_bind_attempts -q
```

기대 출력:

```markdown
FAILED
```

---

## Task 2: bind 루프를 owned HWND aware로 변경

**Files:**

- Modify: `linkedin_scrap.py`

- [x] **Step 1: `bind_opencli_browser_session()` 시그니처를 확장한다**

기존:

```python
def bind_opencli_browser_session(session=OPENCLI_PRODUCTION_SESSION, max_attempts=3, retry_interval=1.0):
```

변경:

```python
def bind_opencli_browser_session(
    session=OPENCLI_PRODUCTION_SESSION,
    max_attempts=3,
    retry_interval=1.0,
    owned_hwnd=None,
):
```

완료 기준:

- 기존 호출은 그대로 동작한다.
- `owned_hwnd`가 전달되면 bind 시도마다 focus를 수행할 수 있다.

- [x] **Step 2: bind 시도 직전에 LinkedIn 전용창을 다시 focus한다**

`bind_opencli_browser_session()` 루프 안에서 OpenCLI `browser bind` 명령을 실행하기 직전에 아래 로직을 넣는다.

```python
for attempt in range(max_attempts):
    attempt_number = attempt + 1
    if owned_hwnd is not None:
        if not prepare_owned_chrome_window_for_bind(owned_hwnd):
            raise RuntimeError(f"OpenCLI Chrome focus failed for HWND {owned_hwnd}")
        print(f"OpenCLI browser bind 전 LinkedIn 창 focus 완료: {attempt_number}/{max_attempts}")

    command = get_opencli_command() + ["browser", session, "bind"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
```

완료 기준:

- `owned_hwnd`가 있는 경우 bind 3회 시도면 focus도 3회 호출된다.
- `focus_chrome_window()` 실패 시 collector로 넘어가지 않는다.

- [x] **Step 3: URL 불일치 시 `unbind`만 수행한다**

URL 검증 실패 블록을 아래처럼 바꾼다.

```python
print(
    "OpenCLI browser bind URL 불일치 "
    f"({attempt_number}/{max_attempts}): expected LinkedIn saved posts, actual={last_url}"
)
run_opencli_browser_session_command("unbind", session=session)
if attempt + 1 < max_attempts:
    time.sleep(retry_interval)
```

주의:

- 여기서는 `cleanup_opencli_browser_session()`을 호출하지 않는다.
- wrong URL에 붙었을 때는 `close`를 호출하지 않는다.
- 최종 실패 메시지는 기존처럼 마지막 URL을 포함한다.

완료 기준:

- wrong URL bind마다 `unbind`가 호출된다.
- wrong URL bind에서는 `close`가 호출되지 않는다.

---

## Task 3: `collect_opencli_posts()` cleanup flag를 분리

**Files:**

- Modify: `linkedin_scrap.py`

- [x] **Step 1: cleanup 상태 변수를 분리한다**

기존 `opencli_session_touched` 하나로 browser cleanup과 daemon cleanup을 함께 제어하지 않는다.

변경 방향:

```python
owned_hwnd = None
validated_bound_session = False
opencli_daemon_touched = False
daemon_was_running = None
```

완료 기준:

- wrong-bind 실패에서도 daemon stop 판단은 가능하다.
- wrong-bind 실패에서는 성공 bind용 `cleanup_opencli_browser_session()`이 실행되지 않는다.

- [x] **Step 2: bind 호출부를 `owned_hwnd` 전달 방식으로 바꾼다**

기존:

```python
if not prepare_owned_chrome_window_for_bind(owned_hwnd):
    raise RuntimeError(f"OpenCLI Chrome focus failed for HWND {owned_hwnd}")
daemon_was_running = is_opencli_daemon_running()
opencli_session_touched = True
bind_opencli_browser_session()
bound_session_state = validate_bound_opencli_session()
```

변경:

```python
daemon_was_running = is_opencli_daemon_running()
opencli_daemon_touched = True
bind_opencli_browser_session(owned_hwnd=owned_hwnd)
validated_bound_session = True
bound_session_state = validate_bound_opencli_session()
```

완료 기준:

- bind 전 focus는 `bind_opencli_browser_session()` 내부에서만 수행된다.
- 성공 bind 뒤에는 기존 검증과 collector 실행이 그대로 이어진다.

- [x] **Step 3: finally cleanup 조건을 분리한다**

변경 방향:

```python
finally:
    if validated_bound_session:
        try:
            cleanup_opencli_browser_session()
        except RuntimeError as exc:
            print(f"OpenCLI browser cleanup 실패: {exc}")
    if opencli_daemon_touched and should_stop_opencli_daemon() and daemon_was_running is False:
        try:
            stop_opencli_daemon()
        except RuntimeError as exc:
            print(f"OpenCLI daemon cleanup 실패: {exc}")
    if owned_hwnd is not None:
        try:
            close_owned_chrome_window(owned_hwnd)
        except RuntimeError as exc:
            print(f"Chrome window cleanup 실패: {exc}")
```

완료 기준:

- wrong-bind 실패 시 `bind_opencli_browser_session()` 내부의 `unbind`만 수행되고, finally의 browser `close`는 실행되지 않는다.
- 성공 bind 뒤 validate/collector 단계 실패 시 기존 browser cleanup은 유지된다.
- daemon이 기존에 꺼져 있었고 OpenCLI가 켜졌다면 stop은 유지된다.

---

## Task 4: 성공 경로와 기존 테스트 기대값을 정렬

**Files:**

- Modify: `tests/integration/test_linkedin_opencli_pipeline.py`

- [x] **Step 1: 성공 bind 경로 테스트의 이벤트 순서를 갱신한다**

`test_collect_opencli_posts_uses_bound_validation_without_whoami`는 `bind_opencli_browser_session`을 monkeypatch하는 현재 구조에서는 내부 focus 반복을 검증하지 못한다. 이 테스트는 기존 목적인 "whoami 미사용, bound validation 사용, 성공 cleanup 유지"만 검증하도록 둔다.

기대 이벤트는 기존과 동일하게 유지 가능하다.

```python
assert events == [
    ("focus", 1001),
    ("bind", None),
    ("unbind", None),
    ("close", None),
    ("stop", None),
    ("wm_close", 1001),
]
```

단, Task 3에서 `collect_opencli_posts()`의 직접 focus가 제거되면 이 테스트의 monkeypatch 방식도 조정해야 한다. 선택지는 둘 중 하나다.

1. `bind_opencli_browser_session` monkeypatch 안에서 `events.append(("focus", 1001))`를 함께 기록한다.
2. 이 테스트의 기대값에서 `("focus", 1001)`를 제거하고, focus 반복은 Task 1의 wrong-bind 테스트가 담당하게 한다.

권장: 2번. 성공 경로 테스트는 bind 내부 구현에 덜 결합되도록 둔다.

완료 기준:

- 성공 경로 테스트가 cleanup 순서만 검증한다.
- focus 반복 검증은 wrong-bind 전용 테스트에 집중된다.

- [x] **Step 2: 기존 bind retry 단위 테스트를 확장한다**

`test_bind_opencli_browser_session_retries_until_saved_posts_url`를 `owned_hwnd=6161`로 호출하고 focus/unbind 순서를 검증한다.

핵심 기대:

```python
assert events == [
    ("focus", 6161),
    ("bind", None),
    ("unbind", None),
    ("focus", 6161),
    ("bind", None),
]
```

완료 기준:

- 첫 번째 wrong URL 뒤 `unbind`가 실행된다.
- 두 번째 시도 전에 focus가 다시 실행된다.
- LinkedIn 저장글 URL에 붙으면 `unbind` 없이 return한다.

검증:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_bind_opencli_browser_session_retries_until_saved_posts_url -q
```

기대 출력:

```markdown
1 passed
```

---

## Task 5: 테스트와 정적 검증

**Files:**

- Modify: 없음

- [x] **Step 1: 관련 통합 테스트를 실행한다**

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
```

기대 출력:

```markdown
25 passed
```

실제 테스트 개수가 바뀌면 통과 개수는 현재 파일 기준으로 갱신한다. 실패가 있으면 실패 테스트명과 원인을 계획 실행 로그에 남긴다.

- [x] **Step 2: OpenCLI cleanup 테스트를 실행한다**

```powershell
pytest tests/unit/test_opencli_cleanup.py -q
```

기대 출력:

```markdown
3 passed
```

- [x] **Step 3: LinkedIn collector JS 문법 검사를 유지한다**

이번 변경은 JS 파일을 건드리지 않아야 하지만, 최근 LinkedIn 수집 변경의 회귀 방지로 문법 검사는 유지한다.

```powershell
node --check scripts/linkedin_opencli_shadow_collect.mjs
```

기대 출력:

```markdown
exit 0
```

- [x] **Step 4: CLI 도움말 smoke를 실행한다**

```powershell
node utils/query-sns.mjs --help
```

기대 출력:

```markdown
Usage 또는 command help 출력
```

---

## Task 6: 실제 LinkedIn update QA

**Files:**

- Runtime data may change: `output_linkedin/python/*`, `output_total/*`, `logs/linkedin.log`, `logs/scrap_progress.log`

- [x] **Step 1: 실행 전 상태와 백업을 기록한다**

```powershell
git status --short --untracked-files=all
Get-ChildItem output_linkedin/python -Filter 'linkedin_py_full_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 3 FullName,LastWriteTime
Get-ChildItem output_linkedin/opencli_runtime/raw -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 3 FullName,LastWriteTime

$evidenceRoot = ".omo/evidence/linkedin-opencli-bind-qa"
$backupRoot = Join-Path $evidenceRoot "backups"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

$latestLinkedinJson = Get-ChildItem output_linkedin/python -Filter 'linkedin_py_full_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$latestLinkedinMd = if ($latestLinkedinJson) { Get-Item ($latestLinkedinJson.FullName -replace '\.json$', '.md') -ErrorAction SilentlyContinue }
$latestTotalJson = Get-ChildItem output_total -Filter 'total_full_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($latestLinkedinJson) { Copy-Item -LiteralPath $latestLinkedinJson.FullName -Destination (Join-Path $backupRoot $latestLinkedinJson.Name) -Force }
if ($latestLinkedinMd) { Copy-Item -LiteralPath $latestLinkedinMd.FullName -Destination (Join-Path $backupRoot $latestLinkedinMd.Name) -Force }
if ($latestTotalJson) { Copy-Item -LiteralPath $latestTotalJson.FullName -Destination (Join-Path $backupRoot $latestTotalJson.Name) -Force }
```

기대:

- 코드 변경 파일과 사용자 기존 변경 파일이 구분된다.
- 최신 LinkedIn full/raw 기준 시각이 확인된다.
- `.omo/evidence/linkedin-opencli-bind-qa/backups/`에 최신 LinkedIn/total 백업이 생성된다.
- 백업 폴더는 local-only evidence로 남기고 커밋하지 않는다.

- [x] **Step 2: 실제 LinkedIn update를 실행한다**

```powershell
python linkedin_scrap.py --mode update
```

성공 기대:

```markdown
OpenCLI browser bind 전 LinkedIn 창 focus 완료: 1/3
OpenCLI browser bind 완료
✅ OpenCLI LinkedIn 저장글 창 확인: linkedin
📥 OpenCLI raw 수집 완료: \d+ pages, \d+ unique IDs
✅ OpenCLI parse 검증 통과
✅ LinkedIn full 저장 기준: output_linkedin/python\linkedin_py_full_\d{8}.json
```

실패 기대:

- 실패하더라도 로그에 `OpenCLI browser bind URL 불일치 (n/3)`가 시도별로 남는다.
- wrong URL마다 `unbind`가 수행된다.
- wrong URL 실패 경로에서 `close`가 호출되지 않는다.
- 실패 후 최신 LinkedIn JSON/MD 또는 total JSON이 parse 불가 상태면 Step 1 백업에서 복원한다.

- [x] **Step 3: 통합 파일 갱신을 항상 검증한다**

LinkedIn update가 성공하면 아래 명령을 항상 실행한다. 이 계획의 완료 기준은 LinkedIn 원천 파일과 total 파일의 count 일치까지 포함한다.

```powershell
python total_scrap.py --mode update
node utils/query-sns.mjs stats
```

기대:

- `stats.files.posts`가 최신 `output_total/total_full_YYYYMMDD.json`를 가리킨다.
- LinkedIn count가 최신 `output_linkedin/python/linkedin_py_full_YYYYMMDD.json` count와 일치한다.
- 신규 1건이 있으면 LinkedIn count가 이전보다 1 증가한다.
- `git status --short --untracked-files=all`에서 QA로 갱신된 `output_linkedin/`, `output_total/`, `logs/`, `.omo/evidence/` 변경이 코드 변경과 구분된다.

- [x] **Step 4: QA 실패 시 복원 기준을 적용한다**

아래 중 하나라도 발생하면 백업 복원을 수행하고 실패 원인을 기록한다.

- `python linkedin_scrap.py --mode update`가 non-zero로 종료
- 최신 `output_linkedin/python/linkedin_py_full_*.json`이 JSON parse 실패
- 최신 `output_total/total_full_*.json`이 JSON parse 실패
- LinkedIn full count와 total LinkedIn count가 불일치

복원 명령:

```powershell
$backupRoot = ".omo/evidence/linkedin-opencli-bind-qa/backups"
$latestLinkedinBackup = Get-ChildItem $backupRoot -Filter 'linkedin_py_full_*.json' | Sort-Object Name -Descending | Select-Object -First 1
$latestLinkedinMdBackup = Get-ChildItem $backupRoot -Filter 'linkedin_py_full_*.md' | Sort-Object Name -Descending | Select-Object -First 1
$latestTotalBackup = Get-ChildItem $backupRoot -Filter 'total_full_*.json' | Sort-Object Name -Descending | Select-Object -First 1

if ($latestLinkedinBackup) { Copy-Item -LiteralPath $latestLinkedinBackup.FullName -Destination "output_linkedin/python/$($latestLinkedinBackup.Name)" -Force }
if ($latestLinkedinMdBackup) { Copy-Item -LiteralPath $latestLinkedinMdBackup.FullName -Destination "output_linkedin/python/$($latestLinkedinMdBackup.Name)" -Force }
if ($latestTotalBackup) { Copy-Item -LiteralPath $latestTotalBackup.FullName -Destination "output_total/$($latestTotalBackup.Name)" -Force }
```

복원 후 검증:

```powershell
node -e "const fs=require('fs'); for (const p of process.argv.slice(1)) JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'')); console.log('json ok')" output_linkedin/python/$($latestLinkedinBackup.Name) output_total/$($latestTotalBackup.Name)
```

기대:

```markdown
json ok
```

---

## Task 7: 문서와 변경 범위 점검

**Files:**

- Modify: `CHANGELOG.md`
- No change: this plan document

- [x] **Step 1: 변경 범위를 확인한다**

```powershell
git diff --stat
git diff -- linkedin_scrap.py tests/integration/test_linkedin_opencli_pipeline.py
```

기대:

- 코드 변경은 `linkedin_scrap.py`, `tests/integration/test_linkedin_opencli_pipeline.py` 중심이다.
- `scripts/linkedin_opencli_shadow_collect.mjs`, `total_scrap.py`, `web_viewer/`는 변경되지 않는다.
- QA 산출물은 아래처럼 처리한다.
  - `.omo/evidence/linkedin-opencli-bind-qa/`: local-only, 커밋 제외
  - `logs/*.log`: local-only, 커밋 제외
  - `output_linkedin/`, `output_total/`: 사용자 요청이 있을 때만 별도 data 커밋으로 분리
  - `CHANGELOG.md`: 구현 완료 시 코드 변경 커밋 범위에 포함 가능

- [x] **Step 2: CHANGELOG를 갱신한다**

기존 루트 `CHANGELOG.md` 형식을 유지한다. `Scope`는 `linkedin-opencli-bind`처럼 실제 변경 범위를 사용한다.

완료 기준:

- 변경 이유가 "wrong active Chrome bind 방지"로 명확히 남는다.
- Threads/X/UI 변경처럼 범위 밖 내용이 섞이지 않는다.

- [ ] **Step 3: 커밋은 사용자 요청 시에만 `cp` 스킬로 진행한다**

이 레포 규칙상 직접 `git add/commit`을 실행하지 않는다.

커밋이 요청되면:

```markdown
cp 스킬 사용
security-gate precommit --repo D:/vibe-coding/scrap_sns --staged
관심사별 커밋
```

권장 커밋 메시지:

```markdown
fix(linkedin-opencli-bind): LinkedIn 전용창 bind 재시도 안정화 — 활성 Chrome 오인식 방지
```

---

## 최종 완료 기준

- `pytest tests/integration/test_linkedin_opencli_pipeline.py -q`가 통과한다.
- `pytest tests/unit/test_opencli_cleanup.py -q`가 통과한다.
- `node --check scripts/linkedin_opencli_shadow_collect.mjs`가 exit 0이다.
- 실제 `python linkedin_scrap.py --mode update`에서 OpenCLI가 LinkedIn 저장글 URL에 bind된다.
- 실제 QA 후 `python total_scrap.py --mode update`와 `node utils/query-sns.mjs stats`로 LinkedIn 원천 count와 total LinkedIn count가 일치한다.
- wrong URL bind 재현 테스트에서 시도마다 focus -> bind -> unbind 순서가 검증된다.
- wrong URL bind 실패 경로에서 사용자 GitHub/로컬 탭을 닫을 수 있는 `close` 호출이 없다.
- OpenCLI, 기존 로그인 Chrome 프로필, raw -> parse -> merge 파이프라인은 유지된다.
- `.omo/evidence/`, `logs/`, QA data output의 커밋 포함/제외 기준이 `git status`로 분리 확인된다.

## Self Review

- 목적 적합성: 현재 실패 원인인 active Chrome wrong-bind만 직접 겨냥한다.
- 범위 통제: OpenCLI 제거, Playwright 전환, isolated session 전환을 명시적으로 제외했다.
- 테스트 가능성: wrong URL 3회 재현, 성공 bind, cleanup 분리를 pytest로 검증한다.
- 데이터 안전성: schema 변경과 마이그레이션은 없지만 실제 QA 전 백업, 실패 시 복원 명령, QA 산출물 커밋 제외/분리 기준을 명시했다.
- 사용자 방해: bind 순간 focus는 남지만 지속 전면 점유를 목표로 하지 않는다. 화면 밖 배치 등 UI 위치 제어는 별도 후속 개선으로 남긴다.

## Plan Check 반영 이력

- 검수보고서: [[20260710_01_LinkedIn-OpenCLI-bind-재시도-안정화-구현계획_검수보고서]]
- 반영:
  - Task 6의 조건부 실행 문구를 제거하고 total 갱신/검증을 필수화했다.
  - 실행 불가 placeholder 표기를 실제 경로와 정규식 기대값으로 바꿨다.
  - QA 전 백업, 실패 시 복원, QA 산출물 local-only/data-commit 분리 기준을 추가했다.
  - focus stealing 리스크와 트레이드오프는 "현재 vs 개선" 및 Self Review의 사용자 방해 항목으로 유지했다.

## 수행내역

수행 시각: 2026-07-10 14:26 KST

### 구현 결과

- `linkedin_scrap.py`
  - `bind_opencli_browser_session()`에 `owned_hwnd` 인자를 추가했다.
  - bind 시도 직전마다 LinkedIn 전용 Chrome 창을 다시 focus하도록 바꿨다.
  - wrong URL bind는 즉시 `unbind`하고 재시도하며, 이 경로에서는 `close`를 호출하지 않도록 했다.
  - 성공 bind 이후 cleanup과 daemon cleanup 상태를 분리했다.
  - Chrome 복원 프롬프트가 새 창 후보에 섞인 경우 실제 새 Chrome 창을 선택하도록 보강했다.
  - `SetForegroundWindow`가 일시 실패하는 경우를 위해 focus를 짧게 재시도하도록 했다.
  - LinkedIn saved URL이 확인되면 본문 문구가 즉시 로드되지 않아도 계속 진행하고 경고만 남기도록 했다.
- `scripts/linkedin_opencli_shadow_parse.py`
  - update 모드의 `existing_ids.json`을 raw page로 오인하지 않도록 `linkedin_opencli_raw_*.json`만 파싱하게 했다.
- `tests/integration/test_linkedin_opencli_pipeline.py`
  - wrong URL bind에서 `focus -> bind -> unbind`가 매 시도 반복되는지 검증했다.
  - wrong URL bind 실패 경로에서 `close`가 호출되지 않는지 검증했다.
  - Chrome 복원 프롬프트 후보 제외, focus 재시도, saved URL 문구 미확인 허용 테스트를 추가했다.
- `tests/unit/test_linkedin_opencli_shadow_parse.py`
  - `existing_ids.json`이 raw parser 대상에서 제외되는 회귀 테스트를 추가했다.
- `CHANGELOG.md`
  - `linkedin-opencli-bind` 범위의 fix 항목을 추가했다.

### Red/Green 확인

- wrong-bind 재현 테스트는 기존 구현에서 실패했다.
  - 명령: `pytest tests/integration/test_linkedin_opencli_pipeline.py::test_collect_opencli_posts_refocuses_and_unbinds_between_wrong_url_bind_attempts -q`
  - 실패 원인: 기존 구현은 최초 focus 1회 후 bind만 반복하고, 실패 cleanup에서 `close`까지 호출했다.
- `existing_ids.json` parser 테스트는 기존 구현에서 실패했다.
  - 명령: `pytest tests/unit/test_linkedin_opencli_shadow_parse.py -vv`
  - 실패 원인: `existing_ids.json` 배열을 detail dict로 처리해 `AttributeError: 'list' object has no attribute 'get'`가 발생했다.
- Chrome 복원 프롬프트 후보 테스트는 기존 구현에서 실패했다.
  - 명령: `pytest tests/integration/test_linkedin_opencli_pipeline.py::test_open_owned_chrome_window_ignores_chrome_restore_prompt_candidate -q`
  - 실패 원인: restore prompt와 새 Chrome 창 2개를 모두 후보로 보고 ambiguous 처리했다.
- saved URL 문구 미확인 테스트는 기존 구현에서 실패했다.
  - 명령: `pytest tests/integration/test_linkedin_opencli_pipeline.py::test_validate_bound_opencli_session_accepts_saved_url_without_loaded_page_text -q`
  - 실패 원인: URL은 saved posts였지만 본문/title 문구가 즉시 로드되지 않으면 실패했다.
- focus 재시도 테스트는 기존 구현에서 실패했다.
  - 명령: `pytest tests/integration/test_linkedin_opencli_pipeline.py::test_prepare_owned_chrome_window_for_bind_retries_focus_failure -q`
  - 실패 원인: `prepare_owned_chrome_window_for_bind()`에 focus retry 파라미터가 없고 1회 실패로 중단했다.

### 검증 결과

- `pytest tests/integration/test_linkedin_opencli_pipeline.py -q`
  - 결과: `28 passed`
- `pytest tests/unit/test_linkedin_opencli_shadow_parse.py -q`
  - 결과: `1 passed`
- `pytest tests/unit/test_opencli_cleanup.py -q`
  - 결과: `3 passed`
- `node --check scripts/linkedin_opencli_shadow_collect.mjs`
  - 결과: exit 0
- `node utils/query-sns.mjs --help`
  - 결과: Usage/help 출력 확인

### 실제 QA 결과

- QA 전 백업 위치:
  - `.omo/evidence/linkedin-opencli-bind-qa/backups/`
- `python linkedin_scrap.py --mode update`
  - 결과: 성공
  - bind 로그: `OpenCLI browser bind 전 LinkedIn 창 focus 완료: 1/3`, `OpenCLI browser bind 완료`
  - raw 수집: `4 pages`, `39 unique IDs`
  - parse 검증: `parsed=39`, `duplicates=0`, `parser_failed=0`
  - 저장 결과: `output_linkedin/python/linkedin_py_full_20260710.json`
  - LinkedIn full count: `613`
  - 신규 update 파일: `output_linkedin/python/update/linkedin_python_update_20260710_142402.json` (`1개`)
- `python total_scrap.py --mode update`
  - 결과: 성공
  - 저장 결과: `output_total/total_full_20260710.json`
  - total count: `1,776`
  - 이미지 처리: 신규 `1개` 저장
  - 참고: 오래된 운영 JSON 자동 정리에서 `safe-trash.cmd` 확장자 문제 경고가 발생했다. 수집/병합 결과는 성공했으나 cleanup helper 경로는 별도 이슈다.
- `node utils/query-sns.mjs stats`
  - 결과: total `1,776`, LinkedIn `613`, Threads `1,069`, X `94`
  - `files.posts`: `output_total/total_full_20260710.json`
  - LinkedIn 원천 `613`건과 total LinkedIn `613`건이 일치한다.

### 변경 범위 메모

- 코드/테스트/문서 변경:
  - `linkedin_scrap.py`
  - `scripts/linkedin_opencli_shadow_parse.py`
  - `tests/integration/test_linkedin_opencli_pipeline.py`
  - `tests/unit/test_linkedin_opencli_shadow_parse.py`
  - `CHANGELOG.md`
  - `_docs/20260710_01_LinkedIn-OpenCLI-bind-재시도-안정화-구현계획.md`
  - `_docs/plan-check/20260710_01_LinkedIn-OpenCLI-bind-재시도-안정화-구현계획_검수보고서.md`
- 실제 QA 산출물:
  - `output_linkedin/python/linkedin_py_full_20260710.json`
  - `output_total/total_full_20260710.json`
  - `output_twitter/python/twitter_py_full_20260710.json`
  - `output_twitter/python/twitter_py_simple_20260710.json`
- 커밋은 수행하지 않았다. 요청 시 `cp` 스킬 흐름으로 코드/문서와 data 산출물을 관심사별로 분리해야 한다.
