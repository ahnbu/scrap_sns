---
title: "X Detail Collector twitter-cli Cutover Implementation Plan"
created: "2026-04-18 14:41"
tags:
  - plan
  - twitter-cli
  - x
session_id: codex:019d9efb-e85f-7b82-bb66-7ae7de823056
session_path: C:/Users/ahnbu/.codex/sessions/2026/04/18/rollout-2026-04-18T14-06-42-019d9efb-e85f-7b82-bb66-7ae7de823056.jsonl
ai: codex
status: draft
---

# X Detail Collector twitter-cli Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `twitter_scrap_single.py`를 browserless `twitter-cli` 기반 consumer로 전환하면서 기존 persistence 파일과 실패 관리 흐름은 유지한다.

**Architecture:** `twitter_scrap_single.py`는 대상 선정·파일 저장·실패 카운트 관리만 담당하고, 새 `utils/twitter_cli_adapter.py`가 쿠키 토큰 로드, `twitter tweet --json` 실행, focal tweet 정규화를 맡는다. `twitter-cli` structured output에는 parent-reply 메타데이터가 없으므로 이번 cutover는 `data[0]`의 focal tweet만 저장하고 self-thread 병합은 의도적으로 제외한다. 사진은 기존처럼 `wsrv` URL로 저장하고, video/animated media는 raw URL을 저장한다. `web_viewer/script.js`는 이미 `.mp4`를 video post로 처리하므로 viewer 코드는 바꾸지 않는다.

**Tech Stack:** Python 3.13, `subprocess`, `pytest`, `twitter-cli`, PowerShell

---

## Scope Lock

- In scope: `twitter_scrap_single.py` consumer cutover, isolated fixtures/tests, 운영 문서 업데이트.
- Out of scope: `twitter_scrap.py` producer 변경, `utils/twitter_parser.py` 삭제, self-thread parity 구현, 기존 full 데이터 backfill.
- Accepted behavior change 1: 새로 상세 수집되는 X post는 focal tweet만 `full_text`에 저장한다.
- Accepted behavior change 2: 새로 상세 수집되는 video post는 thumbnail JPG 대신 raw `.mp4` URL을 저장한다.
- Stop condition: same-author reply chain parity가 이번 배포의 필수 요구사항으로 바뀌면 이 plan을 실행하지 말고 별도 raw GraphQL parsing plan을 먼저 작성한다.

## File Structure

- Create: `utils/twitter_cli_adapter.py` — token loading, CLI execution, focal tweet normalization.
- Create: `tests/unit/test_twitter_cli_adapter.py` — token/media/payload unit tests.
- Create: `tests/integration/test_twitter_scrap_single_cli.py` — temp-copy integration test.
- Create: `tests/fixtures/twitter_cli/notebooklm.json`
- Create: `tests/fixtures/twitter_cli/toppingtest.json`
- Create: `tests/fixtures/twitter_cli/aakashgupta.json`
- Modify: `twitter_scrap_single.py` — Playwright 제거, adapter 주입, temp-path-friendly `main()`.
- Modify: `README.md` — X auth 역할 분리 문서화.
- Modify: `docs/development.md` — X consumer source, media rule, legacy parser 역할 정리.
- Modify: `docs/crawling_logic.md` — X consumer 단계 설명을 `twitter-cli` 기준으로 현행화.
- Modify: `CHANGELOG.md`
- No change: `utils/twitter_parser.py`, `tests/unit/test_twitter_parser.py`, `tests/integration/test_parser_integration.py`.

## Persistence Surface And Migration Decision

### Affected surfaces

- `output_twitter/python/twitter_py_simple_*.json` — `is_detail_collected`, `username`, `url`, `full_text`, `media`, `source`가 갱신된다.
- `output_twitter/python/twitter_py_full_*.json` — simple 승격 결과를 저장한다.
- `scrap_failures_twitter.json` — 기존 카운트 스키마를 그대로 쓴다.
- `output_total/total_full_*.json` — 다음 `total_scrap.py --mode update`부터 새 X 상세 결과를 병합한다.
- `web_viewer/data.js` — 다음 `python -m utils.build_data_js`부터 새 X 상세 결과를 반영한다.

### Migration decision

- Existing data migration: 하지 않는다.
- Reason 1: 필드 스키마와 파일 패턴이 바뀌지 않는다.
- Reason 2: viewer는 기존 image URL과 새 `.mp4` URL을 모두 렌더링할 수 있다.
- Reason 3: 기존 merged-thread row는 historical snapshot으로 유지하고, 이번 cutover는 future writes만 바꾼다.

### Post-cutover commands

- Refresh merged data: `python total_scrap.py --mode update`
- Refresh viewer cache: `python -m utils.build_data_js`

### Verification commands

- Unit: `pytest tests/unit/test_twitter_cli_adapter.py -q`
- Integration: `pytest tests/integration/test_twitter_scrap_single_cli.py -q`
- Regression: `pytest tests/unit/test_twitter_parser.py tests/integration/test_parser_integration.py -q`
- Contract: `pytest tests/contract/test_schemas.py -q`

## Task 1: Add Stable CLI Fixtures And Adapter Unit Tests

**Files:**
- Create: `tests/fixtures/twitter_cli/notebooklm.json`
- Create: `tests/fixtures/twitter_cli/toppingtest.json`
- Create: `tests/fixtures/twitter_cli/aakashgupta.json`
- Create: `tests/unit/test_twitter_cli_adapter.py`
- Create: `utils/twitter_cli_adapter.py`

- [ ] **Step 1: Promote the existing CLI captures into test fixtures**

Run:

```powershell
New-Item -ItemType Directory -Path tests/fixtures/twitter_cli -Force | Out-Null
Copy-Item tmp/twitter_cli_test/test1_notebooklm.json tests/fixtures/twitter_cli/notebooklm.json
Copy-Item tmp/twitter_cli_test/test2_toppingtest.json tests/fixtures/twitter_cli/toppingtest.json
Copy-Item tmp/twitter_cli_test/test3_aakashgupta.json tests/fixtures/twitter_cli/aakashgupta.json
```

Expected: `tests/fixtures/twitter_cli/` 아래에 3개 JSON fixture가 생긴다.

- [ ] **Step 2: Write the failing adapter tests**

Create `tests/unit/test_twitter_cli_adapter.py`:

```python
import json
from pathlib import Path

from utils.twitter_cli_adapter import (
    TwitterCliDetail,
    build_twitter_cli_env,
    load_twitter_tokens,
    parse_twitter_cli_payload,
)


def _load_fixture(name):
    fixture_path = Path("tests/fixtures/twitter_cli") / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _write_cookie_file(path, auth_token, ct0):
    path.write_text(
        json.dumps(
            [
                {"name": "auth_token", "value": auth_token},
                {"name": "ct0", "value": ct0},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_load_twitter_tokens_reads_latest_cookie_file(tmp_path):
    older = tmp_path / "x_cookies_20260417_090000.json"
    newer = tmp_path / "x_cookies_20260418_090000.json"
    _write_cookie_file(older, auth_token="old-token", ct0="old-ct0")
    _write_cookie_file(newer, auth_token="new-token", ct0="new-ct0")

    assert load_twitter_tokens(auth_dir=tmp_path) == {
        "auth_token": "new-token",
        "ct0": "new-ct0",
    }


def test_build_twitter_cli_env_injects_expected_keys():
    env = build_twitter_cli_env({"PATH": "ok"}, {"auth_token": "aaa", "ct0": "bbb"})

    assert env["PATH"] == "ok"
    assert env["TWITTER_AUTH_TOKEN"] == "aaa"
    assert env["TWITTER_CT0"] == "bbb"


def test_parse_twitter_cli_payload_wraps_photo_urls():
    payload = _load_fixture("toppingtest.json")

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text=payload["data"][0]["text"],
        media=[
            "https://wsrv.nl/?url=https://pbs.twimg.com/media/HEsTPr6akAAiitk.jpg",
            "https://wsrv.nl/?url=https://pbs.twimg.com/media/HEsTa9FbUAA_sck.jpg",
        ],
        real_user="toppingtest",
    )


def test_parse_twitter_cli_payload_keeps_only_focal_tweet_and_raw_video_url():
    payload = _load_fixture("aakashgupta.json")

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text=payload["data"][0]["text"],
        media=[
            "https://video.twimg.com/amplify_video/2038710244122251264/vid/avc1/1280x720/ODmFcZfpQj1AO5g8.mp4?tag=21",
        ],
        real_user="aakashgupta",
    )
    assert "@carlvellotti" not in detail.full_text
```

- [ ] **Step 3: Run the tests and verify they fail for the right reason**

Run: `pytest tests/unit/test_twitter_cli_adapter.py -q`

Expected: collection error with `ModuleNotFoundError: No module named 'utils.twitter_cli_adapter'`.

- [ ] **Step 4: Implement the adapter module**

Create `utils/twitter_cli_adapter.py`:

```python
from __future__ import annotations

import glob
import json
import os
import subprocess
from dataclasses import dataclass

WSRV_PREFIX = "https://wsrv.nl/?url="


@dataclass(frozen=True)
class TwitterCliDetail:
    full_text: str
    media: list[str]
    real_user: str


def load_twitter_tokens(auth_dir="auth"):
    pattern = os.path.join(str(auth_dir), "x_cookies_*.json")
    cookie_files = sorted(glob.glob(pattern), reverse=True)
    if not cookie_files:
        return None

    with open(cookie_files[0], "r", encoding="utf-8") as file:
        cookies = json.load(file)

    values = {
        item.get("name"): item.get("value")
        for item in cookies
        if item.get("name") in {"auth_token", "ct0"}
    }
    if not values.get("auth_token") or not values.get("ct0"):
        return None

    return {
        "auth_token": values["auth_token"],
        "ct0": values["ct0"],
    }


def build_twitter_cli_env(base_env, tokens):
    env = dict(base_env)
    env["TWITTER_AUTH_TOKEN"] = tokens["auth_token"]
    env["TWITTER_CT0"] = tokens["ct0"]
    return env


def _normalize_media(media_items):
    normalized = []
    for item in media_items or []:
        url = item.get("url")
        if not url:
            continue
        if item.get("type") == "photo":
            normalized.append(f"{WSRV_PREFIX}{url}")
        else:
            normalized.append(url)
    return list(dict.fromkeys(normalized))


def parse_twitter_cli_payload(payload, fallback_user):
    if not payload.get("ok") or not payload.get("data"):
        return None

    main_tweet = payload["data"][0]
    real_user = ((main_tweet.get("author") or {}).get("screenName")) or fallback_user
    full_text = (main_tweet.get("text") or "").strip()
    media = _normalize_media(main_tweet.get("media", []))
    if not full_text and not media:
        return None

    return TwitterCliDetail(
        full_text=full_text,
        media=media,
        real_user=real_user,
    )


def fetch_tweet_detail(url, target_user, env, timeout=30, runner=subprocess.run):
    try:
        result = runner(
            ["twitter", "tweet", url, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return parse_twitter_cli_payload(payload, fallback_user=target_user)
```

- [ ] **Step 5: Run the adapter tests again and verify they pass**

Run: `pytest tests/unit/test_twitter_cli_adapter.py -q`

Expected: `4 passed`.

- [ ] **Step 6: Update the changelog row and commit this slice**

Prepend a new row to `CHANGELOG.md` using the actual current KST timestamp, `feat` type, `twitter-cli` scope, and this summary: `X consumer CLI adapter와 focal-tweet normalization 추가`.

Then commit with the `cp` skill workflow using this message:

```text
feat(twitter-cli): X consumer CLI adapter 추가
```

## Task 2: Refactor twitter_scrap_single.py To Use The Adapter And Temp Paths

**Files:**
- Modify: `twitter_scrap_single.py`
- Create: `tests/integration/test_twitter_scrap_single_cli.py`
- Test: `tests/unit/test_twitter_parser.py`
- Test: `tests/integration/test_parser_integration.py`

- [ ] **Step 1: Write the failing integration test around temp copies**

Create `tests/integration/test_twitter_scrap_single_cli.py`:

```python
import json

import twitter_scrap_single
from utils.twitter_cli_adapter import TwitterCliDetail


def test_main_writes_temp_outputs_without_touching_repo_paths(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "Unknown",
                        "url": "https://x.com/i/status/2034688795652816948",
                        "media": [],
                        "created_at": "2026-03-19 17:49:46",
                        "date": "2026-03-19",
                        "sequence_id": 79,
                        "is_detail_collected": False,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": {"auth_token": "token", "ct0": "ct0"},
        fetch_detail=lambda url, target_user, env, timeout=30: TwitterCliDetail(
            full_text="We wanted to come on here to clear the air and confirm that the rumors are true...",
            media=[],
            real_user="NotebookLM",
        ),
        sleep_fn=lambda _seconds: None,
    )

    saved_simple = json.loads(simple_file.read_text(encoding="utf-8-sig"))
    saved_post = saved_simple["posts"][0]
    assert saved_post["is_detail_collected"] is True
    assert saved_post["username"] == "NotebookLM"
    assert saved_post["url"] == "https://x.com/NotebookLM/status/2034688795652816948"
    assert saved_post["source"] == "full_tweet_cli"

    full_files = list(output_dir.glob("twitter_py_full_*.json"))
    assert len(full_files) == 1
    full_data = json.loads(full_files[0].read_text(encoding="utf-8-sig"))
    assert full_data["posts"][0]["full_text"].startswith("We wanted to come on here")

    update_files = list((output_dir / "update").glob("twitter_py_full_update_*.json"))
    assert len(update_files) == 1
    assert json.loads(failure_file.read_text(encoding="utf-8")) == {}
```

- [ ] **Step 2: Run the integration test and verify it fails before the refactor**

Run: `pytest tests/integration/test_twitter_scrap_single_cli.py -q`

Expected: `TypeError: main() got an unexpected keyword argument 'output_dir'`.

- [ ] **Step 3: Refactor the consumer to use injected paths and the CLI adapter**

Replace the top of `twitter_scrap_single.py` and the `main()` signature/body with this implementation:

```python
import json
import time
import os
import glob
import argparse
from datetime import datetime

from utils.twitter_cli_adapter import (
    build_twitter_cli_env,
    fetch_tweet_detail,
    load_twitter_tokens,
)

OUTPUT_DIR = "output_twitter/python"
SIMPLE_FILE_PATTERN = "twitter_py_simple_*.json"
FULL_FILE_PATTERN = "twitter_py_full_{date}.json"
FAILURE_FILE = "scrap_failures_twitter.json"


def clean_text(text):
    if not text:
        return ""
    return text.strip()


def load_failures(path=FAILURE_FILE):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as file:
            try:
                return json.load(file)
            except Exception:
                return {}
    return {}


def save_failures(failures, path=FAILURE_FILE):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(failures, file, ensure_ascii=False, indent=4)


def main(
    limit=0,
    output_dir=OUTPUT_DIR,
    failure_file=FAILURE_FILE,
    auth_dir="auth",
    token_loader=load_twitter_tokens,
    fetch_detail=fetch_tweet_detail,
    sleep_fn=time.sleep,
):
    failures = load_failures(failure_file)

    simple_files = glob.glob(os.path.join(output_dir, SIMPLE_FILE_PATTERN))
    if not simple_files:
        print("❌ Simple 파일을 찾을 수 없습니다.")
        return

    latest_simple = sorted(simple_files, reverse=True)[0]
    print(f"📂 목록 로드: {os.path.basename(latest_simple)}")
    with open(latest_simple, 'r', encoding='utf-8-sig') as file:
        simple_data = json.load(file)

    posts = simple_data.get('posts', [])
    targets = []
    skipped_count = 0
    for post in posts:
        pid = str(post.get('platform_id') or post.get('id'))
        if post.get('is_detail_collected'):
            continue

        fail_info = failures.get(pid, {})
        if fail_info.get('count', 0) >= 3:
            skipped_count += 1
            continue

        targets.append(post)

    if skipped_count > 0:
        print(f"⏩ [Skip] {skipped_count}개 항목 제외 (3회 이상 실패)")

    if not targets:
        print("✨ 상세 수집할 새로운 항목이 없습니다. (메타데이터 동기화만 진행)")

    updated_count = 0
    if targets:
        if limit > 0:
            print(f"🎯 테스트 모드: {limit}개만 수집합니다.")
            targets = targets[:limit]

        tokens = token_loader(auth_dir=auth_dir)
        if not tokens:
            print("❌ twitter-cli 토큰을 찾을 수 없습니다. auth/x_cookies_*.json을 확인하세요.")
            return

        env = build_twitter_cli_env(os.environ, tokens)
        total_targets = len(targets)
        print(f"🚀 총 {total_targets}개의 신규 항목 상세 수집 시작...")

        for index, post in enumerate(targets, start=1):
            pid = str(post.get('platform_id') or post.get('id'))
            url = post['url']
            user = post.get('username') or post.get('user')
            progress_percent = int((index / total_targets) * 100)
            progress_msg = f"({index}/{total_targets}, {progress_percent}%)"

            detail = fetch_detail(url, user, env=env)
            if detail:
                post['username'] = detail.real_user
                post['url'] = f"https://x.com/{detail.real_user}/status/{pid}"
                post['full_text'] = clean_text(detail.full_text)
                post['media'] = list(dict.fromkeys((post.get('media', []) or []) + detail.media))
                post['is_detail_collected'] = True
                post['source'] = 'full_tweet_cli'
                post['sns_platform'] = 'x'

                if not post.get('created_at'):
                    post['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    post['date'] = datetime.now().strftime('%Y-%m-%d')

                if pid in failures:
                    del failures[pid]
                updated_count += 1
                print(f"   ✅ 수집 완료: @{detail.real_user} {progress_msg}")
            else:
                fail_info = failures.get(pid, {"count": 0, "last_fail": ""})
                fail_info['count'] += 1
                fail_info['last_fail'] = datetime.now().isoformat()
                fail_info['url'] = url
                failures[pid] = fail_info
                print(f"   ❌ 수집 실패 ({fail_info['count']}/3): {url} {progress_msg}")

            save_failures(failures, failure_file)
            sleep_fn(3)

    today = datetime.now().strftime('%Y%m%d')
    full_file = os.path.join(output_dir, FULL_FILE_PATTERN.format(date=today))
    all_full_posts = []
    max_sequence_id = 0
    if os.path.exists(full_file):
        with open(full_file, 'r', encoding='utf-8-sig') as file:
            try:
                full_data_existing = json.load(file)
                all_full_posts = full_data_existing.get('posts', [])
                max_sequence_id = full_data_existing.get('metadata', {}).get('max_sequence_id', 0)
            except Exception:
                pass

    full_map = {str(post.get('platform_id') or post.get('id')): post for post in all_full_posts}
    for post in posts:
        if post.get('is_detail_collected'):
            pid = str(post.get('platform_id') or post.get('id'))
            if pid in full_map:
                full_map[pid].update(post)
            else:
                full_map[pid] = post
            sequence_id = post.get('sequence_id', 0)
            if sequence_id > max_sequence_id:
                max_sequence_id = sequence_id

    final_posts = sorted(full_map.values(), key=lambda item: item.get('sequence_id', 0), reverse=True)
    if final_posts:
        with open(full_file, 'w', encoding='utf-8-sig') as file:
            json.dump(
                {
                    "metadata": {
                        "updated_at": datetime.now().isoformat(),
                        "total_count": len(final_posts),
                        "max_sequence_id": max_sequence_id,
                        "platform": "x",
                    },
                    "posts": final_posts,
                },
                file,
                ensure_ascii=False,
                indent=4,
            )
        print(f"📦 최종 상세 데이터 동기화 완료: {full_file} (max_sequence_id: {max_sequence_id}, total: {len(final_posts)})")

    if updated_count > 0:
        newly_updated_posts = [post for post in targets if post.get('is_detail_collected')]
        update_dir = os.path.join(output_dir, 'update')
        os.makedirs(update_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        update_file = os.path.join(update_dir, f"twitter_py_full_update_{timestamp}.json")
        with open(update_file, 'w', encoding='utf-8-sig') as file:
            json.dump(newly_updated_posts, file, ensure_ascii=False, indent=4)
        print(f"📂 상세 수집 업데이트 저장: {update_file} ({updated_count}개)")

    with open(latest_simple, 'w', encoding='utf-8-sig') as file:
        json.dump(simple_data, file, ensure_ascii=False, indent=4)

    print(f"\n✨ 상세 수집 마감! 총 {updated_count}개 신규 갱신됨.")
```

Also remove these imports from the file:

```python
from playwright.sync_api import sync_playwright
from utils.twitter_parser import parse_twitter_html
```

- [ ] **Step 4: Run the integration test plus parser regressions**

Run:

```powershell
pytest tests/integration/test_twitter_scrap_single_cli.py tests/unit/test_twitter_parser.py tests/integration/test_parser_integration.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Update the changelog row and commit this slice**

Prepend a new row to `CHANGELOG.md` using the actual current KST timestamp, `fix` type, `twitter-single` scope, and this summary: `Playwright consumer를 twitter-cli 기반 browserless flow로 전환`.

Then commit with the `cp` skill workflow using this message:

```text
fix(twitter-single): browserless detail collection으로 전환
```

## Task 3: Update Docs And Run An Isolated Smoke Test

**Files:**
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `docs/crawling_logic.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README auth instructions**

Replace the X auth section in `README.md` with:

````md
## 인증 갱신

Threads와 LinkedIn 세션을 다시 저장할 때:

```powershell
python renew_auth.py
```

X(Twitter) 인증은 producer와 consumer가 다르게 쓴다.

- `twitter_scrap.py`: `auth/x_user_data/` persistent Chrome profile 사용
- `twitter_scrap_single.py`: `auth/x_cookies_*.json`에서 `auth_token`과 `ct0`를 읽어 `twitter-cli`에 주입

Producer Chrome 프로필을 다시 저장할 때:

```powershell
python renew_twitter_auth.py
```

persistent profile에 최신 쿠키를 재주입할 때:

```powershell
python inject_x_cookies.py
```
````

- [ ] **Step 2: Update the developer and crawling docs**

Replace the X section in `docs/development.md` with:

```md
### X(Twitter)

- 목록 수집기: `twitter_scrap.py`
- 상세 수집기: `twitter_scrap_single.py` (`twitter-cli` 기반 focal tweet collector)
- 레거시 HTML 파서: `utils/twitter_parser.py` (회귀 테스트 전용, runtime 미사용)

주요 매핑:

- `platform_id`: `rest_id`
- `full_text`: `twitter-cli data[0].text`만 저장한다. same-author reply chain은 이 단계에서 병합하지 않는다.
- `media`: `photo`는 `https://wsrv.nl/?url=...`, `video`와 `animated_gif`는 raw URL을 저장한다.
- `created_at`: 목록 수집 단계에서 채운 값을 우선 유지하고, 비어 있으면 상세 수집 시각으로 채운다.
- `url`: 기본은 `https://x.com/{username}/status/{post_id}`, 사용자명이 비어 있으면 `https://x.com/i/status/{post_id}`

상세 수집 단계에서 실제 작성자명이 확인되면 `username`과 `url`이 재보정될 수 있다.
```

Replace the X section in `docs/crawling_logic.md` with:

```md
### X(Twitter)

1. `twitter_scrap.py`가 북마크 타임라인 JSON과 HTML fallback에서 simple 목록을 만든다.
2. `twitter_scrap_single.py`가 `auth/x_cookies_*.json`에서 토큰을 읽어 `twitter tweet <url> --json`을 호출한다.
3. consumer는 focal tweet만 `full_text`, `media`, 실제 작성자명으로 보강한다.
4. 3회 이상 실패한 항목은 `scrap_failures_twitter.json`을 기준으로 잠시 제외한다.

주요 출력:

- `output_twitter/python/twitter_py_simple_YYYYMMDD.json`
- `output_twitter/python/twitter_py_full_YYYYMMDD.json`
- `scrap_failures_twitter.json`
```

- [ ] **Step 3: Verify docs and contracts**

Run:

```powershell
rg -n "twitter-cli|x_cookies_|focal tweet|full_tweet_cli" README.md docs/development.md docs/crawling_logic.md twitter_scrap_single.py
pytest tests/contract/test_schemas.py -q
```

Expected:
- `rg` 출력에 4개 파일이 모두 잡힌다.
- `pytest` 결과는 `1 passed` 이상으로 끝난다.

- [ ] **Step 4: Run a live smoke test against sandbox copies only**

Run:

```powershell
$Sandbox = Join-Path $env:TEMP 'twitter-cli-cutover-smoke'
New-Item -ItemType Directory -Path "$Sandbox\output_twitter\python" -Force | Out-Null
$Simple = Get-ChildItem output_twitter/python/twitter_py_simple_*.json | Sort-Object Name -Descending | Select-Object -First 1
Copy-Item $Simple.FullName "$Sandbox\output_twitter\python\$($Simple.Name)"
@"
import json
from pathlib import Path

simple_path = Path(r"$Sandbox\output_twitter\python\$($Simple.Name)")
data = json.loads(simple_path.read_text(encoding="utf-8-sig"))
data["posts"][0]["is_detail_collected"] = False
simple_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8-sig")
"@ | python -
@"
import twitter_scrap_single

twitter_scrap_single.main(
    limit=1,
    output_dir=r"$Sandbox\output_twitter\python",
    failure_file=r"$Sandbox\scrap_failures_twitter.json",
    auth_dir=r"auth",
    sleep_fn=lambda _seconds: None,
)
"@ | python -
Get-ChildItem "$Sandbox\output_twitter\python" -Recurse -File | Select-Object Name
```

Expected:
- sandbox 경로에 `twitter_py_full_*.json` 1개가 생성된다.
- sandbox `update/` 아래에 `twitter_py_full_update_*.json` 1개가 생성된다.
- repo 루트 `output_twitter/python` 파일은 수정되지 않는다.

- [ ] **Step 5: Update the changelog row and commit this slice**

Prepend a new row to `CHANGELOG.md` using the actual current KST timestamp, `docs` type, `twitter-cli` scope, and this summary: `consumer auth 분리와 focal-tweet 규칙 문서화`.

Then commit with the `cp` skill workflow using this message:

```text
docs(twitter-cli): consumer auth와 persistence 규칙 문서화
```

## Final Verification

Run:

```powershell
pytest tests/unit/test_twitter_cli_adapter.py tests/integration/test_twitter_scrap_single_cli.py tests/unit/test_twitter_parser.py tests/integration/test_parser_integration.py tests/contract/test_schemas.py -q
python total_scrap.py --mode update
python -m utils.build_data_js
```

Expected:
- 테스트는 모두 pass 한다.
- `total_scrap.py --mode update`에서 X consumer 구간이 `twitter-cli` 기반으로 동작하고 `📦 최종 상세 데이터 동기화 완료` 로그가 나온다.
- `web_viewer/data.js`가 최신 통합본 기준으로 다시 생성된다.

## Exit Criteria

- `twitter_scrap_single.py`가 Playwright 없이 실행된다.
- repo 테스트와 sandbox smoke가 모두 pass 한다.
- `utils/twitter_parser.py`와 기존 parser regression tests는 그대로 유지된다.
- 운영 문서가 `x_user_data`와 `x_cookies_*.json`의 역할을 분리해서 설명한다.
- 이 plan 범위 안에서는 self-thread parity를 주장하지 않는다.
