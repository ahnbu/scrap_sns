# linkedin-opencli-collection-surface - Work Plan

## TL;DR (For humans)
**What you'll get:** LinkedIn 수집이 사용자 SNS Scrap Chrome 창을 직접 오염시키지 않도록 수집 표면을 분리하고, 수집 완료/실패 후 그 수집 표면과 OpenCLI 디버깅 연결을 정리하는 수정입니다. 최종 사용자 기준은 “SNS Scrap 창 상단에 OpenCLI 디버깅 배너가 남지 않는다”입니다.

**Why this approach:** 기존 Playwright 방식은 별도 브라우저 창을 열고 닫았지만, OpenCLI 도입 후 `open --window background`로 바뀌며 별도 창/종료 보장이 사라졌습니다. 따라서 단순 `unbind/close/daemon stop`이 아니라, OpenCLI가 연 collection-owned target을 정확히 추적하고 닫는 수명주기 복원이 필요합니다.

**What it will NOT do:** 사용자 SNS Scrap 탭을 닫지 않습니다. Chrome 탭을 URL/제목으로 찾아 닫지 않습니다. LinkedIn 파서, 병합, 이미지, 태그 정책은 건드리지 않습니다.

**Effort:** Medium
**Risk:** High - 실제 Chrome/OpenCLI 표면을 다루므로 잘못 구현하면 사용자 탭을 닫거나 배너를 다시 남길 수 있습니다.
**Decisions to sanity-check:** “사용자 Chrome에 LinkedIn 탭이 없다”를 직접 기준으로 삼지 않고, “OpenCLI collection-owned target 정리 + 사용자 SNS Scrap 창 배너 제거”를 기준으로 삼습니다.

Your next move: 이 계획으로 구현을 시작하거나, 구현 전에 별도 고정밀 검수를 요청하세요. Full execution detail follows below.

---

> TL;DR (machine): Medium effort, high risk browser-integration fix; restore OpenCLI LinkedIn collection target lifecycle and verify no user-window debug banner remains.

## Scope
### Must have
- Restore the collection surface lifecycle that was lost when LinkedIn moved from Playwright to OpenCLI.
- Capture the `page` targetId returned by `opencli browser linkedin_saved_production open <url> --window background`.
- Close only that collection-owned target with `opencli browser linkedin_saved_production tab close <targetId>` in `finally`.
- Run target cleanup before `unbind -> close -> daemon stop`.
- Preserve cleanup on success, parser failure, OpenCLI command failure, and daemon-stop-disabled mode.
- Verify from the real user surface that the SNS Scrap Chrome window has no OpenCLI debugging banner after the run.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not close SNS Scrap tab.
- Do not close arbitrary Chrome tabs/windows.
- Do not close tabs by URL/title matching.
- Do not use `taskkill`, Alt+F4, PowerShell window close, or OS-level Chrome termination as the product fix.
- Do not treat `opencli daemon status == not running` as sufficient completion proof.
- Do not change LinkedIn parser semantics, saved-post merge rules, image download policy, tag sync, or output JSON schema.
- Do not revert or overwrite current dirty output data created by user reruns.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD. Capture RED first with the cheapest faithful test, then GREEN after implementation.
- Primary test commands:
  - `pytest tests/unit/test_opencli_cleanup.py -q`
  - `node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs`
  - `pytest tests/integration/test_linkedin_opencli_pipeline.py -q`
  - `python -m py_compile linkedin_scrap.py`
  - `node --check scripts/linkedin_opencli_shadow_collect.mjs`
- Real-surface QA command:
  - `curl -s -X POST http://localhost:5000/api/run-scrap -H "Content-Type: application/json" -d "{\"mode\":\"update\",\"run_id\":\"qa-opencli-surface\"}"`
- Real-surface QA evidence:
  - `.omo/evidence/linkedin-opencli-collection-surface/user-window-before.png`
  - `.omo/evidence/linkedin-opencli-collection-surface/user-window-after.png`
  - `.omo/evidence/linkedin-opencli-collection-surface/run-scrap-output.txt`
  - `.omo/evidence/linkedin-opencli-collection-surface/opencli-daemon-status.txt`
  - `.omo/evidence/linkedin-opencli-collection-surface/opencli-tab-list-after.txt`
- Binary PASS/FAIL observables:
  - After cleanup, OpenCLI daemon status output contains `Daemon: not running`.
  - After cleanup, `opencli browser linkedin_saved_production tab list` does not contain the collection `page` targetId captured from `browser open`.
  - After real update run, the captured `SNS Feed Viewer - Chrome` screenshot does not show the Chrome OpenCLI debugging banner.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.
- Wave 0: RED proofs and current behavior pinning.
- Wave 1: Minimal JS collector lifecycle implementation.
- Wave 2: Python parent cleanup and orchestration contract verification.
- Wave 3: Real-surface QA through SNS Scrap update flow.
- Wave 4: Final review, evidence cleanup, and atomic commit.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 4, 5 | 2, 3 |
| 2 | none | 4, 5 | 1, 3 |
| 3 | none | 6, 7 | 1, 2 |
| 4 | 1, 2 | 8 | 5 |
| 5 | 1, 2 | 8 | 4 |
| 6 | 3 | 8 | 7 |
| 7 | 3 | 8 | 6 |
| 8 | 4, 5, 6, 7 | 9, 10 | none |
| 9 | 8 | 11 | 10 |
| 10 | 8 | 11 | 9 |
| 11 | 9, 10 | commit | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [ ] 1. RED: Replace weak source-string cleanup test with target lifecycle failure proof
  What to do / Must NOT do: Update `tests/unit/test_opencli_cleanup.py` so it fails on the current code because `scripts/linkedin_opencli_shadow_collect.mjs` does not close the `page` target returned by `browser open`. This test may remain source-level only for the initial RED, but it must specifically require `tab close` before `unbind`/`close`, not just any string containing `close`.
  Parallelization: Wave 0 | Blocked by: none | Blocks: 4, 5
  References: `tests/unit/test_opencli_cleanup.py`; `scripts/linkedin_opencli_shadow_collect.mjs:64-67`, `scripts/linkedin_opencli_shadow_collect.mjs:193`; OpenCLI help `browser tab close [targetId]`.
  Acceptance criteria: `pytest tests/unit/test_opencli_cleanup.py -q` fails before production code with an assertion proving no collection-owned target close exists.
  QA scenarios: failure evidence command `pytest tests/unit/test_opencli_cleanup.py -q | tee .omo/evidence/linkedin-opencli-collection-surface/task-1-red.txt`.
  Commit: N | covered by final fix commit

- [ ] 2. RED: Add executable Node unit test for collection-owned target cleanup order
  What to do / Must NOT do: Add `tests/unit/test_linkedin_opencli_surface_lifecycle.mjs` using `node:test`. It should drive exported or injectable cleanup helpers and expect command order: `tab close <pageId>`, `unbind`, `close`. Do not call real OpenCLI. Do not require LinkedIn network access.
  Parallelization: Wave 0 | Blocked by: none | Blocks: 4, 5
  References: JS test style in `tests/unit/test_linkedin_shadow_compare.mjs`; current collector at `scripts/linkedin_opencli_shadow_collect.mjs`.
  Acceptance criteria: `node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs` fails before implementation because the helper/export or `tab close` behavior does not exist.
  QA scenarios: failure evidence command `node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs | tee .omo/evidence/linkedin-opencli-collection-surface/task-2-red.txt`.
  Commit: N | covered by final fix commit

- [ ] 3. PIN: Preserve current Python parent cleanup contract before changing JS collector lifecycle
  What to do / Must NOT do: Keep the existing Python integration tests around `collect_opencli_posts`, daemon keep option, and `unbind` failure behavior. If necessary, add one characterization assertion that Python parent cleanup still happens after JS collector returns. Do not remove or weaken existing tests.
  Parallelization: Wave 0 | Blocked by: none | Blocks: 6, 7
  References: `tests/integration/test_linkedin_opencli_pipeline.py`; `linkedin_scrap.py:85-188`.
  Acceptance criteria: `pytest tests/integration/test_linkedin_opencli_pipeline.py -q` passes before production changes.
  QA scenarios: pin evidence command `pytest tests/integration/test_linkedin_opencli_pipeline.py -q | tee .omo/evidence/linkedin-opencli-collection-surface/task-3-pin.txt`.
  Commit: N | covered by final fix commit

- [ ] 4. GREEN: Make JS collector capture `browser open` page target and close only that target in finally
  What to do / Must NOT do: In `scripts/linkedin_opencli_shadow_collect.mjs`, store the JSON returned by `browser(session, ["open", url, "--window", "background"], { expectJson: true })`. Keep `openedPageId = result.page` only if it is a non-empty string. In `finally`, call target cleanup first: `browser(session, ["tab", "close", openedPageId])`, then `unbind`, then `close`. If `openedPageId` is missing, skip `tab close` and still run `unbind`/`close`. Do not close by URL/title. Do not select or close active tabs.
  Parallelization: Wave 1 | Blocked by: 1, 2 | Blocks: 8
  References: `scripts/linkedin_opencli_shadow_collect.mjs:60-67`, `scripts/linkedin_opencli_shadow_collect.mjs:181-194`, `scripts/linkedin_opencli_shadow_collect.mjs` final `finally` block; OpenCLI `tab close` help.
  Acceptance criteria: `pytest tests/unit/test_opencli_cleanup.py -q` and `node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs` pass.
  QA scenarios: green evidence command `pytest tests/unit/test_opencli_cleanup.py -q && node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs | tee .omo/evidence/linkedin-opencli-collection-surface/task-4-green.txt`.
  Commit: N | covered by final fix commit

- [ ] 5. GREEN: Make JS collector import-safe enough for lifecycle tests without changing CLI behavior
  What to do / Must NOT do: If the Node unit test requires imports, guard CLI execution with the standard ESM entrypoint check and export only minimal lifecycle helpers. The CLI invocation `node scripts/linkedin_opencli_shadow_collect.mjs --session ...` must behave identically. Do not split the whole collector or refactor parsing/network logic.
  Parallelization: Wave 1 | Blocked by: 1, 2 | Blocks: 8
  References: `package.json` has `"type": "module"`; JS test import style in `tests/unit/test_linkedin_shadow_compare.mjs`.
  Acceptance criteria: `node --check scripts/linkedin_opencli_shadow_collect.mjs` passes; `node scripts/linkedin_opencli_shadow_collect.mjs --help` behavior is not required if no help existed, but normal CLI argument parsing must remain intact.
  QA scenarios: green evidence command `node --check scripts/linkedin_opencli_shadow_collect.mjs && node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs | tee .omo/evidence/linkedin-opencli-collection-surface/task-5-green.txt`.
  Commit: N | covered by final fix commit

- [ ] 6. GREEN: Preserve Python parent cleanup after JS target cleanup
  What to do / Must NOT do: Keep `linkedin_scrap.py` parent cleanup order as the final safety net: JS collector closes the target it owns; Python still runs `cleanup_opencli_browser_session()` and optional `stop_opencli_daemon()` in `finally`. If JS collector exits non-zero, Python cleanup must still run. Do not rely on JS cleanup alone.
  Parallelization: Wave 2 | Blocked by: 3 | Blocks: 8
  References: `linkedin_scrap.py:116-140`, `linkedin_scrap.py:157-188`; `tests/integration/test_linkedin_opencli_pipeline.py`.
  Acceptance criteria: `pytest tests/integration/test_linkedin_opencli_pipeline.py -q` passes, including cleanup order assertions.
  QA scenarios: green evidence command `pytest tests/integration/test_linkedin_opencli_pipeline.py -q | tee .omo/evidence/linkedin-opencli-collection-surface/task-6-green.txt`.
  Commit: N | covered by final fix commit

- [ ] 7. Static guard: prevent forbidden user-tab cleanup strategies
  What to do / Must NOT do: Add or update tests so the diff cannot introduce `taskkill`, Alt+F4, title/URL-based Chrome closing, or `tab close` without using the captured `page` target. The guard should inspect changed source text only where necessary; it must not replace behavioral tests.
  Parallelization: Wave 2 | Blocked by: 3 | Blocks: 8
  References: guardrail in this plan; `tests/unit/test_opencli_cleanup.py`.
  Acceptance criteria: `pytest tests/unit/test_opencli_cleanup.py -q` fails if forbidden cleanup strings are introduced in LinkedIn OpenCLI collector cleanup.
  QA scenarios: guard evidence command `pytest tests/unit/test_opencli_cleanup.py -q | tee .omo/evidence/linkedin-opencli-collection-surface/task-7-green.txt`.
  Commit: N | covered by final fix commit

- [ ] 8. Integrated verification: run syntax and targeted tests together
  What to do / Must NOT do: Run all targeted verification before any real browser QA. Do not proceed to browser-surface QA if unit/integration tests fail.
  Parallelization: Wave 3 | Blocked by: 4, 5, 6, 7 | Blocks: 9, 10
  References: `package.json`, `pytest.ini`, targeted test files above.
  Acceptance criteria: All commands exit 0: `python -m py_compile linkedin_scrap.py`; `node --check scripts/linkedin_opencli_shadow_collect.mjs`; `pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q`; `node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs`.
  QA scenarios: evidence command `(python -m py_compile linkedin_scrap.py && node --check scripts/linkedin_opencli_shadow_collect.mjs && pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q && node --test tests/unit/test_linkedin_opencli_surface_lifecycle.mjs) | tee .omo/evidence/linkedin-opencli-collection-surface/task-8-targeted.txt`.
  Commit: N | covered by final fix commit

- [ ] 9. Real-surface QA: actual SNS Scrap update flow leaves no user-window OpenCLI debug banner
  What to do / Must NOT do: Use the running app surface, not a pure CLI-only substitute. Before the run, capture the `SNS Feed Viewer - Chrome` window with a non-focus `PrintWindow` script. Trigger the same update path used by the UI via `/api/run-scrap`. After completion, capture the same Chrome window again. Verify the OpenCLI debugging banner is absent. Do not interactively steal the user's screen except where impossible; prefer HWND capture.
  Parallelization: Wave 3 | Blocked by: 8 | Blocks: 11
  References: `scrap_sns_server.py:1075-1110`; `total_scrap.py:351-411`; prior evidence showed foreground capture can accidentally capture Codex, so use HWND-targeted `PrintWindow`.
  Acceptance criteria: `curl -s -X POST http://localhost:5000/api/run-scrap -H "Content-Type: application/json" -d "{\"mode\":\"update\",\"run_id\":\"qa-opencli-surface\"}"` completes successfully; after screenshot of `SNS Feed Viewer - Chrome` does not show the OpenCLI Chrome debugging banner.
  QA scenarios: evidence files `.omo/evidence/linkedin-opencli-collection-surface/user-window-before.png`, `.omo/evidence/linkedin-opencli-collection-surface/user-window-after.png`, `.omo/evidence/linkedin-opencli-collection-surface/run-scrap-output.txt`.
  Commit: N | covered by final fix commit

- [ ] 10. Runtime cleanup QA: collection-owned target removed and OpenCLI daemon stopped
  What to do / Must NOT do: Record the collection `page` targetId from the JS collector summary or debug evidence. After the run, verify that targetId is no longer present in `opencli browser linkedin_saved_production tab list`, and verify `opencli daemon status` returns `Daemon: not running`. Do not use daemon status as a substitute for screenshot QA.
  Parallelization: Wave 3 | Blocked by: 8 | Blocks: 11
  References: OpenCLI `browser tab list`, `browser tab close`, `daemon status`.
  Acceptance criteria: `opencli browser linkedin_saved_production tab list` output does not contain the recorded `page`; `opencli daemon status` contains `Daemon: not running`.
  QA scenarios: evidence commands `opencli browser linkedin_saved_production tab list > .omo/evidence/linkedin-opencli-collection-surface/opencli-tab-list-after.txt`; `opencli daemon status > .omo/evidence/linkedin-opencli-collection-surface/opencli-daemon-status.txt`.
  Commit: N | covered by final fix commit

- [ ] 11. Final documentation and commit
  What to do / Must NOT do: Update this plan with execution results if executing under ULW, and update `CHANGELOG.md` following existing table format. Commit code/tests/docs in one fix commit unless runtime data files changed from the actual QA run; if data files changed, commit them separately as `chore(data)`. Do not include unrelated user dirty changes without acknowledging they came from the QA run.
  Parallelization: Wave 4 | Blocked by: 9, 10 | Blocks: final
  References: `CHANGELOG.md`; project Git rules; this plan.
  Acceptance criteria: `git status --short` shows only intended staged/committed changes after commit; pushed only if the user requested cp or commit-push.
  QA scenarios: evidence command `git status --short | tee .omo/evidence/linkedin-opencli-collection-surface/task-11-status.txt`.
  Commit: Y | `fix(linkedin-opencli): 수집 표면 종료와 디버깅 배너 정리`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit: verify each todo's acceptance criterion has a matching evidence file under `.omo/evidence/linkedin-opencli-collection-surface/`.
- [ ] F2. Code quality review: inspect diff for scope creep into LinkedIn parser/merge/image/tag logic and reject if present.
- [ ] F3. Real manual QA: verify the final `SNS Feed Viewer - Chrome` screenshot shows no OpenCLI debugging banner.
- [ ] F4. Scope fidelity: verify no code closes arbitrary Chrome tabs/windows and no test uses only `Daemon: not running` as completion proof.

## Commit strategy
- Preferred single implementation commit: `fix(linkedin-opencli): 수집 표면 종료와 디버깅 배너 정리`.
- If real QA updates output JSON or tag files, split those into `chore(data): 20260709 수집 산출물 갱신`.
- If plan/evidence updates are committed separately, use `docs(opencli-plan): 수집 표면 정리 계획과 검증 기록`.
- Do not commit user-generated dirty files unless they are produced by the planned QA run or explicitly requested.

## Success criteria
- The implementation records the collection-owned OpenCLI `page` target returned by `browser open`.
- Cleanup closes only that recorded target before `unbind -> close -> daemon stop`.
- Existing LinkedIn collection parsing and merge behavior remains unchanged.
- Targeted tests pass: Python unit/integration, Node unit, Python compile, Node syntax check.
- Real SNS Scrap update flow completes and the `SNS Feed Viewer - Chrome` window has no OpenCLI debugging banner afterward.
- OpenCLI daemon is stopped after collection.
- The recorded collection target is absent from `opencli browser linkedin_saved_production tab list` after cleanup.
