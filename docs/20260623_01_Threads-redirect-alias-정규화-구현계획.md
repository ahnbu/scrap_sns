---
title: Threads Redirect Alias Normalization Implementation Plan
created: 2026-06-23 11:58
session_id: codex:019ef22e-a6c4-7a82-8510-685235863bce
session_path: C:/Users/ahnbu/.codex/sessions/2026/06/23/rollout-2026-06-23T10-53-28-019ef22e-a6c4-7a82-8510-685235863bce.jsonl
ai: codex
tags:
  - implementation-plan
  - threads
---

# Threads Redirect Alias Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Threads simple 목록 URL이 다른 canonical 게시글로 이동할 때, alias 후보를 별도 웹 카드로 만들지 않고 canonical 게시글에 연결한다.

**Architecture:** `thread_scrap_single.py`의 상세 수집 경계에서 requested URL/code/user와 final URL/code/user를 비교한다. redirect 또는 code/user mismatch가 있으면 canonical 기준으로 저장하고, 기존 canonical이 있으면 alias 상태만 기록해 full/total 카드 생성을 막는다. 과거 전체 데이터는 자동 정리하지 않고, 확인된 `DYk4nq4ExZn -> DYizvvNE_Kf` 1건만 별도 정리 대상으로 둔다.

**Tech Stack:** Python, requests, pytest, existing JSON full/simple files, existing `utils/query-sns.mjs`.

---

## 범위

### 포함

- 신규 Threads 상세 수집에서 redirect/final URL 정보를 보존한다.
- requested code/user와 extracted code/user 불일치를 감지한다.
- canonical 글이 이미 존재하면 alias 후보를 새 카드로 만들지 않는다.
- redirect/mismatch 케이스만 추적 로그 또는 alias 상태로 남긴다.
- 이번 문제 케이스 `DYk4nq4ExZn -> DYizvvNE_Kf`를 검증 케이스로 사용한다.

### 제외

- 기존 simple/full 전체 자동 정리.
- `root_code != code` 58건 일괄 수정.
- 이미지 다운로드/hash 구조 변경.
- 웹 UI 구조 변경.
- 과거 전체 마이그레이션.

## 파일 구조

- Modify: `utils/threads_http_adapter.py`
  - `ThreadsFetchResult`에 requested/final URL과 redirect chain 메타를 추가한다.
- Modify: `thread_scrap_single.py`
  - 상세 수집 결과의 canonical code/user를 판정한다.
  - alias 상태 기록 및 canonical 중복 차단을 담당한다.
  - canonical 중복으로 판정된 simple 후보가 다음 실행에서 재import되지 않도록 한다.
- Modify: `total_scrap.py`
  - alias/duplicate 상태 글이 `output_total` 카드로 나가지 않도록 필터링한다.
- Modify: `utils/post_schema.py`
  - 필요 시 새 메타 필드의 출력 순서만 안정화한다.
- Test: `tests/unit/test_threads_http_adapter.py`
  - redirect chain 메타 반환을 검증한다.
- Create: `tests/unit/test_thread_scrap_single_redirect_alias.py`
  - redirect alias와 canonical 중복 처리 단위 테스트를 둔다.
- Test: `tests/unit/test_total_scrap_orchestration.py` 또는 신규 `tests/unit/test_total_scrap_redirect_alias.py`
  - alias 상태 글이 total 결과에서 제외되는지 검증한다.

## 상태 모델

| 필드 | 의미 | 예시 |
|---|---|---|
| `detail_status` | 후보 URL의 상세 처리 상태 | `collected`, `redirected`, `duplicate_of_canonical`, `failed` |
| `requested_url` | simple/network에서 발견한 원래 URL | `https://www.threads.com/@oatplat_/post/DYk4nq4ExZn` |
| `final_url` | 상세 요청 후 최종 도착 URL | `https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf` |
| `canonical_code` | 실제 저장 기준 게시글 code | `DYizvvNE_Kf` |
| `canonical_username` | 실제 저장 기준 username | `tonyahn_80` |
| `duplicate_of` | 이미 존재하는 canonical 글 code | `DYizvvNE_Kf` |

## 영구 데이터 영향

- 직접 영향: 새로 생성되는 `output_threads/threads_py_simple_*.json`, `output_threads/threads_py_full_*.json`, `output_total/total_full_*.json`
- 기존 이력 파일: 기본 구현에서는 자동 수정하지 않는다.
- 기존 문제 데이터 처리: 구현 완료 후 별도 승인 시에만 대상 alias 1건을 보정한다.
- 재처리 기준: 이후 수집부터 redirect alias 후보는 `detail_status`, `final_url`, `canonical_code`, `duplicate_of`로 추적된다.
- 뷰어 기준: `duplicate_of_canonical` 상태의 alias는 새 카드로 보이지 않는 것이 정상이다.

## 처리 규칙

| 조건 | 결과 |
|---|---|
| `requested_url == final_url` 그리고 `requested_code == extracted_code` | 기존처럼 `detail_status=collected` |
| `requested_url != final_url` 또는 `requested_code != extracted_code` | redirect/mismatch로 판정 |
| redirect/mismatch이고 canonical이 기존 full에 없음 | canonical 글을 저장하고 후보는 `detail_status=redirected` |
| redirect/mismatch이고 canonical이 기존 full에 있음 | 새 카드 생성 금지, 후보는 `detail_status=duplicate_of_canonical` |
| 추출 실패 | `detail_status=failed`, 완료 처리 금지 |

## Task 1: Redirect 메타 보존

**Files:**
- Modify: `utils/threads_http_adapter.py`
- Test: `tests/unit/test_threads_http_adapter.py`

- [x] **Step 1: 실패 테스트 작성**

`tests/unit/test_threads_http_adapter.py`에 redirect chain을 검증하는 테스트를 추가한다.

```python
def test_fetch_thread_html_records_redirect_metadata():
    class Response:
        status_code = 200
        text = "<html>ok</html>"
        url = "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
        history = [
            type(
                "History",
                (),
                {
                    "status_code": 301,
                    "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                    "headers": {
                        "location": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
                    },
                },
            )()
        ]

    def runner(url, cookies, headers, timeout, allow_redirects):
        assert allow_redirects is True
        return Response()

    result = fetch_thread_html(
        "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
        cookies={"sessionid": "ok"},
        headers={},
        runner=runner,
    )

    assert result.requested_url == "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn"
    assert result.final_url == "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
    assert result.redirect_chain == [
        {
            "status_code": 301,
            "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
            "location": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
        }
    ]
```

- [x] **Step 2: 실패 확인**

Run:

```powershell
pytest tests/unit/test_threads_http_adapter.py::test_fetch_thread_html_records_redirect_metadata -q
```

Expected: `AttributeError` 또는 assertion failure로 실패한다.

- [x] **Step 3: 최소 구현**

`ThreadsFetchResult`에 필드를 추가하고, `fetch_thread_html()`에서 `response.url`과 `response.history`를 기록한다.

```python
@dataclass(frozen=True)
class ThreadsFetchResult:
    html: str
    status_code: int
    requested_url: str = ""
    final_url: str = ""
    redirect_chain: list[dict] | None = None
```

반환부는 아래 형태가 된다.

```python
redirect_chain = [
    {
        "status_code": item.status_code,
        "url": item.url,
        "location": item.headers.get("location"),
    }
    for item in response.history
]
return ThreadsFetchResult(
    html=response.text,
    status_code=response.status_code,
    requested_url=url,
    final_url=response.url,
    redirect_chain=redirect_chain,
)
```

- [x] **Step 4: 통과 확인**

Run:

```powershell
pytest tests/unit/test_threads_http_adapter.py -q
```

Expected: 기존 테스트와 신규 테스트가 모두 통과한다.

## Task 2: Redirect Alias 판정

**Files:**
- Modify: `thread_scrap_single.py`
- Create: `tests/unit/test_thread_scrap_single_redirect_alias.py`

- [x] **Step 1: 실패 테스트 작성**

파서용 fake HTML 대신 redirect 판정 helper를 직접 검증한다. HTML 파싱은 기존 `tests/unit/test_threads_parser.py`의 책임으로 유지한다.

```python
from utils.threads_http_adapter import ThreadsFetchResult
from thread_scrap_single import _apply_redirect_metadata


def test_apply_redirect_metadata_marks_redirect_alias_to_canonical():
    result = ThreadsFetchResult(
        html="<html></html>",
        status_code=200,
        requested_url="https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
        final_url="https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
        redirect_chain=[
            {
                "status_code": 301,
                "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                "location": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
            }
        ],
    )

    items = _apply_redirect_metadata(
        [
            {
                "code": "DYizvvNE_Kf",
                "username": "tonyahn_80",
                "display_name": "AI컨설턴트 안재윤",
                "full_text": "canonical text",
            }
        ],
        result,
        requested_code="DYk4nq4ExZn",
        requested_username="oatplat_",
    )

    assert items[0]["code"] == "DYizvvNE_Kf"
    assert items[0]["username"] == "tonyahn_80"
    assert items[0]["detail_status"] == "redirected"
    assert items[0]["requested_url"] == "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn"
    assert items[0]["final_url"] == "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
    assert items[0]["canonical_code"] == "DYizvvNE_Kf"
    assert items[0]["canonical_username"] == "tonyahn_80"
```

- [x] **Step 2: 실패 확인**

Run:

```powershell
pytest tests/unit/test_thread_scrap_single_redirect_alias.py -q
```

Expected: `detail_status` 등 신규 필드가 없어 실패한다.

- [x] **Step 3: 최소 구현**

`collect_one()`에서 fetch 결과 메타와 첫 추출 item을 비교한다.

```python
def _apply_redirect_metadata(items, result, requested_code, requested_username):
    if not items:
        return items
    first = items[0]
    final_url = getattr(result, "final_url", "") or ""
    requested_url = getattr(result, "requested_url", "") or ""
    redirected = bool(final_url and requested_url and final_url != requested_url)
    code_mismatch = first.get("code") != requested_code
    user_mismatch = first.get("username") != requested_username

    if not redirected and not code_mismatch and not user_mismatch:
        for item in items:
            item["detail_status"] = item.get("detail_status") or "collected"
        return items

    for item in items:
        item["detail_status"] = "redirected"
        item["requested_url"] = requested_url
        item["final_url"] = final_url
        item["canonical_code"] = first.get("code")
        item["canonical_username"] = first.get("username")
    return items
```

`collect_one()`에서 `extract_items_multi_path()` 직후 위 함수를 호출한다.

- [x] **Step 4: 통과 확인**

Run:

```powershell
pytest tests/unit/test_thread_scrap_single_redirect_alias.py -q
```

Expected: PASS.

## Task 3: Canonical 중복이면 새 카드 생성 방지

**Files:**
- Modify: `thread_scrap_single.py`
- Test: `tests/unit/test_thread_scrap_single_redirect_alias.py`

- [x] **Step 1: 실패 테스트 작성**

`promote_to_full_history()`가 redirect 결과의 canonical code가 이미 full에 있으면 alias simple 자리를 새 카드로 만들지 않는지 검증한다.

```python
import json
from pathlib import Path

from thread_scrap_single import promote_to_full_history


def test_promote_redirect_alias_does_not_create_duplicate_canonical_card(tmp_path):
    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    full_path = output_dir / "threads_py_full_20260623.json"
    full_path.write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "total_count": 2, "max_sequence_id": 933},
                "posts": [
                    {
                        "sequence_id": 933,
                        "platform_id": "DYk4nq4ExZn",
                        "code": "DYk4nq4ExZn",
                        "username": "oatplat_",
                        "display_name": "오트플랫 |",
                        "full_text": "",
                        "media": ["https://example.com/alias.jpg"],
                        "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn",
                        "sns_platform": "threads",
                        "source": "network",
                        "is_detail_collected": False,
                    },
                    {
                        "sequence_id": 922,
                        "platform_id": "DYizvvNE_Kf",
                        "code": "DYizvvNE_Kf",
                        "username": "tonyahn_80",
                        "display_name": "AI컨설턴트 안재윤",
                        "full_text": "existing canonical",
                        "media": ["https://example.com/canonical.jpg"],
                        "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                        "sns_platform": "threads",
                        "source": "consumer_detail",
                        "is_detail_collected": True,
                    },
                ],
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8-sig",
    )

    promote_to_full_history(
        {
            "DYk4nq4ExZn": [
                {
                    "platform_id": "DYizvvNE_Kf",
                    "code": "DYizvvNE_Kf",
                    "username": "tonyahn_80",
                    "display_name": "AI컨설턴트 안재윤",
                    "full_text": "redirected canonical",
                    "media": ["https://example.com/canonical.jpg"],
                    "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf",
                    "sns_platform": "threads",
                    "root_code": "DYk4nq4ExZn",
                    "detail_status": "redirected",
                    "canonical_code": "DYizvvNE_Kf",
                    "duplicate_of": "DYizvvNE_Kf",
                    "source": "consumer_detail",
                    "taken_at": 1779244470,
                }
            ]
        },
        output_dir=str(output_dir),
    )

    saved = json.loads(full_path.read_text(encoding="utf-8-sig"))
    codes = [post["code"] for post in saved["posts"]]

    assert codes.count("DYizvvNE_Kf") == 1
    assert "DYk4nq4ExZn" not in codes
```

- [x] **Step 2: 실패 확인**

Run:

```powershell
pytest tests/unit/test_thread_scrap_single_redirect_alias.py::test_promote_redirect_alias_does_not_create_duplicate_canonical_card -q
```

Expected: 현재 구현은 alias/canonical 중복을 구분하지 못해 실패한다.

- [x] **Step 3: 최소 구현**

`promote_to_full_history()`에서 `merge_map` 적용 전에 기존 canonical code 집합과 alias 업데이트 목록을 만든다. alias가 canonical보다 먼저 저장된 파일 순서도 처리하기 위해 한 번에 `new_posts`에서 찾는 방식은 쓰지 않는다.

```python
existing_codes = {
    post.get("code") or post.get("platform_id")
    for post in posts
    if post.get("code") or post.get("platform_id")
}
alias_updates_by_code = {}
```

redirected item의 canonical code가 기존에 있으면 alias post를 새 글로 남기지 않고, canonical code에 붙일 alias 정보를 따로 모은다.

```python
canonical_code = merged_data.get("canonical_code") or merged_data.get("code")
is_redirect_alias = merged_data.get("detail_status") == "redirected"
is_existing_canonical = canonical_code in existing_codes and canonical_code != code

if is_redirect_alias and is_existing_canonical:
    alias_updates_by_code.setdefault(canonical_code, []).append({
        "code": code,
        "url": post.get("url"),
        "username": post.get("username"),
    })
    post["detail_status"] = "duplicate_of_canonical"
    post["duplicate_of"] = canonical_code
    updated_count += 1
    continue
```

`new_posts` 구성 후 canonical 글에 alias 정보를 붙인다.

```python
for post in new_posts:
    code = post.get("code") or post.get("platform_id")
    if code in alias_updates_by_code:
        aliases = post.setdefault("redirect_aliases", [])
        for alias in alias_updates_by_code[code]:
            if alias not in aliases:
                aliases.append(alias)
```

canonical 중복이 확인되면 해당 simple 후보에도 `detail_status="duplicate_of_canonical"`과 `duplicate_of`를 저장한다. `import_from_simple_database()`는 이 상태의 후보를 새 full 후보로 가져오지 않는다.

- [x] **Step 4: 통과 확인**

Run:

```powershell
pytest tests/unit/test_thread_scrap_single_redirect_alias.py -q
```

Expected: PASS.

## Task 4: Total 병합에서 Alias 카드 제외

**Files:**
- Modify: `total_scrap.py`
- Create: `tests/unit/test_total_scrap_redirect_alias.py`

- [x] **Step 1: 실패 테스트 작성**

```python
from total_scrap import merge_results


def test_merge_results_excludes_duplicate_of_canonical_threads(tmp_path, monkeypatch):
    threads_dir = tmp_path / "output_threads" / "python"
    threads_dir.mkdir(parents=True)
    (threads_dir / "threads_py_full_20260623.json").write_text(
        """
        {
          "metadata": {"total_count": 2},
          "posts": [
            {
              "platform_id": "DYk4nq4ExZn",
              "code": "DYk4nq4ExZn",
              "username": "oatplat_",
              "sns_platform": "threads",
              "detail_status": "duplicate_of_canonical",
              "duplicate_of": "DYizvvNE_Kf",
              "url": "https://www.threads.com/@oatplat_/post/DYk4nq4ExZn"
            },
            {
              "platform_id": "DYizvvNE_Kf",
              "code": "DYizvvNE_Kf",
              "username": "tonyahn_80",
              "sns_platform": "threads",
              "full_text": "canonical",
              "url": "https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf"
            }
          ]
        }
        """,
        encoding="utf-8-sig",
    )

    monkeypatch.setattr("total_scrap.OUTPUT_THREADS_DIR", str(threads_dir))
    monkeypatch.setattr("total_scrap.OUTPUT_LINKEDIN_DIR", str(tmp_path / "linkedin"))
    monkeypatch.setattr("total_scrap.OUTPUT_TWITTER_DIR", str(tmp_path / "twitter"))

    posts, threads_count, linkedin_count, twitter_count = merge_results()

    assert threads_count == 1
    assert [post["code"] for post in posts] == ["DYizvvNE_Kf"]
```

- [x] **Step 2: 실패 확인**

Run:

```powershell
pytest tests/unit/test_total_scrap_redirect_alias.py -q
```

Expected: alias 글이 포함되어 실패한다.

- [x] **Step 3: 최소 구현**

`merge_results()`에서 platform별 posts를 합치기 전에 alias 상태를 제외한다.

```python
def is_visible_post(post):
    return post.get("detail_status") not in {"duplicate_of_canonical"}

threads_posts = [post for post in threads_posts if is_visible_post(post)]
```

- [x] **Step 4: 통과 확인**

Run:

```powershell
pytest tests/unit/test_total_scrap_redirect_alias.py -q
```

Expected: PASS.

## Task 5: 이번 케이스 타깃 정리 Dry Run

**Files:**
- Create: `scripts/diagnose_threads_redirect_alias.mjs`

- [x] **Step 1: dry-run 스크립트 작성**

스크립트는 실제 파일을 수정하지 않고 아래를 출력한다.

```markdown
alias_code=DYk4nq4ExZn
alias_url=https://www.threads.com/@oatplat_/post/DYk4nq4ExZn
canonical_code=DYizvvNE_Kf
canonical_url=https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf
action=remove_alias_card_from_total_and_link_to_canonical
```

- [x] **Step 2: dry-run 실행**

Run:

```powershell
node scripts/diagnose_threads_redirect_alias.mjs DYk4nq4ExZn
```

Expected: 위 케이스가 감지되고 파일 수정이 없어야 한다.

- [x] **Step 3: 실제 데이터 수정은 별도 승인 후 진행**

이번 계획의 기본 실행에서는 기존 전체 데이터 자동 수정은 하지 않는다. `DYk4nq4ExZn` 한 건 정리는 사용자가 별도 승인한 뒤 수행한다.

## 최종 검증

- [x] **단위 테스트**

Run:

```powershell
pytest tests/unit/test_threads_http_adapter.py tests/unit/test_threads_parser.py tests/unit/test_thread_scrap_single_redirect_alias.py tests/unit/test_total_scrap_redirect_alias.py -q
```

Expected: 모두 PASS.

- [x] **CLI 확인**

Run:

```powershell
node utils/query-sns.mjs get DYk4nq4ExZn --format json
node utils/query-sns.mjs get DYizvvNE_Kf --format json
```

Expected after targeted cleanup approval:

- `DYk4nq4ExZn`는 웹 카드로 조회되지 않거나 alias 상태로만 조회된다.
- `DYizvvNE_Kf`는 정상 조회된다.

- [x] **데이터 확인**

Run:

```powershell
python -c "import json; posts=json.load(open('output_total/total_full_20260623.json', encoding='utf-8-sig'))['posts']; print([p['code'] for p in posts if p.get('code') in ('DYk4nq4ExZn','DYizvvNE_Kf')])"
```

Expected after targeted cleanup approval:

```markdown
['DYizvvNE_Kf']
```

## 완료 기준

- 신규 redirect alias가 full/total에 별도 깨진 카드로 생성되지 않는다.
- redirect/mismatch 발생 시 final URL, canonical code, canonical username 추적 정보가 남는다.
- 기존 정상 Threads 수집 테스트가 통과한다.
- 이번 케이스는 사용자 승인 후 별도 정리할 수 있는 dry-run 근거가 있다.

## 자체 검수

- Spec coverage: redirect 감지, canonical 중복 방지, alias 카드 제외, 이번 케이스 dry-run을 모두 포함했다.
- Scope control: 기존 전체 데이터 자동 정리, 이미지 구조 변경, UI 변경은 제외했다.
- Risk: `root_code != code`인 정상 merged thread를 오탐하지 않도록 redirect/final URL 근거가 있는 케이스만 처리한다.
- Persistence: simple 후보 재import 차단과 영구 JSON 영향 범위를 명시했다.
- Executability: 테스트 상수명과 검증 명령은 현재 코드와 Windows PowerShell 기준으로 맞췄다.

## 실행 결과

실행일: 2026-06-23 KST

### 구현 완료

- `utils/threads_http_adapter.py`
  - `ThreadsFetchResult`에 `requested_url`, `final_url`, `redirect_chain`을 추가했다.
  - `fetch_thread_html()`이 `response.history`와 최종 URL을 보존한다.
- `thread_scrap_single.py`
  - `_apply_redirect_metadata()`를 추가해 requested/final code/user mismatch를 `detail_status=redirected`로 기록한다.
  - canonical이 이미 full에 있으면 alias 카드를 제거하고 canonical 글의 `redirect_aliases`에 연결한다.
  - simple 후보에 `detail_status=duplicate_of_canonical`, `duplicate_of`, canonical 메타를 남겨 재import를 차단한다.
  - `import_from_simple_database()`가 `duplicate_of_canonical` 후보를 건너뛴다.
- `total_scrap.py`
  - `merge_results()`가 `detail_status=duplicate_of_canonical`인 Threads 글을 total 카드에서 제외한다.
- `scripts/diagnose_threads_redirect_alias.mjs`
  - 기존 JSON을 수정하지 않는 dry-run 진단 스크립트를 추가했다.
- `.gitignore`
  - `scripts/*` ignore 규칙 때문에 dry-run 스크립트가 누락되지 않도록 해당 파일만 예외 처리했다.
- 테스트
  - `tests/unit/test_threads_http_adapter.py`에 redirect 메타 테스트를 추가했다.
  - `tests/unit/test_thread_scrap_single_redirect_alias.py`를 추가했다.
  - `tests/unit/test_total_scrap_redirect_alias.py`를 추가했다.

### 검증 결과

| 검증 | 명령 | 결과 |
|---|---|---|
| Redirect 메타 | `pytest tests/unit/test_threads_http_adapter.py -q` | PASS, 9 passed |
| Redirect alias 처리 | `pytest tests/unit/test_thread_scrap_single_redirect_alias.py -q` | PASS, 3 passed |
| Total alias 제외 | `pytest tests/unit/test_total_scrap_redirect_alias.py -q` | PASS, 1 passed |
| 계획서 지정 묶음 | `pytest tests/unit/test_threads_http_adapter.py tests/unit/test_threads_parser.py tests/unit/test_thread_scrap_single_redirect_alias.py tests/unit/test_total_scrap_redirect_alias.py -q` | PASS, 16 passed |
| Unit 전체 | `pytest tests/unit -q` | PASS, 127 passed |
| Dry run | `node scripts/diagnose_threads_redirect_alias.mjs DYk4nq4ExZn` | alias/canonical 감지 성공 |

### Dry Run 출력

```markdown
alias_code=DYk4nq4ExZn
alias_url=https://www.threads.com/@oatplat_/post/DYk4nq4ExZn
canonical_code=DYizvvNE_Kf
canonical_url=https://www.threads.com/@tonyahn_80/post/DYizvvNE_Kf
action=remove_alias_card_from_total_and_link_to_canonical
source_file=D:\vibe-coding\scrap_sns\output_total\total_full_20260623.json
```

### 현재 데이터 상태

기존 데이터 보정은 계획 범위에서 제외했으므로 아직 실행하지 않았다.

| 확인 | 결과 |
|---|---|
| `node utils/query-sns.mjs get DYk4nq4ExZn --format json` | 현재 기존 total 데이터에서 조회됨 |
| `node utils/query-sns.mjs get DYizvvNE_Kf --format json` | 현재 기존 total 데이터에서 조회됨 |
| `python -c "..."` 대상 코드 확인 | `['DYk4nq4ExZn', 'DYizvvNE_Kf']` |

결론: 재발 방지 로직은 구현 및 검증 완료. 기존 `2026-06-23` total 데이터의 alias 카드 보정은 별도 승인 후 진행해야 한다.
