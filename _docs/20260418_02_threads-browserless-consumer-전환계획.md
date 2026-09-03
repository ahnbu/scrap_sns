---
title: "Threads Browserless Consumer Cutover Implementation Plan"
created: "2026-04-18"
tags:
  - plan
  - threads
  - browserless
session_id: f78abf57-7453-405a-8226-9adb476e3fba
ai: claude
status: completed
related_plan: "[[20260418_01_twitter-cli-consumer-전환계획]]"
---

# Threads Browserless Consumer Cutover Implementation Plan

## Context

현재 `thread_scrap_single.py`는 Playwright로 `https://www.threads.com/@{username}/post/{code}` 페이지를 열어 `page.content()` HTML을 받은 뒤, `utils/threads_parser.py`의 순수 파이썬 함수(`extract_json_from_html`, `extract_items_multi_path`, `extract_posts_from_node`)로 `thread_items` JSON을 추출한다. 브라우저가 실제로 하는 일은 **쿠키 주입 + HTML 수신** 두 가지뿐이고, Threads는 SSR이라 응답 HTML 본문 안에 `"result":{"data":...thread_items...}` JSON이 이미 임베드되어 있다. 따라서 브라우저 없이 `requests`(또는 `httpx`)로 동일 HTML을 받아 동일 파서에 넘기면 self-reply 타래 병합·승격·failures 관리 로직(`merge_thread_items`, `promote_to_full_history`, `scrap_failures_threads.json`)을 그대로 재사용할 수 있다.

이번 전환의 목표는 세 가지다. 첫째, 건당 3–8초 걸리던 상세 수집을 0.3–1초 수준으로 단축한다. 둘째, Chrome 프로세스(수백 MB 메모리)와 `CONCURRENCY_LIMIT=3` 제약을 제거해 더 높은 병렬성을 얻는다. 셋째, twitter-cli 전환(`utils/twitter_cli_adapter.py` + `twitter_scrap_single.py`)에서 확립된 DI 패턴을 Threads에도 동일하게 적용해 테스트 주입성을 확보한다.

공개된 `threads-cli`는 존재하지 않고 `Danie1/threads-api`·`dmytrostriletskyi/threads-net`은 2023-09 Meta cease-letter 이후 archive 상태다. 공식 Threads Graph API는 permalink → media_id 역조회를 제공하지 않으므로, 이번 계획은 "자체 쿠키 주입 HTTP fetcher + 기존 HTML 파서 재사용"으로 한정한다. Producer(`thread_scrap.py`의 `/saved` 무한 스크롤 + GraphQL response 인터셉트)는 이번 범위에서 변경하지 않는다.

**Goal:** Consumer인 `thread_scrap_single.py`를 browserless `requests` 기반으로 전환하면서 기존 파서·병합·스키마·failures·full/simple 파일 흐름을 그대로 유지한다.

**Architecture:** `thread_scrap_single.py`는 대상 선정·파일 저장·failures 카운트·병합·승격만 담당하고, 새 `utils/threads_http_adapter.py`가 쿠키 로드, HTTP GET 호출, `requests.Response.text` 반환을 맡는다. 어댑터 반환형은 **HTML 문자열**(또는 None)로 한정해 `extract_json_from_html` → `extract_items_multi_path` 기존 파이프라인을 그대로 먹인다. 이미지 URL 처리·`root_code` 기준 그룹핑·`merge_thread_items`·`is_merged_thread` 승격은 전혀 손대지 않는다.

**Tech Stack:** Python 3.13, `requests`(이미 레포에 설치됨), `pytest`, PowerShell

---

## Scope Lock

- In scope: `thread_scrap_single.py` consumer cutover, 신규 `utils/threads_http_adapter.py`, 단위/통합 테스트, 운영 문서 업데이트.
- Out of scope: `thread_scrap.py` producer 변경, `utils/threads_parser.py` 로직 변경(모듈 그대로 재사용), `auth_threads.json` 포맷 변경, merge/promote 로직 수정, 과거 데이터 마이그레이션.
- Accepted behavior change 1: 새로 상세 수집되는 Threads post의 `source` 값은 `consumer_detail`(기존) 그대로 유지(어댑터가 교체해도 파서 출력은 같음 — 호환성 확보 차원).
- Accepted behavior change 2: Playwright 의존 제거로 `HEADLESS`/`WINDOW_*` 설정 상수는 deprecated 처리.
- Stop condition: ~~W1 실측에서 `requests.get` + `auth_threads.json` 쿠키 조합이 Playwright HTML과 **동등한 `thread_items` JSON**을 얻지 못하면 즉시 중단하고 plan을 재수립한다.~~ → **[완료]** Codex가 실제 `auth_threads.json` 쿠키로 3개 URL 실측해 모두 200/thread_items 포함/`extract_items_multi_path` 성공 확인. W1은 완료된 것으로 처리하고 W2부터 진행한다.

## File Structure

- Create: `utils/threads_http_adapter.py` — 쿠키 로드, HTTP GET, HTML 반환.
- Create: `tests/unit/test_threads_http_adapter.py` — 쿠키 파싱·헤더 조립·실패 판정 테스트.
- Create: `tests/integration/test_thread_scrap_single_browserless.py` — temp-copy 통합 테스트, HTML fixture 기반.
- Create: `tests/fixtures/threads_http/sample_post.html` — 기존 `tests/fixtures/threads_sample.html` 재활용 또는 신규 스냅샷 1건.
- Modify: `thread_scrap_single.py` — `async_playwright`·`context.new_page` 제거, 어댑터 주입, `main()` 파라미터화.
- Modify: `docs/crawling_logic.md` — Threads consumer 단계 설명을 browserless 기준으로 현행화.
- Modify: `docs/development.md` — Threads consumer source, 인증 경로 정리.
- Modify: `README.md` — 인증 갱신 섹션에 Threads consumer 설명 추가.
- Modify: `CHANGELOG.md` — feat/fix/docs 3회 분리.
- No change: `utils/threads_parser.py`, `utils/post_schema.py`, `tests/unit/test_threads_parser.py`, `tests/unit/test_threads_schema_guard.py`, `tests/smoke/test_threads_smoke.py`, `thread_scrap.py`, `renew_auth.py`, `migrate_threads_domain.py`.

## Persistence Surface And Migration Decision

### Affected surfaces

- `output_threads/python/threads_py_simple_*.json` — `is_detail_collected` 플래그만 갱신(schema 변화 없음).
- `output_threads/python/threads_py_full_*.json` — 상세 수집 결과가 병합(`is_merged_thread=True`)되는 동작은 그대로.
- `scrap_failures_threads.json` — 기존 `{code: {fail_count, url?}}` 스키마 유지. `total_scrap.py`는 하위호환으로 `fail_count` 우선, 없으면 `count`를 읽는다. 기존 Twitter failure 파일(`count`)과 Threads failure 파일(`fail_count`)을 모두 수용한다.
- `output_total/total_full_*.json` — 다음 `total_scrap.py --mode update`부터 새 Threads 상세 결과를 병합.
- `web_viewer/data.js` — 다음 `python -m utils.build_data_js`부터 반영.
- `auth/auth_threads.json` — 포맷 변경 없음(기존 Playwright storage_state JSON을 그대로 읽음).

### Migration decision

- Existing data migration: 하지 않는다.
- Reason 1: 파서 출력 스키마와 파일 패턴이 바뀌지 않는다(`extract_posts_from_node`를 그대로 호출).
- Reason 2: `source="consumer_detail"` 문자열을 유지하므로 소비자(viewer, `build_data_js`)가 분기를 바꿀 필요 없다.
- Reason 3: `auth_threads.json`은 Playwright storage_state 포맷(`cookies[]`, `origins[]`)을 읽기만 하고 갱신하지 않으므로 `renew_auth.py`는 그대로 쓴다.

### Post-cutover commands

- Refresh merged data: `python total_scrap.py --mode update`
- Refresh viewer cache: `python -m utils.build_data_js`

### Verification commands

- Unit: `pytest tests/unit/test_threads_http_adapter.py -q`
- Integration: `pytest tests/integration/test_thread_scrap_single_browserless.py -q`
- Regression: `pytest tests/unit/test_threads_parser.py tests/unit/test_threads_schema_guard.py tests/unit/test_migrate_threads_domain.py -q`
- Smoke (manual, optional): `pytest tests/smoke/test_threads_smoke.py -q` (현재 Playwright 기반 — 영향 없음)
- Contract: `pytest tests/contract/test_schemas.py -q`

## Wave 구성

4개 Wave로 분할. W1은 실측(정보 수집, 코드 변경 없음), W2는 어댑터 구현, W3는 consumer 재배선, W4는 검증과 문서·커밋.

```
Wave 1: 실측 — ✅ 완료 (Codex 실측: 3개 URL 모두 200/thread_items/extract 성공)

Wave 2: 어댑터 구현 — ✅ 완료
  ├─ W2-A: utils/threads_http_adapter.py 신설 + 단위 테스트
  └─ W2-B: fixture 정리(기존 스냅샷 재사용 or 신규 1건 캡처)

Wave 3: Consumer 재배선 — ✅ 완료
  ├─ W3-A: thread_scrap_single.py에서 Playwright 제거, 어댑터 주입
  └─ W3-B: tests/integration/test_thread_scrap_single_browserless.py 추가

Wave 4: 검증 + 문서 + 커밋 — ✅ 완료
  ├─ W4-A: 회귀 테스트 전량 통과 — ✅ 완료 (22 passed, 0.98s)
  ├─ W4-B: sandbox live smoke + docs/*, README, CHANGELOG 업데이트 — ✅ 완료
  ├─ W4-C: `total_scrap.py --mode update` 통합 실행 — ✅ 완료
  └─ W4-D: cp 스킬로 관심사별 커밋 분리 — ✅ 완료
```

---

## Wave 1 — 실측 ✅ 완료

> Codex가 `auth/auth_threads.json` 쿠키로 3개 URL을 직접 실측해 전량 통과. W2부터 진행한다.

- HTTP 200 ✅ (302 리다이렉트 없음)
- 응답 HTML에 `thread_items` 포함 ✅
- `extract_json_from_html()` dict 반환 ✅
- `extract_items_multi_path()` 1~3개 아이템 추출 ✅

---

## Wave 2 — 어댑터 구현

### W2-A. utils/threads_http_adapter.py

**인터페이스**(twitter-cli 어댑터와 동일 DI 패턴):

```python
THREADS_COOKIE_KEYS = ("sessionid", "csrftoken", "ds_user_id", "mid", "ig_did", "rur")

@dataclass(frozen=True)
class ThreadsFetchResult:
    html: str
    status_code: int

def load_threads_cookies(auth_file: str = "auth/auth_threads.json") -> dict | None: ...
def build_threads_headers(base_headers: dict | None = None) -> dict: ...
def fetch_thread_html(
    url: str,
    cookies: dict,
    headers: dict,
    timeout: int = 15,
    runner = requests.get,
) -> ThreadsFetchResult | None: ...
```

**구현 요점**:
- `load_threads_cookies`: Playwright storage_state JSON(`{"cookies": [...], "origins": [...]}`)을 읽어 `domain` suffix가 `.threads.com`인 것만 dict로 반환. 필수 키가 모두 없으면 `None`.
- `build_threads_headers`: Chrome UA + `Accept`/`Accept-Language`/`Sec-Fetch-*` 기본값. 호출자가 UA를 override 가능.
- `fetch_thread_html`: `runner(url, cookies=cookies, headers=headers, timeout=timeout, allow_redirects=True)` 호출 후 `status_code != 200`이면 `None`, 아니면 `ThreadsFetchResult(text, 200)`.
- 실패 모드는 **HTTP 레벨만** 판정. `thread_items` 존재 여부는 **판정하지 않음**(파서가 담당). 이유: 단일 책임.

**보안**: 쿠키 값은 stderr·print·로그·파일에 절대 출력 금지. 테스트는 `_write_cookie_file(tmp_path, ...)` fixture로만.

**단위 테스트**(`tests/unit/test_threads_http_adapter.py`):
1. `load_threads_cookies_reads_storage_state` — Playwright storage_state 모양의 tmp 파일에서 6개 키 모두 추출.
2. `load_threads_cookies_returns_none_when_sessionid_missing` — `sessionid`가 없으면 `None`.
3. `load_threads_cookies_filters_non_threads_domains` — `.instagram.com` 쿠키는 무시.
4. `build_threads_headers_preserves_override` — UA override 동작.
5. `fetch_thread_html_wraps_200_response` — `runner` mock이 200 응답을 주면 `html` 필드에 text 반영.
6. `fetch_thread_html_returns_none_on_302` — 로그인 리다이렉트 시 `None`.
7. `fetch_thread_html_returns_none_on_timeout` — `requests.exceptions.Timeout` 발생 시 `None`.

### W2-B. Fixture

- 기존 `tests/fixtures/threads_sample.html`을 통합 테스트의 `fetch_thread_html` mock 반환값으로 사용 가능한지 확인.
- 사용 불가면 W1-B에서 얻은 실제 HTML 1건을 `tests/fixtures/threads_http/sample_post.html`로 저장하되, **쿠키·개인식별정보 헤더는 제거**한 상태로.

---

## Wave 3 — Consumer 재배선

### W3-A. thread_scrap_single.py 리팩터

**제거**:
- `import asyncio`, `from playwright.async_api import async_playwright` (1–2행)
- `HEADLESS`, `WINDOW_X`, `WINDOW_Y`, `WINDOW_WIDTH`, `WINDOW_HEIGHT` 상수 및 주석
- `async def worker(context, semaphore, ...)` 전체
- `async def run()` 내부의 `async with async_playwright() as p: ...` 블록과 `CONCURRENCY_LIMIT` 세마포어

**유지 (로직은 그대로, 시그니처만 경로 파라미터 추가)**:
- `OUTPUT_DIR`, `SIMPLE_FILE_PATTERN`, `FULL_FILE_PATTERN`, `FAILURES_FILE`, `AUTH_FILE` — 상수는 유지하되 함수 기본값으로만 사용
- `get_post_code`, `merge_thread_items`, `_assert_threads_schema`, normalize_post 호출부 — 변경 없음
- **`load_failures`·`save_failures`·`promote_to_full_history`·`import_from_simple_database`·`sync_detail_collected_flags` — 경로를 파라미터로 주입받도록 시그니처 변경 필수**:
  ```python
  def load_failures(path: str = FAILURES_FILE) -> dict: ...
  def save_failures(failures: dict, path: str = FAILURES_FILE) -> None: ...
  def promote_to_full_history(grouped_data: dict, output_dir: str = OUTPUT_DIR) -> None: ...
  def import_from_simple_database(output_dir: str = OUTPUT_DIR) -> str | None: ...
  def sync_detail_collected_flags(simple_path: str, full_path: str) -> int: ...
  ```
  이유: 현재 이 함수들은 모듈-레벨 상수(`FAILURES_FILE`, `OUTPUT_DIR`)를 직접 참조한다(`thread_scrap_single.py:38, 45, 111, 162`). 파라미터화 없이는 통합 테스트와 W4-B sandbox smoke가 레포 루트를 건드린다. `main()`은 인자로 받은 경로를 각 헬퍼에 명시적으로 전달한다.

**신설**(어댑터 DI를 받는 동기 worker + `main()`):

```python
import requests  # 기존 requirements에 이미 포함
from utils.threads_http_adapter import (
    ThreadsFetchResult,
    build_threads_headers,
    fetch_thread_html,
    load_threads_cookies,
)

def collect_one(
    code: str,
    username: str,
    cookies: dict,
    headers: dict,
    fetch_fn = fetch_thread_html,
) -> list[dict]:
    url = f"https://www.threads.com/@{username}/post/{code}"
    result = fetch_fn(url, cookies=cookies, headers=headers)
    if not result:
        return []
    data = extract_json_from_html(result.html)
    if not data:
        return []
    return extract_items_multi_path(data, code, username)

def main(
    output_dir: str = OUTPUT_DIR,
    failures_file: str = FAILURES_FILE,
    auth_file: str = AUTH_FILE,
    cookie_loader = load_threads_cookies,
    header_builder = build_threads_headers,
    fetch_fn = fetch_thread_html,
    sleep_fn = time.sleep,
    max_workers: int = 5,
) -> None:
    ...
```

**병렬성**: `concurrent.futures.ThreadPoolExecutor(max_workers=5)`로 `collect_one` 병렬 실행. Playwright 세마포어(`CONCURRENCY_LIMIT=3`) 대체. 실제 상한은 Wave 4 실측 후 조정.

**rate limit 완충**: worker 간 `sleep_fn(0.3)` 랜덤 지터(0.2~0.5) 삽입. 기존 `asyncio.sleep(3)`의 "페이지 로딩 대기" 의미는 불필요하므로 제거.

**기존 `run()` → `main()` 호환**: 파일 끝 `if __name__ == "__main__": asyncio.run(run())` → `if __name__ == "__main__": main()`.

### W3-B. 통합 테스트

`tests/integration/test_thread_scrap_single_browserless.py`:

```python
def test_main_writes_outputs_with_mocked_fetch(tmp_path, monkeypatch):
    # 1. output_dir, failure_file, auth_file를 tmp로 구성
    # 2. simple_file에 is_detail_collected=False인 post 1개 배치
    # 3. cookie_loader lambda: {"sessionid": "x", "csrftoken": "y", "ds_user_id": "1"}
    # 4. fetch_fn lambda: ThreadsFetchResult(html=fixture_html, status_code=200)
    # 5. main() 실행
    # 6. 검증:
    #    - threads_py_full_*.json 1개 생성
    #    - posts[0].is_merged_thread is True (fixture가 thread_items 2+ 포함인 경우)
    #    - posts[0].source == "consumer_detail"
    #    - simple_file의 is_detail_collected가 True로 갱신
    #    - failure_file이 빈 dict
```

---

## Wave 4 — 검증 + 문서 + 커밋

### W4-A. 회귀 테스트

```powershell
pytest tests/unit/test_threads_http_adapter.py `
       tests/integration/test_thread_scrap_single_browserless.py `
       tests/unit/test_threads_parser.py `
       tests/unit/test_threads_schema_guard.py `
       tests/unit/test_migrate_threads_domain.py `
       tests/contract/test_schemas.py -q
```

**기대**: 모두 pass. 특히 `test_threads_schema_guard`가 `merge_thread_items` 결과의 `is_merged_thread`, `original_item_count`, `"\n\n---\n\n"` 조인을 그대로 검증하므로 browserless 전환 후에도 schema invariant가 유지됨을 보증.

**실행 결과**:
- `tests/unit/test_threads_http_adapter.py` 7건 pass
- `tests/integration/test_thread_scrap_single_browserless.py` 1건 pass
- `tests/unit/test_threads_parser.py` 3건 pass
- `tests/unit/test_threads_schema_guard.py` 4건 pass
- `tests/unit/test_migrate_threads_domain.py` 5건 pass
- `tests/contract/test_schemas.py` 1건 pass
- `tests/unit/test_total_scrap_should_run_consumer.py` 1건 pass
- 합계: 22 passed, 0.98s

### W4-B. 라이브 실측 (sandbox only)

`tmp/threads-browserless-smoke/` sandbox에 simple 파일 1건 복사 → `is_detail_collected=False`로 초기화 → `thread_scrap_single.main(output_dir=..., failures_file=..., auth_file="auth/auth_threads.json")` 실행. 결과:
- full 파일 1개 생성, `post_count=1`
- 병합 타래는 `is_merged_thread=True`, `is_detail_collected=True`, `source="consumer_detail"`
- sandbox 외부(레포 루트 `output_threads/python/`)는 무변경
- 실측 시간: 약 2.0s

**실행 메모**:
- 실제 `auth/auth_threads.json` 쿠키 사용
- `snapshot_saver=lambda *_args, **_kwargs: None`로 snapshot side effect 차단
- 이 항목은 최초 검수 코멘트의 "미실행" 상태와 달리 이미 완료됨

### W4-C. `total_scrap.py --mode update` 통합 실행

실제 레포 루트에서 `python total_scrap.py --mode update` 1회를 실행했다. 결과:

- 종료 코드 `0`
- Threads / X(Twitter) / LinkedIn 3개 프로세스 모두 완료
- 최신 통합본 저장: `output_total/total_full_20260418.json`
- 메타데이터: `total_count=1079`, `threads_count=753`, `linkedin_count=261`, `twitter_count=79`
- `web_viewer/data.js` 갱신 완료

**Threads 로그 요약**:
- producer update 실행 결과 신규 0건
- consumer 명령은 실행됐고, 최종 타깃은 `0개`
- 스킵 집계: `기수집 38개`, `실패한도 57개`
- 종료 시간: 약 0.17s

**해석**:
- browserless consumer가 전체 오케스트레이터 경로에 정상 연결됨
- `total_scrap.py`의 failure count 해석 수정 이후에도 통합 실행이 깨지지 않음
- 현재 데이터 상태에서는 새 Threads 상세 대상이 없어 consumer가 즉시 종료

**관찰된 경고**:
- `output_total/total_full_20260418.json`을 `json_to_md`가 BOM 때문에 읽지 못하는 기존 경고가 재현됨
- 통합 JSON 저장과 `web_viewer/data.js` 갱신은 정상 완료

### W4-D. 문서 업데이트 + 커밋

**README.md** — 인증 갱신 섹션에 추가:

```
Threads 인증은 producer와 consumer가 같은 storage_state(`auth/auth_threads.json`)를 공유한다.
- thread_scrap.py: Playwright storage_state로 /saved 타임라인 수집
- thread_scrap_single.py: storage_state의 .threads.com 쿠키(sessionid, csrftoken 등)를 requests에 주입
Chrome이 없어도 consumer는 실행된다. 쿠키 재발급은 여전히 `python renew_auth.py`로 수행.
```

**docs/development.md** — Threads 섹션 갱신:
- 상세 수집기: `thread_scrap_single.py` (browserless `requests` 기반)
- 어댑터: `utils/threads_http_adapter.py`
- 파서: `utils/threads_parser.py` (변경 없음)

**docs/crawling_logic.md** — Threads 소비자 단계 설명을 "Playwright tab" → "HTTP GET + HTML 파싱"으로 교체. 병합/승격/failures 섹션은 그대로.

**커밋 분리 결과**(cp 스킬 사용, 하나의 관심사 = 하나의 커밋):
1. `feat(threads-http): HTTP 어댑터 신설` — `utils/threads_http_adapter.py` + 단위 테스트 + fixture
2. `fix(threads-single): browserless consumer 전환` — `thread_scrap_single.py` + 통합 테스트
3. `docs(threads): consumer auth/browserless 흐름과 실행 기록 문서화` — README, docs/*, plan 문서
4. `fix(total-scrap): Threads failure count 하위호환 처리` — `total_scrap.py` + 단위 테스트
5. `chore(data): 통합 산출물 갱신` — `output_total/total_full_20260418.json` + `web_viewer/data.js`

---

## 의사결정 원칙 (구현 중 참조)

1. **파서는 건드리지 않는다.** `utils/threads_parser.py`는 이번 범위에서 read-only. 새 경로가 파서 입력(HTML)을 다르게 주더라도 파서 출력은 기존 테스트를 통과해야 한다.
2. **`auth_threads.json` 포맷은 바꾸지 않는다.** `renew_auth.py` 재작업을 유발하지 않기 위해 storage_state JSON을 read-only로 소비한다.
3. **`source="consumer_detail"` 값은 유지한다.** 소비자(`build_data_js`, viewer)가 source 문자열로 분기하지 않지만, 관측성과 롤백 용이성을 위해 소스 문자열은 보존한다.
4. **stop condition에서 즉시 멈춘다.** W1에서 requests 경로가 Playwright 산출물과 semantic parity를 확보하지 못하면 Wave 2부터는 열지 않는다.
5. **쿠키 값은 어떤 출력 경로에도 남기지 않는다.** 로그, print, 에러 메시지, 커밋 diff, fixture 파일 모두.

## 리스크 및 미결 사항

- **Meta 탐지 강화**: 향후 Cloudflare/TLS 지문(JA3) 기반 차단이 강화되면 `requests`가 403을 받을 수 있다. `httpx` 또는 `curl_cffi`(Chrome TLS 모사)로 교체 가능하도록 어댑터 내 `runner` 파라미터를 DI로 노출해둔다.
- **쿠키 만료**: `sessionid`가 만료되면 Producer(Playwright)도 같이 막히므로 공동 실패. `renew_auth.py` 주기를 문서에 명시(현재도 주기적 재발급 전제). 별도 만료 감지 로직은 본 계획 범위 밖.
- **Producer 전환 미포함**: `thread_scrap.py`는 `/saved` 무한 스크롤과 GraphQL response 인터셉트가 본질이라 단순 HTTP fetch로 대체 난이도가 훨씬 높다. 본 계획의 성공 이후 별도 plan으로 분리 검토.
- **`save_debug_snapshot` 호출**: 현재 `thread_scrap_single.py:286`에서 `utils.common.save_debug_snapshot(html, "threads")`가 호출된다. 전환 후에도 `collect_one` 내부에서 동일하게 호출해 스냅샷 생태계를 유지한다(기존 snapshot 폴더 활용).

## 검수 반영 메모

- Claude 검수 기준 크리티컬 이슈 없음.
- Codex 피드백 3건 반영 상태 확인:
  - W3-A 헬퍼 경로 파라미터화 완료
  - `thread_scrap_single.py`에서 Playwright/`asyncio` 제거 완료
  - W1 parity 실측 완료 처리 반영
- 단, Claude 코멘트의 "라이브 smoke 미실행"은 최신 상태와 불일치한다. Codex가 실제 쿠키로 sandbox live smoke를 이미 완료했다.

## 후속 메모

- 남은 blocker는 없다.
- 별도 후속 후보는 `json_to_md`의 UTF-8 BOM 경고 정리다. 이번 scope에서는 기능 회귀와 무관해 보류했다.

## 검증 체크리스트

- [x] `pytest tests/unit/test_threads_http_adapter.py -q` → pass
- [x] `pytest tests/integration/test_thread_scrap_single_browserless.py -q` → pass
- [x] `pytest tests/unit/test_threads_parser.py tests/unit/test_threads_schema_guard.py -q` → pass (파서 회귀 0)
- [x] `pytest tests/contract/test_schemas.py -q` → pass
- [x] `pytest tests/unit/test_total_scrap_should_run_consumer.py -q` → pass
- [x] W4-B sandbox smoke: full 파일 1개 생성, `is_merged_thread` 동작 확인, 레포 루트 무변경
- [x] `python -c "import thread_scrap_single; import inspect; assert 'playwright' not in inspect.getsource(thread_scrap_single)"` → `playwright` 미포함
- [x] `rg -n "asyncio|playwright" thread_scrap_single.py` → 0건
- [x] `python total_scrap.py --mode update` 통합 실행 및 산출물 확인
- [x] `cp` 스킬로 관심사별 커밋 분리 완료

## 참고 자료

| 출처 | 용도 |
|---|---|
| `D:\vibe-coding\scrap_sns\docs\superpowers\plans\20260418_01_twitter-cli-consumer-전환계획.md` | 동일 DI 패턴 선행 사례 |
| `D:\vibe-coding\scrap_sns\utils\twitter_cli_adapter.py` | 어댑터 인터페이스 템플릿 |
| `D:\vibe-coding\scrap_sns\twitter_scrap_single.py` | `main()` DI 시그니처 템플릿 |
| `D:\vibe-coding\scrap_sns\utils\threads_parser.py` | 재사용 파서(변경 금지) |
| `D:\vibe-coding\scrap_sns\thread_scrap_single.py` | 전환 대상 |
| `D:\vibe-coding\scrap_sns\auth\auth_threads.json` | Playwright storage_state → 쿠키 추출 입력 |
| `tests/fixtures/threads_sample.html` | 파서 단위 테스트 fixture(재사용 후보) |
