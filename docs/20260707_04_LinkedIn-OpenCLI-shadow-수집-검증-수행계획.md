---
title: LinkedIn OpenCLI shadow 수집 검증 수행계획
created: 2026-07-07 14:24
tags:
  - scrap_sns
  - linkedin
  - opencli
  - shadow-test
session_id: codex:019f3af6-7093-7be0-b647-4a4fa8a2abb1
session_path: C:/Users/ahnbu/.codex/sessions/2026/07/07/rollout-2026-07-07T14-04-22-019f3af6-7093-7be0-b647-4a4fa8a2abb1.jsonl
ai: codex
---

# LinkedIn OpenCLI Shadow 수집 검증 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenCLI browser/network 기반 LinkedIn 저장글 수집이 기존 `scrap_sns` LinkedIn 수집을 대체하거나 fallback으로 들어가도 되는지, 전체 저장글 기준으로 누락·품질·안정성을 검증한다.

**Architecture:** 운영 수집 파이프라인은 수정하지 않고, OpenCLI shadow 수집기가 LinkedIn 저장글 페이지의 `SEARCH_MY_ITEMS_SAVED_POSTS` GraphQL 응답을 전부 수집한다. 수집 결과는 `output_linkedin/opencli_shadow/`에만 저장하고, 비교 스크립트가 최신 `output_linkedin/python/linkedin_py_full_*.json` 및 필요 시 최신 `output_total/total_full_*.json`과 대조한다.

**Tech Stack:** OpenCLI browser/network, Node.js `.mjs` orchestration, Python LinkedIn parser reuse, existing `utils/linkedin_parser.py`, existing JSON schema.

---

## 범위

이번 검증은 "실제 도입 전 안전성 검증"이다. 운영 파일을 교체하지 않고, 별도 shadow 산출물만 만든다.

포함 범위:

- OpenCLI 로그인 세션으로 `https://www.linkedin.com/my-items/saved-posts/` 접근
- `voyager/api/graphql` 중 `SEARCH_MY_ITEMS_SAVED_POSTS` 응답 전량 캡처
- `결과 더보기` 버튼 클릭 또는 스크롤 기반 추가 로딩
- 모든 저장글 페이지를 끝까지 수집
- 기존 `scrap_sns` 저장 데이터와 `platform_id` 기준 비교
- 본문, 작성자, URL, 미디어, 순서, parser 실패 건수 비교
- Go / No-Go 판정 리포트 작성

제외 범위:

- `linkedin_scrap.py` 운영 로직 교체
- `output_linkedin/python/` 또는 `output_total/` 쓰기
- LinkedIn 저장/해제 같은 계정 상태 변경
- 수동 로그인 자동화, CAPTCHA, 2FA 자동화
- 커밋

## 검증 가설

| 가설 | 판정 방법 | 통과 기준 |
|---|---|---:|
| OpenCLI 인증층이 기존 `storage_state`보다 안정적이다 | 로그인 리다이렉트, step-up, authwall 발생 여부 기록 | ✅ 전체 수집 중 인증 차단 0건 |
| OpenCLI에서도 GraphQL 기반 수집이 가능하다 | `SEARCH_MY_ITEMS_SAVED_POSTS` 응답 캡처 | ✅ page 1 이상, `EntityResultViewModel` 존재 |
| 모든 저장글 추가 로딩이 가능하다 | `paginationToken`, `start`, 고유 activity id 증가 확인 | ✅ 종료 조건 도달 전까지 id 증가 |
| 기존 파서와 연결 가능하다 | `utils.linkedin_parser.parse_linkedin_post()` 적용 | ✅ parser 성공률 98% 이상 |
| 대체 또는 fallback 후보로 충분하다 | 기존 데이터와 품질 비교 | ✅ 공통 ID 핵심 필드 중대 손실 0건 |

## 파일 계획

생성 예정:

- `scripts/linkedin_opencli_shadow_collect.mjs`
  - OpenCLI browser session을 열고 저장글 GraphQL 응답을 페이지 단위로 저장한다.
  - 운영 JSON에는 쓰지 않는다.
- `scripts/linkedin_opencli_shadow_parse.py`
  - shadow raw GraphQL을 기존 `utils.linkedin_parser.parse_linkedin_post()`로 표준 post 배열로 변환한다.
- `scripts/linkedin_shadow_compare.mjs`
  - shadow 결과와 기존 `linkedin_py_full_*.json`, 선택적으로 `total_full_*.json`을 비교한다.
- `tests/unit/test_linkedin_shadow_compare.mjs`
  - 비교 로직의 set diff, field diff, report summary 계산을 fixture로 검증한다.
- `output_linkedin/opencli_shadow/raw/linkedin_opencli_raw_<timestamp>_pageNN.json`
  - page별 원본 GraphQL detail. git 추적 대상 아님.
- `output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json`
  - parser 변환 후 표준 post 배열. git 추적 대상 아님.
- `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.md`
  - 사람이 검토할 비교 리포트. 필요 시 문서로 승격.

수정 예정:

- 없음. 검증 단계에서는 운영 코드 수정 금지.

참조 파일:

- `linkedin_scrap.py`
- `utils/linkedin_parser.py`
- `utils/post_schema.py`
- `docs/crawling_logic.md`
- `docs/development.md`

## 성공 기준

최종 Go 판정은 아래 조건을 모두 만족해야 한다.

| 영역 | 성공 기준 |
|---|---|
| 접근 안정성 | OpenCLI shadow 전체 수집 중 로그인 페이지, authwall, checkpoint 이동 없음 |
| 전체 수집 | `결과 더보기` 버튼 소멸, 또는 3회 연속 신규 id 0건, 또는 paginationToken 반복으로 정상 종료 |
| GraphQL 캡처 | 수집 page마다 `SEARCH_MY_ITEMS_SAVED_POSTS` URL, `start`, `paginationToken`, response size 기록 |
| 데이터 수량 | shadow 고유 `platform_id` 수가 DOM 고유 activity id 수와 일치하거나 차이가 1% 이하 |
| parser 성공률 | `EntityResultViewModel` 대비 표준 post 변환 성공률 98% 이상 |
| 중복 | shadow 결과 내 `platform_id` 중복 0건 |
| 공통 ID 품질 | 기존 데이터와 공통인 ID에서 `url` 누락 0건, `full_text` 심각한 잘림 0건 |
| 미디어 | 공통 ID media count 차이는 리포트에 전부 표기하고, 대표 샘플 10건 수동 확인 |
| 누락 후보 | 기존 full에는 있고 shadow에는 없는 ID를 전부 `missing_from_shadow_candidates`로 분류하고 원인 라벨링 |
| 신규 후보 | shadow에는 있고 기존 full에는 없는 ID를 `shadow_only_candidates`로 분류하고 최신 저장글/기존 미수집 가능성으로 라벨링 |

No-Go 조건:

- OpenCLI가 전체 수집 중 LinkedIn 로그인/보안 확인으로 이동한다.
- GraphQL 응답이 page 1 이후 안정적으로 잡히지 않는다.
- shadow 결과가 기존 full의 최근 저장글 다수를 누락한다.
- 공통 ID에서 본문이 반복적으로 잘리거나 작성자/URL 매핑이 깨진다.
- 수집 종료 조건이 불명확해 무한 루프 위험이 있다.

## Task 1: 기준 데이터 고정

**Files:**
- Read: `output_linkedin/python/linkedin_py_full_*.json`
- Read: `output_total/total_full_*.json`
- Output: `output_linkedin/opencli_shadow/baseline/baseline_inventory_<timestamp>.json`

- [ ] **Step 1: 최신 기준 파일 확인**

Run:

```powershell
$linkedin = Get-ChildItem output_linkedin/python -Filter 'linkedin_py_full_*.json' | Sort-Object Name -Descending | Select-Object -First 1
$total = Get-ChildItem output_total -Filter 'total_full_*.json' | Sort-Object Name -Descending | Select-Object -First 1
[pscustomobject]@{
  linkedin_full = $linkedin.FullName
  linkedin_updated = $linkedin.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
  total_full = $total.FullName
  total_updated = $total.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
} | ConvertTo-Json -Depth 3
```

Expected:

- `linkedin_full`이 `output_linkedin/python/linkedin_py_full_*.json` 파일을 가리킨다.
- `total_full`이 `output_total/total_full_*.json` 파일을 가리킨다.

- [ ] **Step 2: 기준 데이터 인벤토리 저장**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs baseline `
  --linkedin-full "$($linkedin.FullName)" `
  --total-full "$($total.FullName)" `
  --out output_linkedin/opencli_shadow/baseline
```

Expected:

- `baseline_inventory_<timestamp>.json` 생성
- 출력에 `linkedin_full_count`, `total_linkedin_count`, `unique_platform_ids` 포함

완료 기준:

- 최신 기준 파일 경로와 건수가 리포트에 기록된다.
- 기준 파일이 오래됐을 수 있다는 한계를 리포트에 남긴다.

## Task 2: OpenCLI shadow 전체 수집

**Files:**
- Create: `scripts/linkedin_opencli_shadow_collect.mjs`
- Output: `output_linkedin/opencli_shadow/raw/*.json`
- Output: `output_linkedin/opencli_shadow/session_<timestamp>.json`

- [ ] **Step 1: OpenCLI 로그인 상태 확인**

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

- [ ] **Step 2: shadow 수집기 dry-run**

Run:

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs --dry-run
```

Expected:

- shadow 수집기의 `linkedin_saved_shadow` browser 세션에서 저장글 페이지 title이 `저장한 게시물 | LinkedIn`을 포함한다.
- 첫 GraphQL URL이 `SEARCH_MY_ITEMS_SAVED_POSTS`를 포함한다.
- raw 파일은 생성하지 않는다.

- [ ] **Step 3: 전체 저장글 shadow 수집**

Run:

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs `
  --session linkedin_saved_shadow `
  --url https://www.linkedin.com/my-items/saved-posts/ `
  --out output_linkedin/opencli_shadow/raw `
  --until-exhausted
```

Expected:

- page별 raw GraphQL JSON 생성
- 각 page log에 `start`, `count`, `unique_activity_ids`, `paginationToken` 기록
- 종료 사유가 다음 중 하나로 기록
  - `load_button_absent`
  - `no_new_ids_after_3_attempts`
  - `repeated_pagination_token`

완료 기준:

- 전체 수집 중 로그인 페이지로 이동하지 않는다.
- raw page 수가 1 이상이다.
- 마지막 session summary에 `total_unique_activity_ids`가 기록된다.

## Task 3: 기존 parser로 shadow 변환

**Files:**
- Create: `scripts/linkedin_opencli_shadow_parse.py`
- Read: `output_linkedin/opencli_shadow/raw/*.json`
- Output: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json`

- [ ] **Step 1: parser smoke test**

Run:

```powershell
pytest tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q
```

Expected:

```markdown
7 passed
```

- [ ] **Step 2: raw GraphQL을 표준 post 배열로 변환**

Run:

```powershell
python scripts/linkedin_opencli_shadow_parse.py `
  --raw-dir output_linkedin/opencli_shadow/raw `
  --out output_linkedin/opencli_shadow
```

Expected:

- `linkedin_opencli_shadow_<timestamp>.json` 생성
- 출력에 `raw_entity_result_count`, `parsed_post_count`, `duplicate_platform_id_count` 포함

완료 기준:

- `parsed_post_count / raw_entity_result_count >= 0.98`
- `duplicate_platform_id_count = 0`
- 모든 post에 `sns_platform=linkedin`, `platform_id`, `url`, `full_text`, `display_name`이 있다.

## Task 4: 기존 수집내역과 A/B 비교

**Files:**
- Create: `scripts/linkedin_shadow_compare.mjs`
- Read: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json`
- Read: `output_linkedin/python/linkedin_py_full_*.json`
- Read: `output_total/total_full_*.json`
- Output: `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.md`
- Output: `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.json`

- [ ] **Step 1: 비교 리포트 생성**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs compare `
  --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json `
  --linkedin-full output_linkedin/python/<latest-linkedin-full>.json `
  --total-full output_total/<latest-total-full>.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- `common_ids`
- `missing_from_shadow_candidates`
- `shadow_only_candidates`
- `text_length_mismatch`
- `url_mismatch`
- `media_count_mismatch`
- `parser_failed_count`
- `go_no_go_recommendation`

- [ ] **Step 2: 누락 후보 라벨링**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs label-missing `
  --report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.json `
  --sample-size 20
```

Expected:

- missing 후보가 다음 라벨 중 하나로 분류된다.
  - `possibly_unsaved_now`
  - `baseline_stale`
  - `opencli_missing_candidate`
  - `needs_manual_check`

완료 기준:

- missing 후보가 단순 누락으로 과잉 판정되지 않는다.
- shadow-only 후보는 신규 저장글 또는 기존 미수집 후보로 분리된다.

## Task 5: 샘플 수동 검증

**Files:**
- Read: `output_linkedin/opencli_shadow/reports/*.json`
- Output: `output_linkedin/opencli_shadow/reports/manual_spotcheck_<timestamp>.md`

- [ ] **Step 1: 샘플 30건 선정**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs sample `
  --report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.json `
  --common 10 `
  --missing 10 `
  --shadow-only 10 `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- 공통 10건, missing 후보 10건, shadow-only 후보 10건 샘플 목록 생성

- [ ] **Step 2: 실제 LinkedIn 상세 URL 확인**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs spotcheck-template `
  --sample output_linkedin/opencli_shadow/reports/manual_spotcheck_sample_<timestamp>.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- 각 샘플에 `platform_id`, `url`, `expected_display_name`, `expected_text_excerpt`, `check_result` 칸이 있다.

완료 기준:

- missing 후보 중 실제로 현재 저장글 목록에 있어야 하는데 shadow에 없는 사례가 0건이거나 원인이 설명된다.
- shadow-only 후보가 실제 저장글로 확인된다.
- media 손실 후보는 대표 샘플에서 실제 표시 여부를 확인한다.

## Task 6: 반복 실행 안정성 검증

**Files:**
- Read/Write: `output_linkedin/opencli_shadow/`

- [ ] **Step 1: shadow 수집 2회 반복**

Run:

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_a --out output_linkedin/opencli_shadow/raw_run_a --until-exhausted
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_b --out output_linkedin/opencli_shadow/raw_run_b --until-exhausted
```

Expected:

- 두 실행 모두 인증 차단 없이 종료
- 두 실행의 `total_unique_activity_ids` 차이 1% 이하

- [ ] **Step 2: 반복 실행 diff**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs compare-shadow-runs `
  --a output_linkedin/opencli_shadow/linkedin_opencli_shadow_run_a.json `
  --b output_linkedin/opencli_shadow/linkedin_opencli_shadow_run_b.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- `run_a_only`, `run_b_only`, `order_changed`, `field_changed` 출력

완료 기준:

- 반복 실행 간 고유 ID 차이 1% 이하
- 공통 ID의 핵심 필드 차이가 설명 가능한 수준
- 인증 step-up 0건

## Task 7: Go / No-Go 판정

**Files:**
- Output: `output_linkedin/opencli_shadow/reports/go_no_go_<timestamp>.md`

- [ ] **Step 1: 판정 리포트 생성**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs decision `
  --compare-report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_<timestamp>.json `
  --repeat-report output_linkedin/opencli_shadow/reports/compare_shadow_runs_<timestamp>.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- 판정값이 `go`, `trial_fallback`, `no_go` 중 하나다.

판정 기준:

| 판정 | 조건 |
|---|---|
| `go` | 전체 수집 성공, parser 성공률 98% 이상, 중복 0건, 공통 ID 핵심 손실 0건 |
| `trial_fallback` | 수집은 되지만 누락 후보 또는 media 차이가 있어 fallback backend로만 도입 권장 |
| `no_go` | 인증 차단, GraphQL 불안정, parser 실패, 대량 누락 중 하나 발생 |

완료 기준:

- 리포트에 최종 권장안과 근거가 남는다.
- 바로 교체, fallback 도입, 보류 중 하나가 명확히 제시된다.

## 실행 순서 제안

권장 실행 순서는 다음이다.

1. Task 1: 기준 데이터 고정
2. Task 2: OpenCLI shadow 전체 수집
3. Task 3: 기존 parser 변환
4. Task 4: A/B 비교
5. Task 5: 샘플 수동 검증
6. Task 6: 반복 실행 안정성 검증
7. Task 7: Go / No-Go 판정

worktree는 이 검증이 통과한 뒤 사용한다. shadow 수집기와 비교 스크립트는 운영 코드를 건드리지 않으므로 현재 브랜치에서 실행해도 위험이 낮다. 단, 이후 `linkedin_scrap.py`에 `--backend opencli`를 붙이는 단계부터는 별도 worktree 또는 새 브랜치에서 진행한다.

## One-stop 실행 결과

실행 시각: 2026-07-07 14:47 KST

### Plan-check

- 보고서: `docs/plan-check-lite/20260707_04_LinkedIn-OpenCLI-shadow-수집-검증-수행계획_경량계획검수보고서.md`
- Verdict: `실행 가능`
- 반영 사항:
  - `opencli linkedin whoami --site-session linkedin_saved_shadow`는 유효하지 않아 `--site-session persistent`로 정정했다.
  - browser 작업 세션명은 `linkedin_saved_shadow*`로 별도 사용한다.

### 구현 요약

- OpenCLI 로그인 세션으로 LinkedIn saved posts 페이지에 접근했다.
- page 1은 OpenCLI browser network에서 `SEARCH_MY_ITEMS_SAVED_POSTS` GraphQL 응답을 확인했다.
- 이후 page는 같은 OpenCLI browser session 안에서 `voyager/api/graphql`을 직접 `fetch()`하여 `paginationToken` 기반으로 끝까지 수집했다.
- 기존 `utils.linkedin_parser.parse_linkedin_post()`를 재사용해 raw GraphQL `EntityResultViewModel`을 표준 post 배열로 변환했다.
- shadow 결과와 기존 `linkedin_py_full_20260707.json`, `total_full_20260707.json`을 `platform_id` 기준으로 비교했다.
- 같은 절차를 2회 반복해 수집 안정성을 확인했다.

### 변경 파일

- `scripts/linkedin_opencli_shadow_collect.mjs`
- `scripts/linkedin_opencli_shadow_parse.py`
- `scripts/linkedin_shadow_compare.mjs`
- `tests/unit/test_linkedin_shadow_compare.mjs`
- `docs/20260707_04_LinkedIn-OpenCLI-shadow-수집-검증-수행계획.md`

운영 수집 코드인 `linkedin_scrap.py`, `output_linkedin/python/`, `output_total/`은 수정하지 않았다.

### 산출물

- 기준 인벤토리: `output_linkedin/opencli_shadow/baseline/baseline_inventory_20260707143227.json`
- 1차 raw: `output_linkedin/opencli_shadow/raw_full3/`
- 1차 shadow: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_144332.json`
- 2차 raw: `output_linkedin/opencli_shadow/raw_full4/`
- 2차 shadow: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_144707.json`
- 비교 리포트: `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707144340.md`
- 반복 실행 비교: `output_linkedin/opencli_shadow/reports/compare_shadow_runs_20260707144717.json`
- 최종 판정: `output_linkedin/opencli_shadow/reports/go_no_go_20260707144723.md`

### 검증 결과

| 항목 | 결과 |
|---|---:|
| 기준 LinkedIn full | 604 |
| 기준 total LinkedIn | 604 |
| 1차 shadow parsed | 602 |
| 2차 shadow parsed | 602 |
| raw entity result | 602 |
| parser 실패 | 0 |
| shadow 내부 중복 | 0 |
| 기존 기준과 공통 ID | 601 |
| shadow 누락 후보 | 3 |
| shadow-only 후보 | 1 |
| 반복 실행 차이 | 0 |
| 본문 길이 차이 후보 | 2 |
| URL 차이 | 0 |
| media 수 차이 후보 | 90 |

불일치 ID의 반복 실행 분류:

| ID | 기준 대비 | 1차 현재 저장목록 | 2차 현재 저장목록 | 수동 확인 반영 해석 |
|---|---|---:|---:|---|
| 7314662801090781184 | shadow 누락 후보 | 없음 | 없음 | 현재 접근 불가. 삭제/비공개 또는 기준 데이터 stale 가능성 높음 |
| 7431989991947321344 | shadow 누락 후보 | 없음 | 없음 | 현재 접근 불가. 삭제/비공개 또는 기준 데이터 stale 가능성 높음 |
| 7450664369769816064 | shadow 누락 후보 | 없음 | 없음 | 저장글 자체가 아니라 저장된 원문을 인용한 wrapper 게시물. 실제 저장 원문은 `7449713771888971776` |
| 7467799020007002112 | shadow-only 후보 | 있음 | 있음 | 현재 접근 가능. 기존 수집 누락 또는 기준 데이터 stale 가능성 |

수동 확인으로 정정된 실제 누락 해석:

| 분류 | 건수 | 근거 |
|---|---:|---|
| 확인된 OpenCLI 실제 누락 | 0 | 저장목록에 있어야 하는데 OpenCLI가 놓친 사례는 현재 확인되지 않음 |
| 기존 기준 stale/삭제 가능성 | 2 | `7314662801090781184`, `7431989991947321344`는 현재 접근 불가 |
| wrapper/original 매칭 문제 | 1 | `7450664369769816064`는 wrapper이고, 원문 `7449713771888971776`은 기준과 shadow 모두에 존재 |
| shadow-only 정상 후보 | 1 | `7467799020007002112`는 현재 접근 가능하고 shadow 2회 모두 수집됨 |

`7450664369769816064` 관련 확인:

- 기존 `scrap_sns` full/total에는 `7450664369769816064`와 `7449713771888971776`이 모두 존재한다.
- OpenCLI shadow에는 `7449713771888971776`만 존재한다.
- OpenCLI raw에는 `SaveState:(SAVE,urn:li:activity:7449713771888971776)`가 명시되어 있다.
- 따라서 이 사례는 OpenCLI 누락이라기보다 기존 데이터/비교 기준이 wrapper 게시물과 실제 저장 원문을 구분하지 못한 케이스다.

### 실행한 검증

```powershell
opencli linkedin whoami --site-session persistent -f json
node scripts/linkedin_shadow_compare.mjs baseline --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json --total-full output_total/total_full_20260707.json --out output_linkedin/opencli_shadow/baseline
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_full3 --out output_linkedin/opencli_shadow/raw_full3 --until-exhausted
python scripts/linkedin_opencli_shadow_parse.py --raw-dir output_linkedin/opencli_shadow/raw_full3 --out output_linkedin/opencli_shadow
node scripts/linkedin_shadow_compare.mjs compare --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_144332.json --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json --total-full output_total/total_full_20260707.json --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_shadow_compare.mjs label-missing --report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707144340.json --sample-size 20
node scripts/linkedin_shadow_compare.mjs sample --report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707144340.json --common 10 --missing 10 --shadow-only 10 --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_shadow_compare.mjs spotcheck-template --sample output_linkedin/opencli_shadow/reports/manual_spotcheck_sample_20260707144349.json --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_full4 --out output_linkedin/opencli_shadow/raw_full4 --until-exhausted
python scripts/linkedin_opencli_shadow_parse.py --raw-dir output_linkedin/opencli_shadow/raw_full4 --out output_linkedin/opencli_shadow
node scripts/linkedin_shadow_compare.mjs compare-shadow-runs --a output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_144332.json --b output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_144707.json --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_shadow_compare.mjs decision --compare-report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707144340.json --repeat-report output_linkedin/opencli_shadow/reports/compare_shadow_runs_20260707144717.json --out output_linkedin/opencli_shadow/reports
node --test tests/unit/test_linkedin_shadow_compare.mjs
pytest tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q
```

검증 출력:

- `node --test tests/unit/test_linkedin_shadow_compare.mjs`: 3 passed
- `pytest tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q`: 7 passed

### 최종 판단

판정: `trial_fallback`

이유:

- OpenCLI 기반 전체 저장글 수집은 2회 모두 인증 차단 없이 끝까지 완료됐다.
- parser 성공률은 100%, 중복은 0건이다.
- 20건 수준이 아니라 현재 GraphQL 기준 전체 602건 수집이 가능했다.
- 반복 실행 간 ID 차이는 0건이다.
- 기존 기준 604건과 비교하면 기계적 diff로는 누락 후보 3건, shadow-only 1건이 있었다.
- 수동 확인 반영 후 확인된 OpenCLI 실제 누락은 0건이다.
- 불일치 3건은 삭제/비공개 또는 wrapper/original 매칭 문제로 재분류된다.
- media count 차이 후보 90건은 OpenCLI 접근층 문제가 아니라 media URL 선택/필터 로직 문제일 가능성이 높다.

권장안:

- 다음 단계는 `linkedin_scrap.py` 교체가 아니라 OpenCLI backend를 fallback 또는 shadow backend로 붙여 일정 기간 병행 운용한다.
- 기존 `storage_state` 방식이 로그인 실패할 때 OpenCLI backend를 사용하도록 붙이는 것이 전면 대체보다 안전하다.
- 전면 대체는 `SaveState` 기반 저장 대상 필터, wrapper/original canonical 매칭, media parser 보정 후 재비교한 뒤 결정한다.

### 남은 리스크

- `output_linkedin/opencli_shadow/` 결과는 검증 산출물이며 운영 데이터로 병합하지 않았다.
- 수동 상세 URL 클릭 검증은 템플릿만 만들었고, 실제 브라우저에서 30건을 모두 확인하지는 않았다.
- media count 차이는 90건으로 적지 않다. 다만 대표 raw 확인 결과 이미지 정보는 OpenCLI raw에 존재했고, `utils/linkedin_parser.py`의 whitelist가 `feedshare-image-high-res`, `shrink_800`, `shrink_1280` 계열 artifact를 걸러낸 것으로 보인다.
- OpenCLI network cache만으로는 page 후반부 응답을 안정적으로 잡기 어려워, 구현은 browser session 내부 `fetch()` pagination을 병행한다.

## 후속 도입판단 테스트 계획

작성 시각: 2026-07-07 KST

목적은 OpenCLI 접근층 자체 재검증이 아니라, OpenCLI 기반 LinkedIn 저장글 수집이 운영 대체 또는 fallback으로 들어갈 만큼 정규화 품질을 갖췄는지 판단하는 것이다.

### 후속 검증 가설

| 가설 | 판정 방법 | 통과 기준 |
|---|---|---|
| 현재 저장글 판정은 `EntityResultViewModel` 단독보다 GraphQL cluster reference + `SaveState` 기준이 정확하다 | `searchDashClustersByAll.elements[*].*entityResult`로 실제 결과 항목을 먼저 한정하고, raw `included`의 `SaveState:(SAVE,urn:li:activity:<id>)`와 post ID를 교차 검증 | ✅ shadow post 전부가 cluster reference와 SaveState activity ID 양쪽에 매칭 |
| 기존 수집 데이터에는 wrapper/original 중복 또는 stale 항목이 섞일 수 있다 | 기준 full의 activity ID를 현재 OpenCLI SaveState ID와 대조하고, 접근 불가/wrapper/original을 분류 | ✅ 단순 누락 후보를 `real_opencli_missing`으로 과잉 판정하지 않음 |
| media count 차이는 OpenCLI 접근층 문제가 아니라 parser 보정 문제다 | raw GraphQL image artifact와 parsed `media`를 비교 | ✅ media mismatch가 크게 감소하거나 남은 차이가 설명됨 |
| OpenCLI backend는 기존 인증 실패 시 fallback 접근층으로 쓸 수 있다 | 기존 `storage_state` 실패/만료 상황에서 OpenCLI persistent session으로 whoami와 saved posts 접근 확인 | ✅ 기존 실패 상황에서도 OpenCLI 수집 성공 |

### 후속 계획 검수 및 보완 사항

검수 결과, 기존 후속 계획에는 도입판단을 왜곡할 수 있는 크리티컬 보완점이 있었다. 아래 사항을 후속 구현의 필수 조건으로 반영한다.

| 이슈 | 위험 | 보완 |
|---|---|---|
| `SaveState`만으로 저장글 여부를 판단 | `included`에는 실제 검색 결과 외의 참조 객체가 섞일 수 있어, SaveState가 있더라도 저장목록 행과 1:1 대응한다고 단정하기 어렵다 | `searchDashClustersByAll.elements[*].*entityResult`가 참조한 `EntityResultViewModel`만 후보로 삼고, SaveState는 검증 조건으로 사용 |
| canonical 비교 기준이 모호함 | normalized JSON만 보면 wrapper/original 관계를 사후 추론하기 어렵고, 다시 `platform_id` 비교 오류가 반복될 수 있다 | shadow parse 단계에서 `saved_activity_id`, `entity_activity_id`, `embedded_activity_ids`, `canonical_activity_id`, `save_state_verified` 같은 진단 필드를 별도 metadata/report에 남김 |
| media 보정 기준이 "대폭 감소"로 모호함 | 실제 도입판단에서 media 손실을 과소평가할 수 있다 | 기존 90건 mismatch를 기준으로 `unexplained_media_mismatch <= 10` 또는 전건 원인 라벨링을 통과 기준으로 둠 |
| `utils/linkedin_parser.py` 수정 영향 범위가 큼 | 기존 Playwright/storage_state backend의 media 파싱 결과가 바뀌어 운영 데이터 품질에 영향을 줄 수 있다 | OpenCLI raw fixture와 기존 parser fixture를 모두 테스트하고, actor/profile/company logo가 post media로 섞이지 않는 regression test를 추가 |
| fallback 인증 실패 테스트가 파괴적일 수 있음 | 기존 auth 파일을 일부러 망가뜨리면 운영 수집 인증 상태를 깨뜨릴 수 있다 | 실제 auth 파일을 수정하지 않고, 임시 storage_state 경로/환경변수 또는 read-only 실패 로그 재현으로 fallback 조건만 검증 |

### 후속 Task 1: SaveState 기반 저장 대상 필터 추가

**Files:**
- Modify: `scripts/linkedin_opencli_shadow_parse.py`
- Modify: `scripts/linkedin_shadow_compare.mjs`
- Output: `output_linkedin/opencli_shadow/reports/save_state_audit_<timestamp>.json`

- [ ] **Step 1: raw GraphQL에서 cluster entityResult reference와 SaveState activity ID 추출**

Run:

```powershell
python scripts/linkedin_opencli_shadow_parse.py `
  --raw-dir output_linkedin/opencli_shadow/raw_full3 `
  --out output_linkedin/opencli_shadow `
  --require-save-state
```

Expected:

- 출력 metadata에 `cluster_entity_result_count`, `save_state_activity_count`, `entity_result_count`, `cluster_save_state_matched_post_count`, `entity_without_cluster_reference_count`, `entity_without_save_state_count` 포함
- `entity_without_save_state_count`가 있으면 별도 후보 파일로 저장

완료 기준:

- 저장글로 채택된 post는 모두 `searchDashClustersByAll.elements[*].*entityResult`가 참조한 `EntityResultViewModel`이다.
- 저장글로 채택된 post는 모두 `SaveState:(SAVE, activity)`에 포함된다.
- cluster reference 또는 `SaveState`에 없는 `EntityResultViewModel`은 운영 후보에서 제외된다.
- raw page별 `cluster_entity_result_count`, `save_state_activity_count`, `parsed_post_count` 차이가 리포트에 남는다.

### 후속 Task 2: wrapper/original canonical 매칭 비교

**Files:**
- Modify: `scripts/linkedin_shadow_compare.mjs`
- Output: `output_linkedin/opencli_shadow/reports/canonical_compare_<timestamp>.json`
- Output: `output_linkedin/opencli_shadow/reports/canonical_compare_<timestamp>.md`

- [ ] **Step 1: 기준 full과 shadow의 원문/wrapper 관계를 분류**

Run:

```powershell
node scripts/linkedin_shadow_compare.mjs canonical-compare `
  --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json `
  --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json `
  --total-full output_total/total_full_20260707.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- 리포트에 다음 분류가 포함된다.
  - `confirmed_saved_in_opencli`
  - `baseline_only_unreachable`
  - `baseline_only_wrapper`
  - `shadow_only_confirmed_saved`
  - `real_opencli_missing`
- shadow post별 진단 필드가 포함된다.
  - `saved_activity_id`
  - `entity_activity_id`
  - `embedded_activity_ids`
  - `canonical_activity_id`
  - `save_state_verified`
  - `cluster_reference_verified`

완료 기준:

- `7450664369769816064` 같은 wrapper ID는 `real_opencli_missing`이 아니라 `baseline_only_wrapper`로 분류된다.
- `real_opencli_missing`이 0건이거나, 각 건의 수동 확인 근거가 남는다.
- normalized JSON만으로 wrapper/original 관계를 추론할 수 없는 경우에는 `needs_raw_evidence`로 분리하고 자동 판정하지 않는다.

### 후속 Task 3: media parser 보정 및 재검증

**Files:**
- Modify: `utils/linkedin_parser.py`
- Add/Modify: parser unit tests
- Output: `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.json`

- [ ] **Step 1: OpenCLI raw image artifact 패턴 보정**

수정 후보:

- `feedshare-image-high-res`
- `shrink_800`
- `shrink_1280`
- `feedshare-` rootUrl + `image-high-res` segment
- `articleshare-shrink_`

완료 기준:

- 대표 ID `7417789055347863552`의 raw image가 parsed `media`에 1건 이상 들어간다.
- 기존 media mismatch 90건 중 설명 불가 mismatch가 10건 이하로 줄어들거나, 남은 전건에 원인 라벨이 붙는다.
- profile image, company logo 같은 actor 이미지가 post media로 섞이지 않는다.
- 기존 Playwright/storage_state GraphQL fixture의 media 결과가 퇴행하지 않는다.

- [ ] **Step 2: media 보정 후 shadow 재파싱 및 비교**

Run:

```powershell
python scripts/linkedin_opencli_shadow_parse.py `
  --raw-dir output_linkedin/opencli_shadow/raw_full3 `
  --out output_linkedin/opencli_shadow

node scripts/linkedin_shadow_compare.mjs compare `
  --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_<timestamp>.json `
  --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json `
  --total-full output_total/total_full_20260707.json `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- `media_count_mismatch`가 기존 90건보다 의미 있게 감소하고, `unexplained_media_mismatch <= 10`을 만족한다.
- 남는 media 차이는 representative sample에 원인 라벨이 붙는다.

- [ ] **Step 3: parser regression test 실행**

Run:

```powershell
pytest tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q
node --test tests/unit/test_linkedin_shadow_compare.mjs
```

Expected:

- 기존 parser unit test가 모두 통과한다.
- OpenCLI raw fixture 기반 media test가 추가되어 통과한다.
- profile image/company logo 오탐 방지 fixture가 통과한다.

### 후속 Task 4: 2일 이상 shadow 병행 안정성 확인

**Files:**
- Output: `output_linkedin/opencli_shadow/runs/YYYYMMDD/`
- Output: `output_linkedin/opencli_shadow/reports/multi_day_stability_<timestamp>.md`

- [ ] **Step 1: 최소 2일, 2회 이상 동일 로직 실행**

Run:

```powershell
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_dayN --out output_linkedin/opencli_shadow/runs/YYYYMMDD/raw --until-exhausted
python scripts/linkedin_opencli_shadow_parse.py --raw-dir output_linkedin/opencli_shadow/runs/YYYYMMDD/raw --out output_linkedin/opencli_shadow/runs/YYYYMMDD
```

완료 기준:

- 인증 차단 0건
- 반복 실행 간 현재 저장글 ID 차이는 실제 저장/삭제 변동으로 설명된다.
- `SaveState` 기준 총건수와 parsed post 수가 일치한다.

### 후속 Task 5: 비파괴 fallback 시나리오 검증

**Files:**
- Read: existing auth/status logs
- Output: `output_linkedin/opencli_shadow/reports/fallback_scenario_<timestamp>.md`

- [ ] **Step 1: 기존 auth 파일을 훼손하지 않는 방식으로 fallback 조건 검증**

Run:

```powershell
opencli linkedin whoami --site-session persistent -f json
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_fallback --out output_linkedin/opencli_shadow/fallback/raw --until-exhausted
```

완료 기준:

- 기존 `auth/` 또는 storage_state 파일을 수정하지 않는다.
- OpenCLI persistent session이 로그인 상태와 saved posts 접근을 통과한다.
- fallback 도입 시 트리거 조건은 "기존 backend가 `SNS_AUTH_REQUIRED` 또는 `login_required`로 실패한 경우"처럼 명시된다.

### 후속 Go / No-Go 기준

| 판정 | 조건 |
|---|---|
| `go` | cluster reference + SaveState 기준 저장글만 수집, 실제 OpenCLI 누락 0건, unexplained media mismatch 10건 이하 또는 전건 설명, 2회 이상 반복 안정 |
| `fallback_only` | 접근 안정성은 충분하지만 media/canonical 차이가 일부 남아 기존 backend 실패 시 대체 경로로만 사용 |
| `no_go` | SaveState 매칭 실패, 현재 저장글 실제 누락, 인증/GraphQL 불안정, media 유실 대량 지속 중 하나 발생 |

후속 검증 전제:

- 기존 `linkedin_py_full_*.json`과 `total_full_*.json`을 절대 정답으로 보지 않는다.
- 기준 데이터는 누적 병합 결과이므로 삭제/비공개/stale/wrapper 항목이 섞일 수 있다.
- 도입판단의 기준은 "기존 데이터와 1:1 일치"가 아니라 "현재 LinkedIn 저장목록의 SaveState와 안정적으로 일치"이다.

## 후속 테스트 실행 결과

실행 시각: 2026-07-07 15:27 KST

### 구현/보정 사항

- `scripts/linkedin_opencli_shadow_parse.py`
  - `searchDashClustersByAll.elements[*].*entityResult`가 참조한 `EntityResultViewModel`만 저장글 후보로 삼도록 보정했다.
  - `SaveState:(SAVE,urn:li:activity:<id>)`와 교차 검증하는 `--require-save-state` 옵션을 추가했다.
  - shadow post에 `diagnostics.saved_activity_id`, `entity_activity_id`, `canonical_activity_id`, `save_state_verified`, `cluster_reference_verified`를 남기도록 했다.
- `utils/linkedin_parser.py`
  - OpenCLI raw에서 확인된 `feedshare-image-high-res`, `feedshare-shrink_800`, `feedshare-shrink_1280` 계열 media artifact를 허용했다.
- `scripts/linkedin_shadow_compare.mjs`
  - `canonical-compare` 명령을 추가했다.
  - normalized JSON만으로 wrapper/original 관계를 판단할 수 없는 baseline-only 항목은 `real_opencli_missing`이 아니라 `needs_raw_evidence`로 분리했다.
- 테스트 추가/보정:
  - `tests/unit/test_linkedin_opencli_shadow_parse.py`
  - `tests/unit/test_linkedin_parser.py`
  - `tests/unit/test_linkedin_shadow_compare.mjs`

### 실행 산출물

- SaveState 보정 shadow: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json`
- 보정 비교 리포트: `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707152337.json`
- canonical 비교 리포트: `output_linkedin/opencli_shadow/reports/canonical_compare_20260707152714.json`
- fallback raw: `output_linkedin/opencli_shadow/fallback/raw/`
- fallback parsed: `output_linkedin/opencli_shadow/fallback/linkedin_opencli_shadow_20260707_152626.json`
- fallback 반복 비교: `output_linkedin/opencli_shadow/reports/compare_shadow_runs_20260707152633.json`

### 후속 테스트 결과 요약

| 검증 항목 | 결과 | 판정 |
|---|---:|---|
| cluster entityResult count | 602 | 통과 |
| SaveState activity count | 602 | 통과 |
| cluster + SaveState matched post | 602 | 통과 |
| entity without cluster reference | 0 | 통과 |
| entity without SaveState | 0 | 통과 |
| parsed post count | 602 | 통과 |
| duplicate platform_id | 0 | 통과 |
| parser failed | 0 | 통과 |
| fallback 수집 page | 62 | 통과 |
| fallback unique activity IDs | 602 | 통과 |
| fallback parsed post | 602 | 통과 |
| 보정 run vs fallback run ID 차이 | 0 | 통과 |
| canonical `real_opencli_missing` | 0 | 통과 |
| canonical `needs_raw_evidence` | 3 | 추가 확인 필요 |
| shadow-only confirmed candidate | 1 | 추가 확인 필요 |
| media mismatch before 보정 | 90건, 전부 `0 -> 1` | 기존 shadow media 누락 |
| media mismatch after 보정 | 138건, 전부 `1 -> 0` | 추가 확인 필요 |

### 해석

SaveState/cluster 검증은 강하게 통과했다. 즉 OpenCLI raw 안에서 실제 저장목록 결과로 참조된 602개 항목과 SaveState 602개가 정확히 맞고, 이 기준으로 파싱한 결과도 602건이다. fallback 재실행도 같은 602건을 반환했으므로 접근층과 저장 대상 필터의 안정성은 현재 기준 합격이다.

canonical 비교는 자동 판정 기준을 보수적으로 바꾼 뒤 `real_opencli_missing` 0건, `needs_raw_evidence` 3건으로 나왔다. 이 3건은 normalized 기준 데이터만으로는 삭제/비공개/wrapper 여부를 자동 판정할 수 없다는 뜻이다. 앞선 수동 확인에 따르면 2건은 현재 접근 불가, 1건은 wrapper/original 관계다.

media 보정은 기존의 `shadow_media_count: 0`, `baseline_media_count: 1` 90건을 해소했다. 대표 ID `7417789055347863552`는 OpenCLI parsed 결과에 `feedshare-image-high-res` media 1건이 정상 반영됐다. 다만 보정 후에는 반대로 `shadow_media_count: 1`, `baseline_media_count: 0` 138건이 발생했다. 샘플상 post 본문과 관련된 feedshare image로 보이나, 기존 기준 데이터가 media를 놓친 것인지 OpenCLI parser가 media를 과하게 잡은 것인지는 아직 전건 설명되지 않았다.

### 후속 도입판단

현재 판정: `fallback_only`

근거:

- OpenCLI 접근층, 전체 수집, SaveState 저장 대상 필터는 통과했다.
- 기존 `storage_state` 방식 실패 시 fallback 후보로 쓰기에는 충분하다.
- 다만 media mismatch가 `unexplained_media_mismatch <= 10` 기준을 아직 만족하지 못했다.
- canonical 자동 비교도 normalized 데이터만으로는 3건을 `needs_raw_evidence`로 남긴다.

전면 대체 전 남은 필수 확인:

- media mismatch 138건 중 대표 샘플 20건을 실제 LinkedIn 화면 또는 raw embedded object 기준으로 확인한다.
- `needs_raw_evidence` 3건은 수동 확인 결과를 machine-readable override 또는 raw evidence report로 남긴다.
- media 보정이 기존 Playwright/storage_state backend의 media 품질을 퇴행시키지 않는지 fixture를 더 보강한다.

### 실행한 검증 명령

```powershell
pytest tests/unit/test_linkedin_opencli_shadow_parse.py tests/unit/test_linkedin_parser.py -q
node --test tests/unit/test_linkedin_shadow_compare.mjs
python scripts/linkedin_opencli_shadow_parse.py --raw-dir output_linkedin/opencli_shadow/raw_full3 --out output_linkedin/opencli_shadow --require-save-state
node scripts/linkedin_shadow_compare.mjs compare --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json --total-full output_total/total_full_20260707.json --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_shadow_compare.mjs canonical-compare --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json --linkedin-full output_linkedin/python/linkedin_py_full_20260707.json --total-full output_total/total_full_20260707.json --out output_linkedin/opencli_shadow/reports
opencli linkedin whoami --site-session persistent -f json
node scripts/linkedin_opencli_shadow_collect.mjs --session linkedin_saved_shadow_fallback --out output_linkedin/opencli_shadow/fallback/raw --until-exhausted
python scripts/linkedin_opencli_shadow_parse.py --raw-dir output_linkedin/opencli_shadow/fallback/raw --out output_linkedin/opencli_shadow/fallback --require-save-state
node scripts/linkedin_shadow_compare.mjs compare-shadow-runs --a output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json --b output_linkedin/opencli_shadow/fallback/linkedin_opencli_shadow_20260707_152626.json --out output_linkedin/opencli_shadow/reports
pytest tests/unit/test_linkedin_opencli_shadow_parse.py tests/unit/test_linkedin_parser.py tests/unit/test_parsers.py -q
node --test tests/unit/test_linkedin_shadow_compare.mjs
```

## Media mismatch 138건 확인 계획

작성 시각: 2026-07-07 KST

**Goal:** media 보정 후 발생한 `shadow_media_count: 1`, `baseline_media_count: 0` 138건이 실제 게시글 media인지, actor/profile/company logo 오탐인지, 기존 기준 데이터의 media 누락인지 판정한다.

**Architecture:** 운영 데이터는 수정하지 않고, 보정 shadow 결과와 기존 full을 비교한 media mismatch 후보만 별도 audit JSON/MD로 만든다. raw GraphQL의 `entityEmbeddedObject.image`, `image`, `actor` 계열 위치를 분리해 자동 라벨링하고, 자동 판정이 어려운 대표 샘플만 실제 LinkedIn 화면으로 확인한다.

**Tech Stack:** Node.js `.mjs` audit script, existing shadow JSON, OpenCLI raw GraphQL, existing compare report, optional browser/manual spotcheck.

### Media Audit 파일 계획

생성 예정:

- `scripts/linkedin_media_audit.mjs`
  - media mismatch 후보 138건을 raw 위치와 URL 패턴 기준으로 라벨링한다.
- `tests/unit/test_linkedin_media_audit.mjs`
  - post media와 actor/profile/company logo를 구분하는 규칙을 fixture로 검증한다.
- `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.json`
  - 전체 138건의 자동 라벨링 결과.
- `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.md`
  - 도입판단용 요약 리포트.
- `output_linkedin/opencli_shadow/reports/media_spotcheck_sample_<timestamp>.json`
  - 수동 확인 대상 샘플.
- `output_linkedin/opencli_shadow/reports/media_spotcheck_<timestamp>.md`
  - 수동 확인 결과 기록.

수정 예정:

- 없음. 이 단계는 확인 계획이며, 추가 parser 수정은 audit 결과를 보고 별도 판단한다.

### Media Audit 판정 라벨

| 라벨 | 의미 | 도입판단 영향 |
|---|---|---|
| `post_media_confirmed` | raw의 `entityEmbeddedObject.image` 또는 본문 media 위치에서 나온 실제 게시글 media | OpenCLI media 보정 신뢰도 상승 |
| `baseline_missing_media` | OpenCLI는 실제 post media를 잡았고 기존 full이 media를 누락한 것으로 보이는 경우 | 기존 기준 데이터 품질 문제로 분류 |
| `actor_image_false_positive` | 작성자 프로필, 회사 로고, badge 이미지가 post media로 섞인 경우 | parser 보정 필요 |
| `article_or_link_thumbnail` | 링크/기사 preview thumbnail으로, 수집 대상으로 볼지 정책 결정이 필요한 경우 | 정책 결정 필요 |
| `needs_browser_check` | raw 위치만으로 실제 화면 표시 여부를 판단하기 어려운 경우 | 수동 확인 필요 |

### Media Task 1: Audit 스크립트 TDD

**Files:**
- Create: `tests/unit/test_linkedin_media_audit.mjs`
- Create: `scripts/linkedin_media_audit.mjs`

- [ ] **Step 1: post media와 actor image를 구분하는 실패 테스트 작성**

Run:

```powershell
node --test tests/unit/test_linkedin_media_audit.mjs
```

Expected before implementation:

```markdown
FAIL: classifyMediaSource is not exported
```

완료 기준:

- `entityEmbeddedObject.image.detailData.vectorImage`는 `post_media_confirmed`로 분류된다.
- `nonEntityProfilePicture`, `profilePicture`, `companyLogo` 경로는 `actor_image_false_positive`로 분류된다.
- `article-cover_image-shrink_`, `articleshare-shrink_`는 `article_or_link_thumbnail`로 분류된다.

- [ ] **Step 2: 최소 구현 후 테스트 통과**

Run:

```powershell
node --test tests/unit/test_linkedin_media_audit.mjs
```

Expected after implementation:

```markdown
pass
```

### Media Task 2: 138건 자동 라벨링

**Files:**
- Read: `output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707152337.json`
- Read: `output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json`
- Read: `output_linkedin/python/linkedin_py_full_20260707.json`
- Read: `output_linkedin/opencli_shadow/raw_full3/*.json`
- Output: `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.json`
- Output: `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.md`

- [ ] **Step 1: media mismatch 후보 라벨링 실행**

Run:

```powershell
node scripts/linkedin_media_audit.mjs audit `
  --compare-report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707152337.json `
  --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json `
  --baseline output_linkedin/python/linkedin_py_full_20260707.json `
  --raw-dir output_linkedin/opencli_shadow/raw_full3 `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- `media_audit_<timestamp>.json` 생성
- `media_audit_<timestamp>.md` 생성
- summary에 다음 값 포함
  - `total_mismatch`
  - `post_media_confirmed`
  - `baseline_missing_media`
  - `actor_image_false_positive`
  - `article_or_link_thumbnail`
  - `needs_browser_check`

완료 기준:

- 138건 전부 라벨이 붙는다.
- `actor_image_false_positive`가 0건이면 parser 오탐 리스크는 낮음으로 분류한다.
- `needs_browser_check`가 20건을 넘으면 자동 판정 기준을 보수적으로 조정한다.

### Media Task 3: 대표 샘플 수동 확인

**Files:**
- Read: `output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.json`
- Output: `output_linkedin/opencli_shadow/reports/media_spotcheck_sample_<timestamp>.json`
- Output: `output_linkedin/opencli_shadow/reports/media_spotcheck_<timestamp>.md`

- [ ] **Step 1: 라벨별 샘플 생성**

Run:

```powershell
node scripts/linkedin_media_audit.mjs sample `
  --audit output_linkedin/opencli_shadow/reports/media_audit_<timestamp>.json `
  --per-label 5 `
  --out output_linkedin/opencli_shadow/reports
```

Expected:

- 라벨별 최대 5건, 총 20건 내외 샘플 생성
- 각 샘플에 `platform_id`, `post_url`, `shadow_media_url`, `raw_path`, `label`, `text_excerpt` 포함

- [ ] **Step 2: 실제 화면 또는 raw 위치 기준으로 확인**

수동 확인 기준:

| 확인 항목 | 통과 기준 |
|---|---|
| 게시글 본문 이미지 | 화면 또는 raw `entityEmbeddedObject`에서 post content media로 확인 |
| actor/profile/company 이미지 | post media가 아니므로 false positive |
| link/article preview | 수집 정책에 따라 media 포함 여부 결정 |
| 기존 full media 0 | 기존 데이터 누락인지 확인 |

완료 기준:

- 샘플 20건 중 `actor_image_false_positive`가 1건 이하.
- `post_media_confirmed` 또는 `baseline_missing_media`가 대부분이면 OpenCLI media 보정은 유지한다.
- link/article preview를 media로 볼지 별도 정책 결정이 필요한 경우 문서에 명시한다.

### Media Task 4: 도입판정 반영

**Files:**
- Modify: `docs/20260707_04_LinkedIn-OpenCLI-shadow-수집-검증-수행계획.md`

- [ ] **Step 1: media audit 결과를 도입판정에 반영**

판정 기준:

| 판정 | 조건 |
|---|---|
| `go_candidate` | `actor_image_false_positive <= 1`, `needs_browser_check <= 10`, 샘플 확인에서 post media 오탐 1건 이하 |
| `fallback_only` | media 대부분은 설명되지만 link/article thumbnail 정책이 남아 있음 |
| `hold` | actor/profile/company logo 오탐이 반복되거나 media 정책 미정으로 품질 판단 불가 |

완료 기준:

- media 리스크가 `낮음`, `중간`, `높음` 중 하나로 명시된다.
- OpenCLI 전면 대체 가능 여부가 media 근거와 함께 업데이트된다.
- 전면 대체를 보류한다면 남은 확인 항목이 10건 이하로 줄어든다.

### Media Audit 수행 결과

수행 시각: 2026-07-07 KST

생성 파일:

- `scripts/linkedin_media_audit.mjs`
- `tests/unit/test_linkedin_media_audit.mjs`
- `output_linkedin/opencli_shadow/reports/media_audit_20260707154823.json`
- `output_linkedin/opencli_shadow/reports/media_audit_20260707154823.md`
- `output_linkedin/opencli_shadow/reports/media_spotcheck_sample_20260707154828.json`
- `output_linkedin/opencli_shadow/reports/media_spotcheck_20260707154828.md`

검증 명령:

```powershell
node --test tests/unit/test_linkedin_media_audit.mjs
node scripts/linkedin_media_audit.mjs audit --compare-report output_linkedin/opencli_shadow/reports/linkedin_opencli_shadow_compare_20260707152337.json --shadow output_linkedin/opencli_shadow/linkedin_opencli_shadow_20260707_152327.json --baseline output_linkedin/python/linkedin_py_full_20260707.json --raw-dir output_linkedin/opencli_shadow/raw_full3 --out output_linkedin/opencli_shadow/reports
node scripts/linkedin_media_audit.mjs sample --audit output_linkedin/opencli_shadow/reports/media_audit_20260707154823.json --per-label 5 --out output_linkedin/opencli_shadow/reports
```

결과:

| 항목 | 값 |
|---|---:|
| total_mismatch | 138 |
| post_media_confirmed | 138 |
| baseline_missing_media | 0 |
| actor_image_false_positive | 0 |
| article_or_link_thumbnail | 0 |
| needs_browser_check | 0 |

추가 집계:

| 항목 | 값 |
|---|---:|
| raw 경로가 `entityEmbeddedObject.image`인 후보 | 138 |
| media URL이 `feedshare-image-high-res`인 후보 | 138 |
| spotcheck 샘플 수 | 5 |

판정:

| 판정 항목 | 결과 |
|---|---|
| recommendation | `go_candidate` |
| media_risk | `낮음` |
| reason | media 오탐 리스크가 기준 이하임 |

해석:

- `OpenCLI가 media를 더 잡는 138건`은 모두 raw GraphQL의 `entityEmbeddedObject.image.attributes[0].detailData.vectorImage.digitalmediaAsset` 계열에서 확인됐다.
- actor/profile/company logo 오탐으로 분류된 건은 0건이다.
- link/article thumbnail 정책 이슈로 분류된 건도 0건이다.
- 따라서 이번 138건 차이는 OpenCLI parser 오탐이라기보다, 기존 기준 데이터가 `feedshare-image-high-res` 본문 이미지를 media로 보존하지 못한 차이로 보는 것이 합리적이다.
- media 기준으로는 OpenCLI 전면 대체를 막을 리스크는 현재 확인되지 않았다.

남은 리스크:

- 이 audit는 raw GraphQL 경로 기준 확인이다. 실제 브라우저 화면 수동 확인은 수행하지 않았다.
- 다만 138건 전부가 본문 media 경로로 확인되어, 수동 화면 확인이 필요한 후보는 0건으로 줄었다.

## 자체 검수

- 범위 확인: 사용자가 요청한 "모든 저장게시글 수집"과 "기존 scrap_sns 수집내역과 품질·누락 비교"를 포함했다.
- 안전성 확인: 운영 수집 결과 디렉토리에는 쓰지 않고 `output_linkedin/opencli_shadow/`만 사용한다.
- 완료 기준 확인: 각 Task에 완료 기준과 검증 명령을 포함했다.
- 위험 확인: 최신 기준 데이터가 stale일 수 있으므로 누락 후보와 신규 후보를 분리했다.
- 후속 실행 기준: shadow 검증 통과 전에는 `linkedin_scrap.py` 교체를 금지했다.
