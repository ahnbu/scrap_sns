---
title: LinkedIn OpenCLI 기본수집기 도입계획
created: 2026-07-07 16:50
tags:
  - scrap_sns
  - linkedin
  - opencli
  - implementation-plan
session_id: codex:019f3b59-7e4a-7682-8fa6-a6e54f3e15f0
session_path: C:/Users/ahnbu/.codex/sessions/2026/07/07/rollout-2026-07-07T15-52-33-019f3b59-7e4a-7682-8fa6-a6e54f3e15f0.jsonl
ai: codex
---

# LinkedIn OpenCLI 기본수집기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LinkedIn 저장글 수집의 기본 실행 경로를 기존 Playwright/storage_state 방식에서 OpenCLI 기반 수집으로 전환하되, 자동 legacy fallback 없이 실패 시 운영 JSON을 쓰지 않고 중단한다.

**Architecture:** `linkedin_scrap.py`는 계속 운영 진입점으로 유지하고, 내부 수집 단계만 OpenCLI raw 수집 스크립트와 기존 LinkedIn parser 재사용 경로로 교체한다. OpenCLI는 현재 저장목록 전체를 수집하고, 저장 전 검증을 통과한 결과만 기존 `merge_linkedin_full_posts()`와 `update_full_version()` 계열 저장 흐름에 연결한다. 첫 도입에서는 기존 full에만 있던 항목을 삭제하지 않고 보존해 데이터 손실을 막는다.

**Tech Stack:** Python 3.13, Node.js `.mjs`, OpenCLI browser/network, existing `utils.linkedin_parser`, existing `utils.common.save_json`, existing `total_scrap.py`, pytest, node test.

---

## 결정 사항

- 기본 LinkedIn 수집 경로는 OpenCLI로 전환한다.
- `--backend opencli|legacy|auto` 같은 backend 선택 옵션은 만들지 않는다.
- legacy 자동 fallback은 만들지 않는다. 실패하면 원인을 출력하고 운영 JSON 쓰기 전에 중단한다.
- legacy 방식 복구는 git 이력과 직전 data baseline 커밋으로 처리한다.
- OpenCLI raw GraphQL과 비교 리포트 JSON은 계속 git 제외 대상이다.
- 운영 기준 JSON은 이미 git 추적 대상으로 확장되어 있으므로 구현 전후 diff 비교가 가능하다.

## 현재 근거

- `docs/20260707_04_LinkedIn-OpenCLI-shadow-수집-검증-수행계획.md` 기준 OpenCLI shadow 수집은 602건, parser 실패 0건, 중복 0건, 반복 실행 ID 차이 0건이었다.
- SaveState와 cluster reference가 602건으로 일치했다.
- canonical 비교에서 `real_opencli_missing`은 0건이었다.
- media audit에서 138건 모두 `entityEmbeddedObject.image` 계열 본문 media로 분류됐고 actor/profile/company logo 오탐은 0건이었다.
- 남은 한계는 raw 기준 검증 중심이며, 실제 브라우저 화면 수동 확인은 별도 완료되지 않았다는 점이다.

## 범위

포함한다:

- `linkedin_scrap.py`의 기본 수집 경로를 OpenCLI로 교체
- OpenCLI 로그인/접근 실패 시 운영 파일 쓰기 전 중단
- OpenCLI raw 수집 결과를 기존 post schema로 변환
- 기존 full 데이터와 보수 병합
- 저장 전 검증 실패 시 `output_linkedin/python/`과 `output_total/` 미변경 보장
- LinkedIn full 저장 후 `total_scrap.py` 통합 재생성 검증
- 뷰어 API와 실제 화면에서 최신 총건수와 LinkedIn 카드 확인

제외한다:

- legacy backend 자동 fallback
- OpenCLI raw GraphQL의 git 추적
- 저장/해제 같은 LinkedIn 계정 상태 변경
- Threads/X 수집 로직 변경
- 태그 자동분류 정책 변경

## 파일 구조

수정 대상:

- `linkedin_scrap.py`
  - 운영 진입점 유지
  - OpenCLI 수집 실행, parse, validation, merge, save orchestration 담당
  - 기존 Playwright UI 수집 코드는 제거하거나 legacy 복구가 필요할 때 git에서 확인하는 대상으로만 둔다
- `scripts/linkedin_opencli_shadow_collect.mjs`
  - production에서도 재사용 가능한 옵션을 추가한다
  - 기본 raw output은 `output_linkedin/opencli_runtime/raw/<timestamp>/`로 분리한다
- `scripts/linkedin_opencli_shadow_parse.py`
  - import 가능한 함수 계약을 명확히 하고, `--require-save-state`를 production 기본값으로 사용한다
- `utils/linkedin_parser.py`
  - 기존 OpenCLI media 패턴 보정 유지
  - parser 변경이 필요할 경우 기존 fixture 회귀를 먼저 추가한다
- `tests/unit/test_linkedin_opencli_shadow_parse.py`
  - SaveState/cluster 필터와 diagnostics 계약 검증
- `tests/unit/test_linkedin_parser.py`
  - OpenCLI media artifact와 profile image 오탐 방지 검증
- `tests/unit/test_linkedin_shadow_compare.mjs`
  - canonical/compare 보조 검증 유지
- `tests/integration/test_linkedin_opencli_pipeline.py`
  - 새로 생성. OpenCLI parsed payload가 기존 full 저장 흐름에 연결되는지 subprocess 없이 fixture로 검증한다

생성 가능 대상:

- `output_linkedin/opencli_runtime/`
  - raw/parsed/report 임시 산출물. git 제외.
- `docs/plan-check-lite/20260707_06_...`
  - plan-check 요청 시 생성.
- `docs/done-check-lite/20260707_06_...`
  - 완료 검수 요청 시 생성.

## 데이터 쓰기 원칙

- OpenCLI raw 수집과 parse는 먼저 ignored runtime folder에 쓴다.
- `linkedin_py_full_YYYYMMDD.json`은 validation 통과 전까지 쓰지 않는다.
- `total_full_YYYYMMDD.json`은 LinkedIn full 저장과 parser/unit 검증이 끝난 뒤에만 재생성한다.
- 기존 full에만 있고 OpenCLI 현재 저장목록에 없는 항목은 첫 도입에서는 삭제하지 않는다.
- 삭제/비공개/stale 정리는 별도 계획으로 분리한다.

## Task 1: OpenCLI production preflight 계약 고정

**Files:**
- Modify: `scripts/linkedin_opencli_shadow_collect.mjs`
- Test: `tests/unit/test_linkedin_shadow_compare.mjs`

- [ ] **Step 1: OpenCLI 로그인 상태 확인 명령을 문서화된 preflight로 고정한다**

Run:

```powershell
opencli linkedin whoami --site-session persistent -f json
```

Expected:

```json
{
  "logged_in": true,
  "site": "linkedin"
}
```

완료 기준:

- 로그인 실패 시 이후 수집 명령을 실행하지 않는다.
- 실패 메시지는 `OpenCLI LinkedIn session is not logged in`을 포함한다.

- [ ] **Step 2: collector production output 경로 옵션을 확인한다**

Run:

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs `
  --session linkedin_saved_production_probe `
  --url https://www.linkedin.com/my-items/saved-posts/ `
  --out output_linkedin/opencli_runtime/raw_probe `
  --max-pages 1
```

Expected:

```markdown
JSON stdout에 pages_collected >= 1, total_unique_activity_ids >= 1 포함
output_linkedin/opencli_runtime/raw_probe/linkedin_opencli_raw_*_page001.json 생성
```

완료 기준:

- raw output 경로가 `output_linkedin/opencli_shadow/`가 아니라 `output_linkedin/opencli_runtime/` 계열이다.
- 생성된 raw는 git status에 나타나지 않는다.

## Task 2: parser import 계약과 SaveState 필터 검증

**Files:**
- Modify: `scripts/linkedin_opencli_shadow_parse.py`
- Test: `tests/unit/test_linkedin_opencli_shadow_parse.py`

- [ ] **Step 1: production parse 함수 계약 테스트를 추가한다**

Test case:

```python
def test_parse_shadow_raw_requires_cluster_and_save_state(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "page001.json"
    raw_path.write_text(json.dumps(build_saved_posts_raw_fixture()), encoding="utf-8")

    result = parse_shadow_raw(str(raw_dir), datetime(2026, 7, 7, 12, 0, 0), require_save_state=True)

    assert result["metadata"]["cluster_entity_result_count"] == 1
    assert result["metadata"]["save_state_activity_count"] == 1
    assert result["metadata"]["parsed_post_count"] == 1
    assert result["metadata"]["entity_without_save_state_count"] == 0
    assert result["posts"][0]["diagnostics"]["save_state_verified"] is True
    assert result["posts"][0]["diagnostics"]["cluster_reference_verified"] is True
```

Run:

```powershell
pytest tests/unit/test_linkedin_opencli_shadow_parse.py -q
```

Expected:

```markdown
pass
```

완료 기준:

- `parse_shadow_raw(..., require_save_state=True)`가 production에서 직접 import 가능한 함수로 유지된다.
- SaveState와 cluster reference를 모두 통과하지 못한 entity는 post로 저장되지 않는다.

## Task 3: LinkedIn scraper를 OpenCLI 단일 경로로 전환

**Files:**
- Modify: `linkedin_scrap.py`
- Create: `tests/integration/test_linkedin_opencli_pipeline.py`

- [ ] **Step 1: pipeline fixture 테스트를 작성한다**

Test case:

```python
def test_opencli_pipeline_merges_without_deleting_unobserved_existing(tmp_path, monkeypatch):
    old_posts = [
        {"platform_id": "111", "sequence_id": 1, "full_text": "old retained", "media": []},
        {"platform_id": "222", "sequence_id": 2, "full_text": "old updated", "media": []},
    ]
    opencli_posts = [
        {"platform_id": "222", "sequence_id": 0, "full_text": "new text", "media": ["m1"]},
        {"platform_id": "333", "sequence_id": 0, "full_text": "new saved", "media": []},
    ]

    final_posts, new_items, report = merge_linkedin_full_posts(old_posts, opencli_posts, "update only")

    ids = {post["platform_id"] for post in final_posts}
    assert ids == {"111", "222", "333"}
    assert len(new_items) == 1
    assert report["unobserved_existing_count"] == 1
```

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
```

Expected:

```markdown
1 passed
```

완료 기준:

- OpenCLI 현재 저장목록에 없는 기존 항목이 첫 도입에서 삭제되지 않는다.
- 기존 항목의 `sequence_id`와 `crawled_at` 보존 규칙이 유지된다.

- [ ] **Step 2: `linkedin_scrap.py`에서 Playwright 수집 루프를 OpenCLI pipeline 호출로 교체한다**

Implementation contract:

```python
def collect_opencli_posts(crawl_start_time):
    raw_dir = run_opencli_collector(crawl_start_time)
    parsed = parse_shadow_raw(raw_dir, crawl_start_time, require_save_state=True)
    validate_opencli_payload(parsed)
    return parsed["posts"], parsed["metadata"]
```

완료 기준:

- `python linkedin_scrap.py --mode update`가 OpenCLI collector를 호출한다.
- `sync_playwright()` 기반 브라우저 UI 수집 루프는 기본 실행 경로에서 제거된다.
- backend 선택 옵션은 추가하지 않는다.

## Task 4: 저장 전 validation gate 구현

**Files:**
- Modify: `linkedin_scrap.py`
- Test: `tests/integration/test_linkedin_opencli_pipeline.py`

- [ ] **Step 1: validation 실패 시 운영 파일 미쓰기 테스트를 작성한다**

Test case:

```python
def test_validation_failure_stops_before_writing_full_file(tmp_path):
    payload = {
        "metadata": {
            "parsed_post_count": 0,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
        },
        "posts": [],
    }

    with pytest.raises(RuntimeError, match="OpenCLI parsed post count is zero"):
        validate_opencli_payload(payload)
```

Run:

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
```

Expected:

```markdown
pass
```

완료 기준:

- `parsed_post_count == 0`이면 저장하지 않는다.
- `duplicate_platform_id_count > 0`이면 저장하지 않는다.
- `parser_failed_count > 0`이면 저장하지 않는다.
- SaveState/cluster 미검증 항목이 있으면 저장하지 않는다.

- [ ] **Step 2: validation 통과 기준을 구현한다**

Implementation contract:

```python
def validate_opencli_payload(payload):
    metadata = payload.get("metadata") or {}
    if int(metadata.get("parsed_post_count") or 0) <= 0:
        raise RuntimeError("OpenCLI parsed post count is zero")
    if int(metadata.get("duplicate_platform_id_count") or 0) > 0:
        raise RuntimeError("OpenCLI duplicate platform_id detected")
    if int(metadata.get("parser_failed_count") or 0) > 0:
        raise RuntimeError("OpenCLI parser failed for one or more posts")
    if int(metadata.get("entity_without_save_state_count") or 0) > 0:
        raise RuntimeError("OpenCLI SaveState verification failed")
    if int(metadata.get("entity_without_cluster_reference_count") or 0) > 0:
        raise RuntimeError("OpenCLI cluster reference verification failed")
```

완료 기준:

- validation 에러는 `RuntimeError`로 명확히 실패한다.
- validation 실패 시 `output_linkedin/python/linkedin_py_full_YYYYMMDD.json` timestamp가 변하지 않는다.

## Task 5: 운영 실행 검증

**Files:**
- Modify: `output_linkedin/python/linkedin_py_full_YYYYMMDD.json`
- Modify: `output_total/total_full_YYYYMMDD.json`
- Read: `web_viewer/sns_tags.json`
- Read: `web_viewer/sns_user_metadata.json`

- [ ] **Step 1: unit/integration 테스트를 실행한다**

Run:

```powershell
pytest tests/unit/test_linkedin_opencli_shadow_parse.py tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py tests/integration/test_linkedin_opencli_pipeline.py -q
node --test tests/unit/test_linkedin_shadow_compare.mjs tests/unit/test_linkedin_media_audit.mjs
```

Expected:

```markdown
pytest: all passed
node --test: all tests pass
```

완료 기준:

- Python 테스트와 Node 테스트가 모두 exit 0이다.

- [ ] **Step 2: 실제 LinkedIn update 실행**

Run:

```powershell
python linkedin_scrap.py --mode update
```

Expected:

```markdown
stdout에 OpenCLI 수집 raw file count, parsed_post_count, saved full path 포함
output_linkedin/python/linkedin_py_full_YYYYMMDD.json 생성 또는 갱신
```

완료 기준:

- `parsed_post_count >= 1`
- `duplicate_platform_id_count = 0`
- `parser_failed_count = 0`
- 저장된 full JSON의 `metadata.total_count`가 `posts.length`와 일치한다.

- [ ] **Step 3: 통합본 재생성**

Run:

```powershell
python total_scrap.py --mode update
```

Expected:

```markdown
output_total/total_full_YYYYMMDD.json 갱신
metadata.linkedin_count가 최신 linkedin full posts count와 일치
```

완료 기준:

- 최신 `output_total/total_full_YYYYMMDD.json`에 LinkedIn post가 포함된다.
- 전체 `metadata.total_count`가 `posts.length`와 일치한다.

## Task 6: 웹 뷰어 검증

**Files:**
- Read: `scrap_sns_server.py`
- Read: `web_viewer/`
- Read: `output_total/total_full_YYYYMMDD.json`

- [ ] **Step 1: 서버 재시작**

Run:

```powershell
npm run view
```

Expected:

```markdown
5000번 서버가 새로 시작되고 http://localhost:5000/ 이 응답한다.
```

완료 기준:

- 기존 정상 응답 여부와 관계없이 런처가 서버를 재시작한다.
- `http://localhost:5000/api/health` 또는 루트 화면이 응답한다.

- [ ] **Step 2: 실제 화면 확인**

Run:

```powershell
node C:/Users/ahnbu/.claude/skills/_shared/hidden-browser-verify-runner.mjs --url http://localhost:5000/
```

Expected:

```markdown
화면 상단 총건수가 최신 output_total metadata.total_count와 일치한다.
LinkedIn 필터 또는 검색에서 최신 LinkedIn 카드가 표시된다.
```

완료 기준:

- API/CLI 결과만으로 완료 판단하지 않는다.
- 실제 화면에서 LinkedIn 카드가 확인된다.
- 캡처 또는 runner 결과 경로를 완료 보고에 남긴다.

## Task 7: 완료 검수와 커밋

**Files:**
- Modify: `CHANGELOG.md`
- Modify: changed source/test/docs files

- [ ] **Step 1: done-check-lite 검수**

Run:

```powershell
done-check-lite
```

Expected:

```markdown
Blocking issue 없음
```

완료 기준:

- 검수 결과의 blocking issue가 있으면 구현을 수정한다.
- 검수 문서는 `docs/done-check-lite/`에 저장한다.

- [ ] **Step 2: 커밋**

Run:

```markdown
cp 스킬로 concern 단위 커밋을 생성한다.
```

Expected commit split:

```markdown
fix(linkedin): OpenCLI 기본 수집 경로 도입
test(linkedin): OpenCLI 수집 검증 테스트 보강
docs(linkedin): OpenCLI 도입 결과와 검수 기록 추가
```

완료 기준:

- 운영 코드, 테스트, 문서가 concern 단위로 분리된다.
- 보안 게이트가 통과한다.
- remote push가 성공한다.

## 실행 결과 (2026-07-07 KST)

### 구현 결과

- `linkedin_scrap.py`의 기본 수집 경로를 OpenCLI 단일 경로로 전환했다.
- legacy Playwright UI 수집 루프와 로그인/storage_state 처리 코드는 `linkedin_scrap.py`에서 제거했다.
- OpenCLI 로그인 preflight, raw 수집, `parse_shadow_raw(..., require_save_state=True)`, validation, 보수 병합, full 저장 순서로 실행되도록 정리했다.
- validation 실패 시 `RuntimeError`로 중단하며 운영 JSON 저장 전 실패한다.
- Windows cp949 콘솔에서 이모지 로그 출력이 실패하지 않도록 stdout/stderr UTF-8 재설정을 추가했다.
- OpenCLI 네트워크 로그에서 첫 페이지 GraphQL entry가 잡히지 않는 경우 직접 GraphQL fetch로 첫 페이지를 수집하도록 collector를 보강했다.
- LinkedIn full metadata에 OpenCLI 수집·파싱 진단값을 남기도록 했다.

### 산출물

- 수정: `linkedin_scrap.py`
- 수정: `scripts/linkedin_opencli_shadow_collect.mjs`
- 생성: `tests/integration/test_linkedin_opencli_pipeline.py`
- 생성: `docs/plan-check-lite/20260707_06_LinkedIn-OpenCLI-기본수집기-도입계획_경량계획검수보고서.md`
- 갱신: `output_linkedin/python/linkedin_py_full_20260707.json`
- 갱신: `output_total/total_full_20260707.json`
- 갱신: `output_threads/python/threads_py_full_20260707.json`
- 갱신: `output_threads/python/threads_py_simple_20260707.json`
- 갱신: `output_twitter/python/twitter_py_full_20260707.json`
- 갱신: `output_twitter/python/twitter_py_simple_20260707.json`
- 갱신: `web_viewer/sns_tags.json`
- 증거: `docs/done-check-lite/evidence/viewer_home_20260707.png`
- 증거: `docs/done-check-lite/evidence/viewer_search_codex_20260707.png`
- 생성: `docs/done-check-lite/20260707_06_LinkedIn-OpenCLI-기본수집기-도입계획_경량완료검수보고서.md`

### 검증 결과

```powershell
pytest tests/integration/test_linkedin_opencli_pipeline.py -q
```

결과: 8 passed

```powershell
pytest tests/unit/test_linkedin_opencli_shadow_parse.py tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q
```

결과: 10 passed

```powershell
node --test tests/unit/test_linkedin_shadow_compare.mjs tests/unit/test_linkedin_media_audit.mjs
```

결과: 10 passed

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_production_probe --url https://www.linkedin.com/my-items/saved-posts/ --out output_linkedin/opencli_runtime/raw_probe --max-pages 1
```

결과: pages_collected 2, total_unique_activity_ids 19

```powershell
python linkedin_scrap.py --mode update
```

결과:

- OpenCLI raw 수집: 62 pages, 602 unique IDs
- parse 검증: parsed 602, duplicates 0, parser_failed 0
- LinkedIn full 저장: `output_linkedin/python/linkedin_py_full_20260707.json`
- LinkedIn full 총건수: 605
- 신규 LinkedIn 저장글: 0

```powershell
python total_scrap.py --mode update
```

결과:

- Producer/Consumer wave 모두 완료
- `output_total/total_full_20260707.json` 저장
- total 총건수: 1755
- metadata breakdown: Threads 1078, LinkedIn 605, X/Twitter 93

주의:

- 수집·병합은 성공했으나 오래된 운영 JSON 자동 정리 단계에서 `safe-trash.cmd`를 PowerShell `-File`로 호출해 정리만 실패했다.
- 실패 메시지: `Processing -File 'C:\Users\ahnbu\scripts\safe-trash.cmd' failed because the file does not have a '.ps1' extension.`
- 이 문제는 OpenCLI 전환 로직이 아니라 cleanup 호출 방식 문제이며 별도 수정 대상이다.

### 웹 뷰어 검증

```powershell
npm run view
```

결과: `wscript sns_hub.vbs` 정상 종료

```powershell
GET http://localhost:5000/api/status
GET http://localhost:5000/api/posts
GET http://localhost:5000/api/search?q=Codex&platform=linkedin&limit=3
```

결과:

- `/api/status`: `status=running`
- `/api/posts`: 1755건
- LinkedIn `Codex` 검색: 3건

실제 화면 검증:

- `http://localhost:5000/` 로드 성공
- 화면 총건수 1755 표시 확인
- `Codex` 검색 결과 화면 표시 확인
- 캡처 저장:
  - `docs/done-check-lite/evidence/viewer_home_20260707.png`
  - `docs/done-check-lite/evidence/viewer_search_codex_20260707.png`

태그 파일 확인:

- `web_viewer/sns_tags.json`은 뷰어 검증 과정에서 1433개에서 1441개로 증가했다.
- JSON diff는 정렬/재출력 때문에 크게 보이나, parsed key 기준 삭제는 0개, 추가는 8개다.
- 운영 기준 JSON에 해당하므로 되돌리지 않았다.

### 완료 검수

```powershell
done-check-lite --agent
```

결과:

- Verdict: 완료
- Blocking Gaps: 없음
- 보고서: `docs/done-check-lite/20260707_06_LinkedIn-OpenCLI-기본수집기-도입계획_경량완료검수보고서.md`

### 미실행 항목

- Task 7 Step 2 커밋은 `one-stop` 절차의 경계에 따라 수행하지 않았다.
- 커밋은 사용자 지시가 있으면 cp 스킬로 concern 단위 분리해 진행한다.

## 자체 검수

- Spec coverage: OpenCLI 기본값 전환, legacy 자동 fallback 제외, 저장 전 검증, 운영 JSON 보호, 뷰어 검증을 모두 Task에 반영했다.
- Placeholder scan: 미정 상태를 남기는 표현 없이 실행 가능한 명령과 완료 기준을 적었다.
- Type consistency: `parse_shadow_raw`, `validate_opencli_payload`, `merge_linkedin_full_posts` 이름을 각 Task에서 일관되게 사용했다.
- Scope control: Threads/X 수집 로직과 태그 정책 변경은 제외했다.
- Data safety: 기존 full에만 있는 항목을 첫 도입에서 삭제하지 않는 보수 병합을 명시했다.
