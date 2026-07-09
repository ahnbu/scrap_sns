# linkedin-opencli-owned-window - Work Plan

## TL;DR (For humans)
**What you'll get:** LinkedIn 저장글 수집이 사용자 Chrome 창을 오염시키지 않도록, 수집 전용 Chrome 창을 따로 열고 그 창에 OpenCLI를 연결하는 구조로 바꾼다. 완료 기준은 코드 테스트가 아니라 실제 SNS Scrap update 후 수집용 창이 닫히고 뷰어에 결과가 반영되는 것이다.

**Why this approach:** 이전 테스트에서 OpenCLI의 `browser close`는 실제 Chrome 창 종료가 아니라 session tab lease 해제에 가깝다는 점이 확인됐다. 그래서 창 생성·종료는 Windows window handle 기준으로 Python이 맡고, OpenCLI는 이미 열린 창에 `bind`해서 읽기만 하도록 역할을 분리한다.

**What it will NOT do:** LinkedIn parser, Post schema, `total_scrap.py` 병합 규칙, Threads/X 수집 흐름은 바꾸지 않는다. 기존 LinkedIn metadata key는 호환성을 위해 유지하고, 과거 출력 파일 재처리는 하지 않는다. `--max-pages 1`에서 2페이지가 수집되는 pagination prefetch 동작도 이번 작업의 수정 대상이 아니다.

**Effort:** Medium
**Risk:** Medium - Windows Chrome window handle, OpenCLI bind, cleanup 실패 경로가 얽힌다.
**Decisions to sanity-check:** production 기본 경로를 owned-window + bound-session으로 전환한다. 기존 OpenCLI `open --window background` 경로는 fallback으로 유지하지 않는다. OpenCLI daemon은 작업 전 상태로 되돌리는 정책을 쓴다.

Your next move: approve execution with `$start-work` or ask for the dual high-accuracy review first. Full execution detail follows below.

---

> TL;DR (machine): Medium-risk integration plan to make LinkedIn collection use a Python-owned Chrome window handle and OpenCLI bound-session collection, with tests and real viewer QA.

## Scope
### Must have
- `linkedin_scrap.py` opens `https://www.linkedin.com/my-items/saved-posts/` in a dedicated Chrome `--new-window`, records the window `Hwnd`, focuses that window, and runs `opencli browser linkedin_saved_production bind`.
- `Hwnd` identification is deterministic: capture baseline visible Chrome top-level HWNDs, launch Chrome `--new-window`, poll for exactly one new visible Chrome HWND, and record an owned handle only when the baseline diff has exactly one candidate. If there are 0 or 2+ candidates, fail without closing any Chrome window. Only a handle already recorded as owned may receive `WM_CLOSE`.
- `linkedin_scrap.py` replaces `whoami --site-session persistent` with bound-window validation using OpenCLI browser state or eval against the dedicated saved-posts window.
- `run_opencli_collector()` passes `--use-bound-session` to `scripts/linkedin_opencli_shadow_collect.mjs` in production.
- `scripts/linkedin_opencli_shadow_collect.mjs` keeps `--use-bound-session`, but no longer runs session cleanup in its `finally` when the session was provided by an external owner.
- Python owns the final cleanup order: `unbind -> close -> daemon stop -> Hwnd`.
- Cleanup is attempted on success and failure, including Chrome path failure after launch attempt, open failure, HWND identification failure, focus failure, bind failure, bound-window validation failure, collector failure, parse failure, and payload validation failure.
- Cleanup preserves the original error while recording cleanup failures separately.
- OpenCLI daemon handling returns to baseline: if it was not running before the run and `SCRAP_SNS_KEEP_OPENCLI_DAEMON != 1`, stop it; if it was already running before the run or keep env is set, release only this browser session and do not stop the daemon.
- Tests pin the old behavior before changing it, then prove the new behavior:
  - owned-window helper opens/focuses/closes the intended window handle
  - collector command includes `--use-bound-session`
  - `whoami --site-session persistent` is no longer called in production
  - Python cleanup attempts OpenCLI cleanup, daemon stop, and window close in order
  - Node collector does not close externally bound sessions
- Real-surface QA proves:
  - LinkedIn-only update succeeds
  - full SNS Scrap update succeeds
- `SNS Feed Viewer - Chrome` remains open
  - LinkedIn collection window closes
  - OpenCLI daemon is not running unless `SCRAP_SNS_KEEP_OPENCLI_DAEMON=1`
  - latest LinkedIn upstream full file, latest total file, and viewer count/search agree

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Must-NOT-Have: no changes to LinkedIn parser semantics in `utils/linkedin_parser.py`.
- Must-NOT-Have: no changes to Post schema ordering or durable identity rules in `utils/post_schema.py`.
- Must-NOT-Have: no rename/removal of existing LinkedIn output metadata keys such as `opencli_logged_in`, `opencli_site`, `opencli_public_id`; compatibility keys may be populated from bound-window validation instead of `whoami`.
- Must-NOT-Have: no broad refactor of `total_scrap.py`, viewer UI, Threads, or X.
- Must-NOT-Have: no raw deletion of user data or output files. Preserve pre-existing dirty files unless a verification command intentionally regenerates them.
- Must-NOT-Have: no process kill beyond the scoped `scrap_sns_server.py` launcher behavior or the owned LinkedIn collection window handle.
- Must-NOT-Have: do not use `.sh`; use Python or `.mjs` for any helper logic.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD for behavior seams in Python and Node, plus real-surface QA for browser/OpenCLI/user-visible behavior.
- Failing-first rule:
  - Write characterization tests that pass on current cleanup behavior before changing it.
  - Write new tests for owned-window/bound-session behavior and capture RED before implementation.
  - Do not edit production code before the relevant RED evidence exists.
- Core test commands:
  - `node --check scripts/linkedin_opencli_shadow_collect.mjs`
  - `pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py`
  - `pytest tests/unit`
  - `pytest tests/contract`
  - `node utils/query-sns.mjs --help`
- Real-surface commands:
  - `python linkedin_scrap.py --mode update`
  - `python total_scrap.py --mode update`
  - `npm run view`
  - Playwright/Chrome verification against `http://localhost:5000/`
- Dirty worktree and output safety:
  - Before editing overlap files, save `git diff -- <path>` evidence for `scripts/linkedin_opencli_shadow_collect.mjs`, `tests/unit/test_opencli_cleanup.py`, and any other dirty target.
  - Before full update QA, save `git status --short` and output-file diffs/counts because `total_scrap.py --mode update` may regenerate outputs or trigger old-output cleanup.
- Evidence directory:
  - `.omo/evidence/linkedin-opencli-owned-window/`
  - Store command transcripts as `.txt` or `.json`
  - Store viewer screenshots as `.png`
  - Store cleanup receipts as `.txt`

## Execution strategy
### Parallel execution waves
- Wave 1: Pin current behavior and introduce tests for new orchestration seams.
- Wave 2: Implement Python owned-window orchestration and Node external-session cleanup split.
- Wave 3: Run unit/integration verification and fix only issues caused by this change.
- Wave 4: Run LinkedIn-only real-surface QA.
- Wave 5: Run full SNS Scrap update + viewer QA.
- Wave 6: Final review, dirty-worktree audit, and commit preparation if requested.
- Rollback: no runtime fallback is added. If production QA fails after merge, rollback is `git revert <source commit>` plus rerun of LinkedIn-only and viewer QA.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| T1 | none | T4, T5 | T2 |
| T2 | none | T4 | T1 |
| T3 | none | T7 | T1, T2 |
| T4 | T1, T2 | T5, T6 | none |
| T5 | T4 | T7, T8 | T6 |
| T6 | T4 | T7, T8 | T5 |
| T7 | T3, T5, T6 | T8, T9 | none |
| T8 | T7 | T9 | none |
| T9 | T8 | T10 | none |
| T10 | T9 | final | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->

- [x] T1. Pin existing OpenCLI cleanup and production collector command behavior
  What to do / Must NOT do: Add or update tests only. Pin the current production command shape in `linkedin_scrap.py` and existing cleanup order in `collect_opencli_posts()`. Do not change production code in this todo.
  Parallelization: Wave 1 | Blocked by: none | Blocks: T4, T5
  References: `linkedin_scrap.py:116-140`, `linkedin_scrap.py:157-188`, `tests/integration/test_linkedin_opencli_pipeline.py:112-217`, `tests/unit/test_opencli_cleanup.py:4-12`
  Acceptance criteria: RED/GREEN characterization is captured. Existing cleanup tests still pass before implementation.
  QA scenarios:
  - Happy: `pytest tests/integration/test_linkedin_opencli_pipeline.py::test_collect_opencli_posts_cleans_browser_session_before_daemon_stop tests/integration/test_linkedin_opencli_pipeline.py::test_cleanup_opencli_browser_session_attempts_close_after_unbind_failure -q` -> PASS if both tests pass. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t1-characterization-green.txt`
  - Failure QA: Temporarily add the future assertion that production uses `--use-bound-session`; run `pytest tests/integration/test_linkedin_opencli_pipeline.py -q` before implementation -> PASS for this QA if it fails specifically because the flag is absent. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t1-bound-session-red.txt`
  Commit: N | included with implementation commit

- [x] T2. Add Node collector tests for externally owned bound sessions
  What to do / Must NOT do: Update `tests/unit/test_opencli_cleanup.py` so the script is expected to keep OpenCLI cleanup for internally opened sessions but skip `closeBrowserSession(activeSession)` when `--use-bound-session` is used. Static source-string assertions are not enough: add a minimal command-runner seam, dry-run log, or subprocess stub path so the test proves command behavior. Do not remove the existing no `tab close` assertion.
  Parallelization: Wave 1 | Blocked by: none | Blocks: T4
  References: `scripts/linkedin_opencli_shadow_collect.mjs:192-197`, `scripts/linkedin_opencli_shadow_collect.mjs:385-390`, `tests/unit/test_opencli_cleanup.py:4-12`
  Acceptance criteria: The new test fails before implementation because the script currently calls `closeBrowserSession(activeSession)` unconditionally in `finally`.
  QA scenarios:
  - Happy: `pytest tests/unit/test_opencli_cleanup.py -q` after implementation -> PASS if the test suite confirms both internally owned cleanup and externally bound non-cleanup behavior. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t2-node-cleanup-green.txt`
  - Failure QA: `pytest tests/unit/test_opencli_cleanup.py -q` before implementation -> PASS for this QA if it fails on the externally bound cleanup assertion. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t2-node-cleanup-red.txt`
  Commit: N | included with implementation commit

- [x] T3. Audit dirty worktree before implementation
  What to do / Must NOT do: Record `git status --short` and classify unrelated existing changes. For every dirty file this task will edit, save `git diff -- <path>` before editing and record how the new diff is separated from pre-existing changes. Do not revert, restage, or overwrite user/other-agent data changes.
  Parallelization: Wave 1 | Blocked by: none | Blocks: T7
  References: project rule "same repo may have parallel work"; current dirty files include output JSON, `scripts/linkedin_opencli_shadow_collect.mjs`, `tests/unit/test_opencli_cleanup.py`, `web_viewer/sns_tags.json`, `_docs/`, `.omo/`
  Acceptance criteria: Evidence file lists pre-existing dirty paths and marks which paths are allowed for this task.
  QA scenarios:
  - Happy: `git status --short > .omo/evidence/linkedin-opencli-owned-window/t3-git-status-before.txt; git diff -- scripts/linkedin_opencli_shadow_collect.mjs tests/unit/test_opencli_cleanup.py > .omo/evidence/linkedin-opencli-owned-window/t3-overlap-diff-before.patch` -> PASS if both files exist and overlap paths are classified. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t3-git-status-before.txt`, `.omo/evidence/linkedin-opencli-owned-window/t3-overlap-diff-before.patch`
  - Failure QA: If implementation wants to edit any additional dirty file, first save `git diff -- <path>` and record why the edit is necessary. PASS if the evidence names the overlap. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t3-overlap-decision.txt`
  Commit: N

- [x] T4. Implement Node collector ownership split
  What to do / Must NOT do: In `scripts/linkedin_opencli_shadow_collect.mjs`, derive `ownsBrowserSession = !useBoundSession`. Only call `browser(session, ["open", url, "--window", "background"])`, `wait(session, 5)`, and `closeBrowserSession(activeSession)` when `ownsBrowserSession` is true. Keep `--use-bound-session` behavior for the already-bound session. Do not add fallback browser opening inside bound mode.
  Parallelization: Wave 2 | Blocked by: T1, T2 | Blocks: T5, T6
  References: `scripts/linkedin_opencli_shadow_collect.mjs:183-197`, `scripts/linkedin_opencli_shadow_collect.mjs:380-390`, `_docs/20260709_01_OpenCLI-창관리-분리-테스트.md` section 9.2
  Acceptance criteria: `node --check scripts/linkedin_opencli_shadow_collect.mjs` passes and `pytest tests/unit/test_opencli_cleanup.py -q` passes.
  QA scenarios:
  - Happy: `node --check scripts/linkedin_opencli_shadow_collect.mjs && pytest tests/unit/test_opencli_cleanup.py -q` -> PASS if exit code is 0. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t4-node-green.txt`
  - Failure QA: Run the RED from T2 before implementation and confirm it fails for unconditional cleanup, not syntax or import errors. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t4-node-red.txt`
  Commit: N unless explicitly requested; use cp skill only | suggested message `fix(linkedin): 분리된 OpenCLI bound-session cleanup 적용 — 수집용 창 오염 방지`

- [x] T5. Implement Python owned Chrome window lifecycle
  What to do / Must NOT do: In `linkedin_scrap.py`, add minimal Windows-only helpers near the OpenCLI helper section:
  - resolve Chrome executable from `C:/Program Files/Google/Chrome/Application/chrome.exe` then `C:/Program Files (x86)/Google/Chrome/Application/chrome.exe`
  - if Chrome is not found, fail before OpenCLI bind with an actionable error and no daemon/session side effects
  - capture baseline visible Chrome top-level HWNDs before launch
  - open a dedicated `--new-window` saved-posts URL
  - poll for exactly one new visible Chrome top-level HWND
  - if 0 or 2+ candidates appear, record candidate title/HWND/process info to evidence, preserve the original error, and stop before bind without closing any Chrome window
  - record `owned_hwnd` only after exactly one candidate is confirmed
  - focus that recorded window immediately before `opencli browser linkedin_saved_production bind`
  - immediately after bind, run OpenCLI state/eval validation for `location.href` and title/text; if it is not the saved-posts page, run cleanup and fail
  - close only that recorded `Hwnd` with `WM_CLOSE`
  - make close idempotent and log failure without suppressing the original collection error
  Do not close `SNS Feed Viewer - Chrome`.
  Parallelization: Wave 2 | Blocked by: T4 | Blocks: T7, T8
  References: `linkedin_scrap.py:37-113`, `_docs/20260709_01_OpenCLI-창관리-분리-테스트.md` sections 4, 7, 9.3-9.5
  Acceptance criteria: Python tests prove the helper calls are ordered, `owned_hwnd` is recorded only when the baseline diff has exactly one new visible Chrome window, ambiguous candidates are logged but not closed, and only an already recorded owned handle receives `WM_CLOSE`. No product code uses raw process kill for Chrome.
  QA scenarios:
  - Happy: `pytest tests/integration/test_linkedin_opencli_pipeline.py -q` -> PASS if owned-window lifecycle tests pass. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t5-python-window-green.txt`
  - Failure QA: Before implementation, tests cover Chrome path missing, 0 HWND candidates, 2+ HWND candidates, focus failure, bind failure, validation failure, collector failure, parse failure, and payload validation failure. PASS for the RED proof if these fail because helper/lifecycle behavior is absent, then GREEN if 0/2+ HWND candidate cases preserve the original error, write candidate title/HWND/process info to evidence, and do not send `WM_CLOSE`; later failure paths send `WM_CLOSE` only when `owned_hwnd` was already recorded. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t5-python-window-red.txt`
  Commit: N unless explicitly requested; use cp skill only | suggested message `fix(linkedin): Chrome 수집창 수명주기를 Python에서 관리 — 사용자 창 보호`

- [x] T6. Replace persistent whoami with bound-window login/page validation
  What to do / Must NOT do: Remove production dependency on `run_opencli_whoami()` inside `collect_opencli_posts()`. Add a bound-session validation function that uses `opencli browser <session> state` or `eval` after bind and fails unless the page is the LinkedIn saved-posts page with title/text containing `저장한 게시물` or `Saved`. Preserve existing output metadata keys for compatibility: keep `opencli_logged_in`, `opencli_site`, and `opencli_public_id` in the saved metadata shape; populate them from bound-window validation (`opencli_public_id` may be null/empty if not discoverable). No historical `output_linkedin/python/linkedin_py_full_*.json` reprocessing is required. Do not weaken parse validation in `validate_opencli_payload()`.
  Parallelization: Wave 2 | Blocked by: T4 | Blocks: T7, T8
  References: `linkedin_scrap.py:65-82`, `linkedin_scrap.py:157-184`, `linkedin_scrap.py:386-402`, `_docs/20260709_01_OpenCLI-창관리-분리-테스트.md` section 9.5
  Acceptance criteria: Tests prove `run_opencli_whoami()` is not called in production and existing metadata keys are still present. If bound validation detects login/authwall/checkpoint or cannot confirm saved-posts due auth, return `AUTH_REQUIRED_EXIT_CODE` so `total_scrap.py` reports `auth_required`; otherwise use the existing nonzero failure path.
  QA scenarios:
  - Happy: `pytest tests/integration/test_linkedin_opencli_pipeline.py -q` -> PASS if no test requires persistent whoami and metadata assertions pass. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t6-bound-validation-green.txt`
  - Failure QA: Before implementation, a test that monkeypatches `run_opencli_whoami()` to raise but provides valid bound-window state fails because production still calls whoami; a second test with authwall/checkpoint state fails until `AUTH_REQUIRED_EXIT_CODE` is mapped. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t6-whoami-red.txt`
  Commit: N unless explicitly requested; use cp skill only | suggested message `fix(linkedin): bound 창 상태로 로그인 검증 대체 — persistent whoami 제거`

- [x] T7. Run focused automated verification
  What to do / Must NOT do: Run focused tests and syntax checks. Fix only failures caused by T4-T6. Do not broaden cleanup or refactor unrelated code.
  Parallelization: Wave 3 | Blocked by: T3, T5, T6 | Blocks: T8, T9
  References: `README.md` test section, `docs/crawling_logic.md` verification points
  Acceptance criteria: Focused checks pass with transcripts.
  QA scenarios:
  - Happy: `node --check scripts/linkedin_opencli_shadow_collect.mjs; pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q; node utils/query-sns.mjs --help` -> PASS if all exit 0 and help output prints usage. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t7-focused-green.txt`
  - Failure QA: If any check fails, save the first failing transcript and fix only the implicated change. PASS when the rerun transcript is green. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t7-failure-rerun.txt`
  Commit: N
  Ledger: 2026-07-09 17:46 KST focused automated verification passed. Commands: `node --check scripts/linkedin_opencli_shadow_collect.mjs` -> 0; `python -m py_compile linkedin_scrap.py` -> 0; `pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q` -> 0, 22 passed; `node utils/query-sns.mjs --help` -> 0. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t7-focused-green.txt`. Cleanup receipt: no runtime resource spawned; no LinkedIn, Chrome, OpenCLI, or viewer QA was run in T7.

- [x] T8. Run LinkedIn-only real-surface QA
  What to do / Must NOT do: Start from a clean baseline: record OpenCLI daemon status, `opencli browser linkedin_saved_production tab list`, and Chrome top-level windows. Run `python linkedin_scrap.py --mode update`. Verify upstream LinkedIn full output is updated and cleanup leaves no LinkedIn collection window. Daemon PASS condition is "returned to baseline", not always "not running". Do not count this as complete if only CLI tests pass.
  Parallelization: Wave 4 | Blocked by: T7 | Blocks: T9
  References: `README.md` LinkedIn verification command, `_docs/20260709_01_OpenCLI-창관리-분리-테스트.md` sections 9.3-9.6, `docs/development.md` LinkedIn output surface
  Acceptance criteria: Transcript shows collection success, no OpenCLI daemon unless explicitly kept, and only user-intended Chrome windows remain.
  QA scenarios:
  - Happy: `python linkedin_scrap.py --mode update` with pre/post status captures -> PASS if exit 0, latest `output_linkedin/python/linkedin_py_full_YYYYMMDD.json` contains posts, OpenCLI cleanup receipt includes `unbind -> close -> daemon stop -> Hwnd` when daemon was started by this run or `unbind -> close -> Hwnd` when daemon pre-existed/keep env is active, daemon status returns to baseline, and `SNS Feed Viewer - Chrome` is not closed. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t8-linkedin-update-green.txt`
  - Failure QA: Temporarily force bound-window validation to see a non-saved page in a controlled test or monkeypatched integration test -> PASS if cleanup still closes the owned Hwnd and stops/keeps daemon according to env. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t8-cleanup-failure-path.txt`
  Commit: N

- [x] T9. Run full SNS Scrap update and viewer QA
  What to do / Must NOT do: Run the full update path after LinkedIn-only success. Before running, save `git status --short`, output-file counts/diffs, and note that `total_scrap.py --mode update` may run old-output cleanup. Regenerate/verify latest total output, restart viewer using the project launcher, and inspect the actual page. Do not infer viewer success from JSON only. If bind validation fails only under full pipeline and evidence indicates foreground focus race, stop and revise the plan before changing `total_scrap.py`; do not add ad hoc serialization.
  Parallelization: Wave 5 | Blocked by: T8 | Blocks: T10
  References: `README.md` crawling and viewer sections, `docs/crawling_logic.md` full flow, project rule requiring real `http://localhost:5000/` screen verification for viewer-impacting changes
  Acceptance criteria: latest total file count and viewer top count agree; LinkedIn posts are searchable; no OpenCLI debug banner or stray LinkedIn tab/window remains.
  QA scenarios:
  - Happy: `python total_scrap.py --mode update`, then `npm run view`, then Playwright opens `http://localhost:5000/`, records top count, searches `linkedin`, and screenshots the result. PASS if viewer count equals latest total JSON post count and no collection window remains. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t9-viewer-green.txt` and `.omo/evidence/linkedin-opencli-owned-window/t9-viewer.png`
  - Failure QA: If viewer count differs, capture latest `output_total/total_full_YYYYMMDD.json` path/count, API `/api/posts` count, visible card count, and active filters before fixing. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t9-viewer-mismatch.txt`
  Commit: N

- [x] T10. Final audit and commit preparation
  What to do / Must NOT do: Re-read `git status --short`, list changed files by concern, run security gate before any commit if the user asks for commit, and prepare one concern-scoped commit message. Do not commit unless explicitly requested; if committing, use the `cp` skill, not raw `git add/commit`.
  Parallelization: Wave 6 | Blocked by: T9 | Blocks: final
  References: Git rules in project instructions, security gate rule, cp skill requirement
  Acceptance criteria: Final report separates changed source/tests/docs from regenerated output files and states which files were intentionally left unstaged or uncommitted.
  QA scenarios:
  - Happy: `git status --short` and, if commit requested, `node C:/Users/ahnbu/.claude/skills/_shared/security-gate.mjs precommit --repo D:/vibe-coding/scrap_sns --staged` -> PASS if no unexpected files are included. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t10-final-status.txt`
  - Failure QA: If security gate flags secrets or unexpected external transfer/install patterns, stop and ask the user with the exact flagged category redacted for secrets. Evidence: `.omo/evidence/linkedin-opencli-owned-window/t10-security-gate.txt`
  Commit: N unless explicitly requested; use cp skill only | suggested message `fix(linkedin): OpenCLI 수집창 수명주기 분리 — 사용자 Chrome 오염 방지`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit: verify every todo has references, acceptance criteria, happy QA, failure QA, and evidence path.
- [ ] F2. Code quality review: inspect diff for over-broad refactor, `as any`-style suppression equivalents, hidden fallback complexity, and unrelated edits.
- [ ] F3. Real manual QA: verify evidence from LinkedIn-only update, full update, and viewer screenshot exists and matches the success criteria.
- [ ] F4. Scope fidelity: verify no parser/schema/Threads/X/viewer feature changes were introduced.

## Commit strategy
- Default: no commit in the execution turn unless the user explicitly asks.
- If committing is requested, use `cp` skill only.
- One logical source/test commit:
  - `fix(linkedin): OpenCLI 수집창 수명주기 분리 — 사용자 Chrome 오염 방지`
- Do not mix regenerated output JSON or viewer state JSON into the source commit unless they are required evidence and the user approves including data changes.
- If a docs-only update is added later, use a separate docs commit.

## Success criteria
- `scripts/linkedin_opencli_shadow_collect.mjs` no longer closes externally bound sessions when `--use-bound-session` is active.
- `linkedin_scrap.py` owns the collection window lifecycle, identifies the new visible Chrome `Hwnd` by baseline-diff polling only when there is exactly one candidate, leaves ambiguous candidates open, and closes only the recorded LinkedIn collection `Hwnd`.
- Production LinkedIn collection uses `--use-bound-session` and does not depend on `whoami --site-session persistent`.
- Cleanup attempts are observable in order: `unbind -> close -> daemon stop -> Hwnd` when the daemon is owned by the run, or `unbind -> close -> Hwnd` when the daemon pre-existed or keep env is active.
- Focused tests pass:
  - `node --check scripts/linkedin_opencli_shadow_collect.mjs`
  - `pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q`
  - `node utils/query-sns.mjs --help`
- Real-surface QA passes:
  - `python linkedin_scrap.py --mode update`
  - `python total_scrap.py --mode update`
  - actual viewer at `http://localhost:5000/` shows the latest total count and searchable LinkedIn results
- No `SNS Feed Viewer - Chrome` window is closed by the collection flow.
- No LinkedIn collection window or OpenCLI debug banner remains after successful update.
