---
title: LinkedIn update 20건 연속 중단 복귀 구현계획
date: 2026-07-09 18:46
created: 2026-07-09 18:46
tags:
  - scrap_sns/linkedin
  - opencli
  - implementation-plan
session_id: codex:019f45d0-2359-7c43-a4a6-7bca3062e2c5
session_path: C:/Users/ahnbu/.codex/sessions/2026/07/09/rollout-2026-07-09T16-38-16-019f45d0-2359-7c43-a4a6-7bca3062e2c5.jsonl
ai: codex
status: plan
---

# LinkedIn update 20건 연속 중단 복귀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LinkedIn `--mode update`는 신규 저장글만 빠르게 확인하도록 기수집 ID 20건 연속 관측 시 중단하고, `--mode all`은 현재처럼 전체 저장목록 검증을 유지한다.

**Architecture:** Python `linkedin_scrap.py`는 최신 full DB에서 기존 LinkedIn ID 목록을 만들어 OpenCLI collector에 전달한다. Node `scripts/linkedin_opencli_shadow_collect.mjs`는 GraphQL page를 수집하는 즉시 activity ID 순서를 확인하고, update mode에서 기존 ID가 20건 연속 나오면 다음 page 요청 전에 종료한다. 병합은 기존 보수 병합을 유지하되, fast update에서 미관측 기존글을 삭제/누락 판정하지 않는다.

**Tech Stack:** Python 3.13, Node.js ESM `.mjs`, OpenCLI browser/network bound-session, existing `parse_shadow_raw()`, pytest, node test.

---

## 현재 코드 기준

- `linkedin_scrap.py`는 별도 세션 작업 이후 수집 전용 Chrome 창을 열고 OpenCLI를 `bind`한 뒤 collector를 실행한다.
- `linkedin_scrap.py:353-367`의 `run_opencli_collector()`는 현재 `--use-bound-session`과 `--until-exhausted`를 항상 전달한다.
- `linkedin_scrap.py:503-537`의 `LinkedinScraper.__init__()`는 최신 full 파일을 읽어 `self.existing_codes`를 이미 구성한다.
- `scripts/linkedin_opencli_shadow_collect.mjs:184-194`는 `--use-bound-session` 여부를 파싱하고, bound mode에서는 자체 browser open/close를 하지 않는다.
- `scripts/linkedin_opencli_shadow_collect.mjs:213-358`의 수집 루프가 실제 page fetch와 pagination을 담당한다. 조기 중단은 이 루프 안에 들어가야 속도 개선이 생긴다.

## 범위

포함:

- LinkedIn `--mode update`에서 기존 ID 20건 연속 관측 시 OpenCLI collector 조기 종료
- LinkedIn `--mode all`의 `--until-exhausted` 전체 확인 유지
- collector summary/metadata에 종료 사유와 fast update 진단값 기록
- update fast path에서 미관측 기존글을 삭제/누락 판정하지 않도록 metadata 의미 정리
- 관련 unit/integration test와 실제 update QA

제외:

- UI 버튼/메뉴 구조 변경
- LinkedIn parser semantics 변경
- Post schema 변경
- Threads/X 수집 변경
- `total_scrap.py` 병합 규칙 변경
- owned Chrome window lifecycle 변경
- 기존 output 파일 대량 재처리

## 데이터 surface와 마이그레이션 판단

영향받는 영구 데이터:

- `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- `output_linkedin/python/update/linkedin_python_update_YYYYMMDD_HHMMSS.json`
- `output_total/total_full_YYYYMMDD.json`

마이그레이션은 필요 없다.

근거:

- posts 배열 schema를 바꾸지 않는다.
- 기존 `sequence_id`, `platform_id`, `code`, `local_images` 의미를 바꾸지 않는다.
- 추가 metadata는 collector 실행 진단용이며, 과거 파일을 다시 쓰지 않는다.

## 동작 계약

### update mode

```markdown
python linkedin_scrap.py --mode update
-> existing_ids_file 생성
-> node scripts/linkedin_opencli_shadow_collect.mjs --use-bound-session --existing-ids-file <path> --stop-after-existing-streak 20
-> GraphQL page별 activity ID 순서 확인
-> 기존 ID 20건 연속이면 end_reason="existing_streak_20"으로 종료
-> 수집된 raw page만 parse
-> 신규 글만 update 파일에 저장
-> 기존 full DB와 보수 병합
-> 미관측 기존글은 삭제/누락 판정하지 않음
```

### all mode

```markdown
python linkedin_scrap.py --mode all
-> node scripts/linkedin_opencli_shadow_collect.mjs --use-bound-session --until-exhausted
-> 현재 저장목록 전체 확인
-> 기존 full DB와 보수 병합
```

## File Structure

- Modify: `linkedin_scrap.py`
  - `CONSECUTIVE_EXISTING_LIMIT = 20` 상수 복구
  - `run_opencli_collector()`가 mode별 collector 옵션을 구성
  - update mode에서 existing IDs JSON 파일 생성
  - update/all metadata 문구와 merge history 의미 정리
- Modify: `scripts/linkedin_opencli_shadow_collect.mjs`
  - `--existing-ids-file`, `--stop-after-existing-streak` 옵션 추가
  - 기존 ID streak 계산 helper 추가
  - page 수집 루프 안에서 조기 종료
  - summary에 종료 진단값 추가
- Modify: `tests/integration/test_linkedin_opencli_pipeline.py`
  - Python이 mode별 collector command를 올바르게 구성하는지 테스트
  - update mode에서 existing IDs 파일이 생성되는지 테스트
  - all mode가 `--until-exhausted`를 유지하는지 테스트
- Create: `tests/unit/test_linkedin_opencli_fast_stop.mjs`
  - Node streak helper 단위 테스트
  - 기존 ID 연속 20건 도달, 신규 ID reset, threshold 미달 케이스 검증
- No change: `total_scrap.py`
- No change: `web_viewer/`

---

## Task 1: Node collector fast-stop helper를 테스트로 고정

**Files:**

- Modify: `scripts/linkedin_opencli_shadow_collect.mjs`
- Create: `tests/unit/test_linkedin_opencli_fast_stop.mjs`

- [ ] **Step 1: failing node unit test 작성**

Create `tests/unit/test_linkedin_opencli_fast_stop.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";

import { applyExistingStreak } from "../../scripts/linkedin_opencli_shadow_collect.mjs";

test("applyExistingStreak reaches limit after consecutive existing IDs", () => {
  const existingIds = new Set(Array.from({ length: 25 }, (_, index) => `old-${index + 1}`));
  const orderedIds = Array.from({ length: 20 }, (_, index) => `old-${index + 1}`);

  const result = applyExistingStreak(orderedIds, existingIds, 0, 20);

  assert.deepEqual(result, { streak: 20, reached: true });
});

test("applyExistingStreak resets streak when a new ID appears", () => {
  const existingIds = new Set(["old-1", "old-2", "old-3"]);

  const result = applyExistingStreak(["old-1", "old-2", "new-1", "old-3"], existingIds, 0, 3);

  assert.deepEqual(result, { streak: 1, reached: false });
});

test("applyExistingStreak ignores duplicate IDs that were already seen by caller", () => {
  const existingIds = new Set(["old-1", "old-2"]);

  const result = applyExistingStreak(["old-1", "old-2"], existingIds, 18, 20);

  assert.deepEqual(result, { streak: 20, reached: true });
});

test("applyExistingStreak is disabled when limit is zero", () => {
  const existingIds = new Set(["old-1"]);

  const result = applyExistingStreak(["old-1"], existingIds, 0, 0);

  assert.deepEqual(result, { streak: 1, reached: false });
});
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
node --test tests/unit/test_linkedin_opencli_fast_stop.mjs
```

Expected:

```markdown
FAIL
The requested module '../../scripts/linkedin_opencli_shadow_collect.mjs' does not provide an export named 'applyExistingStreak'
```

- [ ] **Step 3: helper export와 main guard 추가**

Modify `scripts/linkedin_opencli_shadow_collect.mjs`:

기존 import는 이미 `spawnSync`, `mkdirSync`/`readFileSync`/`writeFileSync`, `join`을 포함한다(파일 상단 1-4행). `pathToFileURL`만 추가한다. 나머지는 다시 추가하지 않는다.

```javascript
import { pathToFileURL } from "node:url";
```

Add near utility helpers:

```javascript
export function applyExistingStreak(orderedIds, existingIds, currentStreak, limit) {
  let streak = currentStreak;
  let reached = false;
  for (const id of orderedIds) {
    streak = existingIds.has(id) ? streak + 1 : 0;
    if (limit > 0 && streak >= limit) {
      reached = true;
    }
  }
  return { streak, reached };
}
```

파일 하단의 실제 실행 블록은 **`import.meta` 가드가 없는** `try { main() } ... finally { ... }` 형태다(파일 끝 `try {`부터 마지막 `}`까지). 이 기존 블록 전체를 아래 가드 버전으로 교체한다. helper export(`applyExistingStreak` 등)를 test에서 import할 때 `main()`이 실행되지 않도록 가드가 필요하다.

```javascript
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  } finally {
    if (activeSession && ownsBrowserSession) {
      try {
        closeBrowserSession(activeSession);
      } catch (error) {
        console.error(`OpenCLI browser cleanup failed: ${error.message}`);
      }
    }
  }
}
```

- [ ] **Step 4: GREEN 확인**

Run:

```powershell
node --test tests/unit/test_linkedin_opencli_fast_stop.mjs
node --check scripts/linkedin_opencli_shadow_collect.mjs
```

Expected:

```markdown
4 tests pass
node --check exits 0
```

## Task 2: Node collector에 existing IDs 기반 조기 종료 추가

**Files:**

- Modify: `scripts/linkedin_opencli_shadow_collect.mjs`
- Test: `tests/unit/test_linkedin_opencli_fast_stop.mjs`

- [ ] **Step 1: existing IDs loader 테스트 추가**

Append to `tests/unit/test_linkedin_opencli_fast_stop.mjs`:

```javascript
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { loadExistingIdsFile } from "../../scripts/linkedin_opencli_shadow_collect.mjs";

test("loadExistingIdsFile reads platform IDs from JSON array", () => {
  const dir = mkdtempSync(join(tmpdir(), "linkedin-existing-"));
  const file = join(dir, "existing_ids.json");
  writeFileSync(file, `${JSON.stringify(["111", "222", "", null])}\n`, "utf8");
  try {
    const result = loadExistingIdsFile(file);
    assert.deepEqual([...result].sort(), ["111", "222"]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
node --test tests/unit/test_linkedin_opencli_fast_stop.mjs
```

Expected:

```markdown
FAIL
does not provide an export named 'loadExistingIdsFile'
```

- [ ] **Step 3: existing IDs loader 구현**

Add to `scripts/linkedin_opencli_shadow_collect.mjs`:

```javascript
export function loadExistingIdsFile(path) {
  if (!path) return new Set();
  const values = JSON.parse(readFileSync(path, "utf8"));
  if (!Array.isArray(values)) {
    throw new Error("--existing-ids-file must contain a JSON array");
  }
  return new Set(values.filter((value) => typeof value === "string" && value.length > 0));
}
```

- [ ] **Step 4: collector loop에 fast-stop 상태 추가**

In `main()` after parsing `useBoundSession`:

```javascript
const existingIds = loadExistingIdsFile(args["existing-ids-file"]);
const stopAfterExistingStreak = Number(args["stop-after-existing-streak"] || 0);
let existingStreak = 0;
let existingStreakReached = false;
```

Add a local helper inside `main()`:

```javascript
function observeIdsForFastStop(ids) {
  const freshIds = ids.filter((id) => !seenIds.has(id));
  const result = applyExistingStreak(freshIds, existingIds, existingStreak, stopAfterExistingStreak);
  existingStreak = result.streak;
  existingStreakReached = result.reached;
  return freshIds;
}
```

At each current `const before = seenIds.size; ids.forEach(...)` block, change the order to:

```javascript
const freshIds = observeIdsForFastStop(ids);
const before = seenIds.size;
freshIds.forEach((id) => seenIds.add(id));
const newIds = seenIds.size - before;
```

`fetchedIds`를 쓰는 분기는 두 곳이다: page-1 fallback fetch(약 221행)와 next-page fetch(약 307행). 두 곳 모두 아래 패턴으로 교체한다.

```javascript
const freshIds = observeIdsForFastStop(fetchedIds);
const before = seenIds.size;
freshIds.forEach((id) => seenIds.add(id));
const newIds = seenIds.size - before;
```

After each page is pushed to `pages`, before fetching the next page, add:

```javascript
if (existingStreakReached) {
  endReason = `existing_streak_${stopAfterExistingStreak}`;
  break;
}
```

The guard must run after writing the raw page that reached the threshold, and before requesting the next page.

- [ ] **Step 5: summary에 fast-stop 진단값 추가**

In `summary`:

```javascript
existing_streak_stop_limit: stopAfterExistingStreak,
existing_streak_at_end: existingStreak,
existing_ids_loaded: existingIds.size,
```

- [ ] **Step 6: Node checks 실행**

Run:

```powershell
node --test tests/unit/test_linkedin_opencli_fast_stop.mjs
node --check scripts/linkedin_opencli_shadow_collect.mjs
```

Expected:

```markdown
all node tests pass
node --check exits 0
```

## Task 3: Python collector command를 mode별로 분기

**Files:**

- Modify: `linkedin_scrap.py`
- Modify: `tests/integration/test_linkedin_opencli_pipeline.py`

- [ ] **Step 1: update mode command failing test 추가**

Append to `tests/integration/test_linkedin_opencli_pipeline.py`:

```python
def test_update_mode_collector_uses_existing_streak_stop(monkeypatch, tmp_path):
    import json
    import linkedin_scrap

    commands = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = '{"pages_collected": 2, "total_unique_activity_ids": 20, "end_reason": "existing_streak_20"}'
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "update only")
    monkeypatch.setattr(linkedin_scrap, "OPENCLI_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    raw_dir, summary = linkedin_scrap.run_opencli_collector(
        datetime(2026, 7, 9, 18, 0, 0),
        existing_codes={"111", "222"},
    )

    command = commands[0]
    assert "--use-bound-session" in command
    assert "--until-exhausted" not in command
    assert "--existing-ids-file" in command
    assert "--stop-after-existing-streak" in command
    assert command[command.index("--stop-after-existing-streak") + 1] == "20"
    ids_path = command[command.index("--existing-ids-file") + 1]
    assert json.loads(Path(ids_path).read_text(encoding="utf-8")) == ["111", "222"]
    assert summary["end_reason"] == "existing_streak_20"
    assert raw_dir.endswith("raw\\20260709_180000") or raw_dir.endswith("raw/20260709_180000")
```

- [ ] **Step 2: all mode command failing test 추가**

Append:

```python
def test_all_mode_collector_keeps_until_exhausted(monkeypatch, tmp_path):
    import linkedin_scrap

    commands = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = '{"pages_collected": 62, "total_unique_activity_ids": 602, "end_reason": "load_button_absent"}'
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "all")
    monkeypatch.setattr(linkedin_scrap, "OPENCLI_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    linkedin_scrap.run_opencli_collector(
        datetime(2026, 7, 9, 18, 0, 0),
        existing_codes={"111", "222"},
    )

    command = commands[0]
    assert "--use-bound-session" in command
    assert "--until-exhausted" in command
    assert "--existing-ids-file" not in command
    assert "--stop-after-existing-streak" not in command
```

Ensure imports include:

```python
from pathlib import Path
```

- [ ] **Step 3: RED 확인**

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_update_mode_collector_uses_existing_streak_stop tests/integration/test_linkedin_opencli_pipeline.py::test_all_mode_collector_keeps_until_exhausted -q
```

Expected:

```markdown
update mode test fails because run_opencli_collector() has no existing_codes argument or still sends --until-exhausted
all mode may pass current --until-exhausted assertion but fails if signature is not updated
```

- [ ] **Step 4: Python 상수와 existing IDs writer 구현**

In `linkedin_scrap.py` near constants:

```python
CONSECUTIVE_EXISTING_LIMIT = 20
```

Add helper near OpenCLI helpers:

```python
def write_existing_ids_file(raw_dir, existing_codes):
    existing_ids = sorted(str(code) for code in existing_codes if code)
    os.makedirs(raw_dir, exist_ok=True)
    ids_path = os.path.join(raw_dir, "existing_ids.json")
    save_json(ids_path, existing_ids)
    return ids_path
```

> `existing_ids.json`은 반드시 stamp 하위 `raw_dir` 내부에 쓴다. `os.path.dirname(raw_dir)`(공통 `.../raw` 폴더)에 고정 파일명으로 쓰면 `--mode update` 동시 실행 시 덮어쓰기 경합으로 엉뚱한 ID 세트가 collector에 주입된다.

- [ ] **Step 5: `run_opencli_collector()` mode별 command 구현**

Change signature:

```python
def run_opencli_collector(crawl_start_time, existing_codes=None, session=OPENCLI_PRODUCTION_SESSION):
```

Build base command with `--use-bound-session`, then:

```python
if CRAWL_MODE == "update only":
    ids_path = write_existing_ids_file(raw_dir, existing_codes or set())
    command.extend([
        "--existing-ids-file",
        ids_path,
        "--stop-after-existing-streak",
        str(CONSECUTIVE_EXISTING_LIMIT),
    ])
else:
    command.append("--until-exhausted")
```

- [ ] **Step 6: `collect_opencli_posts()`와 `LinkedinScraper.run()` 연결**

Change signature:

```python
def collect_opencli_posts(crawl_start_time, existing_codes=None):
```

Change collector call:

```python
raw_dir, collection_summary = run_opencli_collector(crawl_start_time, existing_codes=existing_codes)
```

Change scraper run call:

```python
self.posts, self.opencli_metadata = collect_opencli_posts(CRAWL_START_TIME, existing_codes=self.existing_codes)
```

- [ ] **Step 7: Python tests GREEN 확인**

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_update_mode_collector_uses_existing_streak_stop tests/integration/test_linkedin_opencli_pipeline.py::test_all_mode_collector_keeps_until_exhausted -q
```

Expected:

```markdown
2 passed
```

## Task 4: metadata와 로그 의미를 update fast path에 맞게 정리

**Files:**

- Modify: `linkedin_scrap.py`
- Test: `tests/integration/test_linkedin_opencli_pipeline.py`

- [ ] **Step 1: metadata contract test 추가**

Append:

```python
def test_update_metadata_records_fast_stop_without_treating_unobserved_as_deletion():
    import linkedin_scrap

    old_posts = [
        {"platform_id": "old-1", "sequence_id": 1, "full_text": "old"},
        {"platform_id": "old-2", "sequence_id": 2, "full_text": "old"},
    ]
    scraped_posts = [
        {"platform_id": "new-1", "sequence_id": 0, "full_text": "new"},
        {"platform_id": "old-2", "sequence_id": 2, "full_text": "old again"},
    ]

    final_posts, new_items, report = linkedin_scrap.merge_linkedin_full_posts(old_posts, scraped_posts, "update only")

    assert {post["platform_id"] for post in final_posts} == {"old-1", "old-2", "new-1"}
    assert [post["platform_id"] for post in new_items] == ["new-1"]
    assert report["unobserved_existing_count"] == 1
    assert report["unobserved_existing_policy"] == "preserved_not_deletion_candidate"
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_update_metadata_records_fast_stop_without_treating_unobserved_as_deletion -q
```

Expected:

```markdown
FAIL
KeyError: 'unobserved_existing_policy'
```

- [ ] **Step 3: merge report에 policy 추가**

In `merge_linkedin_full_posts()`:

```python
unobserved_policy = (
    "preserved_not_deletion_candidate"
    if crawl_mode == "update only"
    else "preserved_pending_full_sync_review"
)
merge_report = {
    "crawl_mode": crawl_mode,
    "observed_existing_count": len(observed_existing),
    "unobserved_existing_count": len(unobserved_existing_ids),
    "unobserved_existing_ids": unobserved_existing_ids[:20],
    "unobserved_existing_policy": unobserved_policy,
}
```

In `update_full_version()` metadata and merge history, include:

```python
"unobserved_existing_policy": merge_report["unobserved_existing_policy"],
"opencli_end_reason": opencli_collection.get("end_reason"),
"opencli_existing_streak_stop_limit": opencli_collection.get("existing_streak_stop_limit"),
"opencli_existing_streak_at_end": opencli_collection.get("existing_streak_at_end"),
"opencli_existing_ids_loaded": opencli_collection.get("existing_ids_loaded"),
```

- [ ] **Step 4: update mode 안내 로그 수정**

Change the existing update message:

```python
print(
    f"🔄 UPDATE ONLY 모드: 기존 {len(self.existing_codes)}건과 대조, "
    f"기수집 {CONSECUTIVE_EXISTING_LIMIT}건 연속 확인 시 수집을 중단합니다."
)
```

Do not change UI button labels.

- [ ] **Step 5: GREEN 확인**

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py::test_update_metadata_records_fast_stop_without_treating_unobserved_as_deletion -q
```

Expected:

```markdown
1 passed
```

## Task 5: focused verification

**Files:**

- Verify only

- [ ] **Step 1: syntax and unit/integration checks**

Run:

```powershell
node --check scripts/linkedin_opencli_shadow_collect.mjs
node --test tests/unit/test_linkedin_opencli_fast_stop.mjs
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
pytest tests/unit/test_opencli_cleanup.py -q
node utils/query-sns.mjs --help
```

Expected:

```markdown
all commands exit 0
query-sns help prints usage
```

- [ ] **Step 2: broader Python smoke**

Run:

```powershell
pytest tests/unit -q
```

Expected:

```markdown
pass or only pre-existing unrelated failures are reported with exact failing tests
```

## Task 6: real update QA

**Files:**

- Generated: latest `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- Generated: latest `output_total/total_full_YYYYMMDD.json`
- Possible generated: `web_viewer/sns_tags.json`

- [ ] **Step 1: baseline 기록**

Run:

```powershell
git status --short --untracked-files=all
```

Expected:

```markdown
existing dirty files are recorded before running collectors
```

- [ ] **Step 2: LinkedIn update 실행**

Run:

```powershell
python linkedin_scrap.py --mode update
```

Expected:

```markdown
exit 0
stdout includes "기수집 20건 연속"
OpenCLI raw summary includes end_reason "existing_streak_20" when no late new item interrupts the streak
pages_collected is materially below the recent full-check baseline of 62-63 pages when the account has no large new backlog
no LinkedIn collection Chrome window remains
```

- [ ] **Step 3: total merge 실행**

Run:

```powershell
python total_scrap.py --mode update
```

Expected:

```markdown
exit 0
latest output_total/total_full_YYYYMMDD.json is regenerated
LinkedIn count is present in SNS_SCRAP_SUMMARY
```

- [ ] **Step 4: viewer surface 확인**

Run:

```powershell
npm run view
```

Then use Playwright or the project browser verification helper to open `http://localhost:5000/`, confirm:

```markdown
viewer top count equals latest total JSON post count
LinkedIn posts are searchable
active filters do not hide the checked post
```

Expected:

```markdown
viewer count and latest total JSON count agree
```

## Task 7: final audit

**Files:**

- Verify only

- [ ] **Step 1: scope audit**

Run:

```powershell
git diff --stat
git diff -- linkedin_scrap.py scripts/linkedin_opencli_shadow_collect.mjs tests/integration/test_linkedin_opencli_pipeline.py tests/unit/test_linkedin_opencli_fast_stop.mjs
```

Expected:

```markdown
diff touches only LinkedIn collector command, Node fast-stop logic, tests, and generated outputs from QA
no UI/viewer/parser/schema/Threads/X logic changes
```

- [ ] **Step 2: commit preparation only if explicitly requested**

If the user asks for commit, use `cp` skill. Do not run raw `git add` or `git commit`.

Suggested commit message:

```markdown
fix(linkedin): update 모드 20건 연속 중단 복귀 — 전체 검증과 빠른 갱신 분리
```

## Self Review

- Spec coverage: `update` fast path, `all` full-check preservation, no UI change, no parser/schema change, metadata/log traceability are covered by Tasks 1-6.
- Placeholder scan: 미완성 표식이 남지 않았고, 현재 남는 검색 매치는 코드 기호(`__init__`)뿐이다.
- Type/name consistency: `CONSECUTIVE_EXISTING_LIMIT`, `--existing-ids-file`, `--stop-after-existing-streak`, `existing_streak_20`, and metadata keys are used consistently.
- Risk note: this plan assumes the prior owned-window work remains uncommitted/dirty but present. Before implementation, re-run `git status --short` and preserve unrelated dirty output JSON/viewer state.

## Plan Check 반영 이력 (2026-07-09)

agy(Gemini 3.1 Pro) + Claude 코드 대조 검수 결과를 반영했다. 검수보고서: `_docs/plan-check/20260709_02_LinkedIn-update-20건-연속중단-복귀-구현계획_검수보고서.md`

- Task 3/Step 4: `existing_ids.json`을 `raw_dir` 내부(stamp 하위)에 쓰도록 수정. 공통 `.../raw` 폴더 고정 파일명 사용 시 동시 실행 덮어쓰기 경합 제거.
- Task 2/Step 3: import 지시를 `pathToFileURL`만 추가하도록 정정(`join` 등 기존 import 중복 제거). 종료 블록 교체 대상을 실제 파일의 가드 없는 `try/finally`로 명시.
- Task 2/Step 4: `fetchedIds` 분기(약 221·307행) 교체 코드를 명시해 스코프 모호성 제거.
