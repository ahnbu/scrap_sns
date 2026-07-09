# scrap-sns-update-image-opencli - Work Plan

## TL;DR (For humans)
**What you'll get:** SNS 수집이 끝난 뒤 LinkedIn 브라우저 디버깅 연결이 남지 않게 하고, 일반 업데이트에서 새 글보다 훨씬 많은 이미지가 생성되는 문제를 막습니다. 전체 업데이트를 돌려도 LinkedIn 이미지 주소의 임시 토큰 변경 때문에 같은 이미지가 계속 새 파일로 저장되지 않게 합니다.

**Why this approach:** 일반 업데이트가 전체 이미지 목록을 다시 훑고 있고, LinkedIn 이미지 주소의 임시 query가 바뀔 때 같은 이미지를 새 이미지로 오인합니다. 그래서 update 모드는 직전 통합 파일에 없던 게시글만 이미지 다운로드 대상으로 보고, update/all 공통 이미지 key는 안정화합니다.

**What it will NOT do:** 게시글+이미지 repair/backfill 기능을 새로 만들지 않습니다. 이미 과다 생성된 이미지 파일을 삭제하지 않습니다. 뷰어 UI나 태그 기능은 바꾸지 않습니다.

**Effort:** Medium
**Risk:** Medium - persistent JSON/image output behavior and LinkedIn browser automation cleanup both change.
**Decisions to sanity-check:** update 모드는 `utils.post_meta.build_post_key(post)` 기준으로 직전 통합 파일에 없던 게시글만 이미지 다운로드 대상으로 봅니다. 기존 게시글은 이미 연결된 로컬 이미지만 보존하고, 누락 이미지를 채우는 repair/backfill은 하지 않습니다. all 모드는 전체를 보되 안정 key로 기존 이미지를 재사용합니다. OpenCLI는 `daemon stop`이 아니라 session-level `browser close`를 사용합니다.

Your next move: execute this plan with `$start-work`, or ask for a high-accuracy review first. Full execution detail follows below.

---

> TL;DR (machine): Medium effort, medium risk. Fix OpenCLI cleanup, update-mode image scope, signed URL image identity, all-mode no-duplicate behavior, and image progress logs without adding repair/backfill.

## Scope
### Must have
- `scripts/linkedin_opencli_shadow_collect.mjs` releases the OpenCLI browser session after success and failure.
- `total_scrap.py` distinguishes update-mode image processing from all-mode image processing.
- `update` mode defines image download targets as posts whose `utils.post_meta.build_post_key(post)` value was absent from the latest pre-run `output_total/total_full_*.json`. If no previous total exists, all merged posts are first-run targets. `sequence_id` must not be used for this comparison.
- Existing posts in `update` mode keep already linked `local_images`, but missing historical `local_images` are not filled as repair/backfill work.
- `all` mode can still process the full merged dataset but must preserve existing local images when LinkedIn signed URL query params change.
- Image identity logic is shared consistently by:
  - `get_local_image_paths()`
  - `collect_preserved_local_images()`
  - `download_images()`
  - `validate_local_image_links()`
- Image-stage logs expose enough progress to explain long waits in the existing `/api/scrap-progress` UI stream.
- `_scrap_progress_message_from_line()` accepts image-stage stdout lines so the progress API actually surfaces the new messages.
- Validation is split so update-mode full-output validation checks that declared `local_images` files exist, while strict "local file exists for this media URL, so it must be linked" validation runs only for update image target posts or all-mode full processing.
- Existing output invariants remain intact: latest platform full files merge into `output_total/total_full_YYYYMMDD.json`, and `local_images` points to files that exist under `web_viewer/images`.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not add a new repair/backfill CLI mode or command.
- Do not redesign Threads/X/LinkedIn post recovery behavior.
- Do not run a full historical image redownload as part of normal `update`.
- Do not scan historical posts in `update` solely to fill missing `local_images`.
- Do not let `validate_local_image_links()` or its replacement force historical missing image links during update mode.
- Do not delete previously over-generated images.
- Do not change `/api/scrap-progress` response schema.
- Do not alter viewer tags, metadata, hidden/star state, card layout, or search/filter behavior.
- Do not use `opencli daemon stop` as the default cleanup path.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD for behavior changes. Add or extend tests before changing production code where a seam exists; for OpenCLI cleanup, introduce the smallest test seam needed to prove `browser close` runs on success and failure.
- Evidence root: `.omo/evidence/scrap-sns-update-image-opencli/`
- Required test commands:
  - `pytest tests/unit/test_total_scrap_local_images.py`
  - `pytest tests/unit/test_total_scrap_orchestration.py`
  - `pytest tests/integration/test_run_scrap_stats.py -q` or a narrower existing progress-parser test after adding image-stage cases for `_scrap_progress_message_from_line()`.
  - Targeted OpenCLI cleanup proof command chosen by the executor after adding the minimal seam, for example `node scripts/linkedin_opencli_shadow_collect.mjs --dry-run ...` with command stubbing, or a repo-local unit probe if the script is made importable.
  - `python total_scrap.py --mode update` or a bounded fixture/probe that exercises `merge_results()` -> `download_images()` -> `validate_local_image_links()` without live SNS collection when live collection would be too slow or auth-dependent.
  - After any server/viewer-facing progress change: `npm run view` or `wscript sns_hub.vbs`, then verify `http://localhost:5000/api/scrap-progress` emits image-stage messages during a bounded run.
- Verification is agent-executed. Any later user confirmation is a handoff/acceptance step outside the execution proof, not a substitute for tests or QA artifacts.

## Execution strategy
### Parallel execution waves
- Wave 0 is read-only confirmation and failing-first proof setup. It can run OpenCLI cleanup test design and image fixture design in parallel because they touch different files.
- Wave 1 fixes OpenCLI cleanup. It is independent of image logic and can land first.
- Wave 2 fixes image identity and preservation. This blocks update/all image behavior because all image paths must share one key rule.
- Wave 3 changes update/all image target selection and logging. It depends on Wave 2.
- Wave 4 performs final integration verification through stored data and viewer/progress surfaces.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 3 | 2 |
| 2 | none | 4, 5, 6 | 1 |
| 3 | 1 | final verification | 4 after 2 |
| 4 | 2 | 5, 6 | 3 |
| 5 | 2, 4 | final verification | none |
| 6 | 2, 4, 5 | final verification | none |
| 7 | 3, 5, 6 | completion | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->

### Wave 0 - Pin current behavior and test seams
- [ ] 1. Pin OpenCLI cleanup behavior before changing it.
  What to do / Must NOT do: Add the smallest test/probe seam for `scripts/linkedin_opencli_shadow_collect.mjs` so command invocations can be observed without opening a real LinkedIn browser. Capture RED first showing there is no `browser <session> close` after success/failure. Do not hit real LinkedIn in this test.
  Parallelization: Wave 0 | Blocked by: none | Blocks: Todo 3
  References (executor has NO interview context - be exhaustive): `scripts/linkedin_opencli_shadow_collect.mjs:37-62`, `scripts/linkedin_opencli_shadow_collect.mjs:176-187`, `scripts/linkedin_opencli_shadow_collect.mjs:347-374`, `linkedin_scrap.py:84-108`
  Acceptance criteria (agent-executable): RED proof fails because expected `browser <session> close` is absent, not because of syntax/import errors.
  QA scenarios (name the exact tool + invocation): Failure scenario: run the chosen probe command, for example `node <probe> --scenario success-with-command-log`, expect non-zero with assertion text containing `missing browser close`; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-1-opencli-red.txt`
  Commit: only if explicitly requested; use `cp` skill | `test(opencli): pin missing browser session cleanup`

- [ ] 2. Pin image identity and update/all scope behavior before changing it.
  What to do / Must NOT do: Extend `tests/unit/test_total_scrap_local_images.py` and/or add a focused fixture to prove current LinkedIn signed URL query churn fails to reuse existing local images. Add a fixture with previous total posts plus current merged/platform posts so update-mode target selection can be tested before implementation. Do not create a repair/backfill feature or depend on current live output files.
  Parallelization: Wave 0 | Blocked by: none | Blocks: Todos 4, 5, 6
  References: `total_scrap.py:90-93`, `total_scrap.py:103-122`, `total_scrap.py:125-149`, `total_scrap.py:553-601`, `total_scrap.py:633-648`, `tests/unit/test_total_scrap_local_images.py:8-74`, `tests/unit/test_total_scrap_orchestration.py:149-193`
  Acceptance criteria: RED proof shows query-only LinkedIn URL changes do not map to the existing local image under current code, and update mode currently passes all merged posts to `download_images` instead of only posts whose `build_post_key(post)` is absent from the latest pre-run total.
  QA scenarios: Failure scenario: `pytest tests/unit/test_total_scrap_local_images.py tests/unit/test_total_scrap_orchestration.py -q`, expect the newly added assertions fail for the intended reason; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-2-image-red.txt`
  Commit: only if explicitly requested; use `cp` skill | `test(images): pin signed url and update-scope regressions`

### Wave 1 - OpenCLI cleanup
- [ ] 3. Implement LinkedIn OpenCLI browser session cleanup.
  What to do / Must NOT do: Add a `finally` cleanup path around `main()` or the session-owning collection flow so `browser(session, ["close"])` is attempted after success and after errors. Cleanup failure should be non-fatal but logged to stderr. Do not use `opencli daemon stop` by default.
  Parallelization: Wave 1 | Blocked by: Todo 1 | Blocks: final verification
  References: `scripts/linkedin_opencli_shadow_collect.mjs:60-62`, `scripts/linkedin_opencli_shadow_collect.mjs:176-187`, `scripts/linkedin_opencli_shadow_collect.mjs:347-374`, OpenCLI help verified earlier: `opencli browser <session> close` releases the current browser session tab lease.
  Acceptance criteria: The RED proof from Todo 1 turns GREEN for both success and thrown-error paths, and stderr/stdout remains parseable by `linkedin_scrap.py:54-61`.
  QA scenarios: Happy: run the OpenCLI cleanup probe success scenario, expect command log includes `browser <session> close` after summary output; Failure: run probe with forced collection error, expect non-zero plus command log includes `browser <session> close`; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-3-opencli-green.txt`
  Commit: only if explicitly requested; use `cp` skill | `fix(opencli): close linkedin browser session after collection`

### Wave 2 - Stable image identity
- [ ] 4. Implement shared stable image identity for local image paths and preservation.
  What to do / Must NOT do: Add a small helper in `total_scrap.py` that derives an image identity key. Only LinkedIn image URLs on `licdn.com`/`media.licdn.com` use `scheme + host + path` as the identity key, excluding volatile query params such as `e`, `v`, and `t`. Non-LinkedIn URLs keep their query string unless a test explicitly proves a safe normalization rule. Use this helper in `get_local_image_paths()`, `collect_preserved_local_images()`, `download_images()`, and `validate_local_image_links()`. Do not change post identity rules or `post_key` behavior.
  Parallelization: Wave 2 | Blocked by: Todo 2 | Blocks: Todos 5, 6
  References: `total_scrap.py:81-93`, `total_scrap.py:103-122`, `total_scrap.py:125-149`, `total_scrap.py:553-601`, `docs/development.md`, `utils/post_schema.py`
  Acceptance criteria: The RED signed-URL test from Todo 2 turns GREEN. Query-only changes for LinkedIn media resolve to the same local web path or preserved local path. Non-LinkedIn URLs retain query-sensitive behavior and do not collapse unrelated query-distinguished images.
  QA scenarios: Happy: `pytest tests/unit/test_total_scrap_local_images.py -q`, expect pass and evidence showing same LinkedIn URL path with different query maps to one local image; Failure: add malformed/empty media URL fixture, expect helper skips or handles it without raising; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-4-image-key-green.txt`
  Commit: only if explicitly requested; use `cp` skill | `fix(images): stabilize linkedin local image identity`

### Wave 3 - update/all behavior and progress logs
- [ ] 5. Limit update-mode image processing without weakening all-mode behavior.
  What to do / Must NOT do: Change `total_scrap.py` orchestration so `mode="update"` computes image download targets by comparing `utils.post_meta.build_post_key(post)` against keys from the latest pre-run `output_total/total_full_*.json`. `sequence_id` must not be used. `save_total()` must still receive the full merged dataset. Existing posts may carry forward already linked `local_images`, but update mode must not scan historical posts solely to fill missing `local_images`. For `mode="all"`, allow full dataset image consideration but rely on the stable image identity from Todo 4 to reuse existing files. Do not create a new repair/backfill mode.
  Parallelization: Wave 3 | Blocked by: Todo 4 | Blocks: Todo 6
  References: `total_scrap.py:448-507`, `total_scrap.py:509-512`, `total_scrap.py:553-601`, `total_scrap.py:633-648`, `utils/post_meta.py:65-76`, `linkedin_scrap.py:278-385`, `thread_scrap.py:823-878`, `twitter_scrap.py:450-504`, `tests/unit/test_total_scrap_orchestration.py:149-193`
  Acceptance criteria: Unit/orchestration tests prove update mode calls image download only for posts whose `build_post_key(post)` is absent from the pre-run total while `save_total()` still receives the full merged dataset. all mode still validates and preserves local image links across the merged dataset. Update mode validation must not require historical missing `local_images` to be filled.
  QA scenarios: Happy: `pytest tests/unit/test_total_scrap_orchestration.py tests/unit/test_total_scrap_local_images.py -q`, expect pass; Failure: fixture with existing post plus changed signed URL must not produce an extra download request in update mode, and fixture with historical missing `local_images` must not fail full-output validation solely because it was not backfilled; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-5-update-scope-green.txt`
  Commit: only if explicitly requested; use `cp` skill | `fix(images): restrict update downloads to current targets`

- [ ] 6. Add image-stage progress logging.
  What to do / Must NOT do: Print clear KST-friendly progress lines from `download_images()` and/or its caller: target posts, media candidates, kept existing local images, newly downloaded files, skipped existing files, failed downloads. Update `_scrap_progress_message_from_line()` and tests so these stdout lines are not dropped. Do not change `/api/scrap-progress` JSON shape.
  Parallelization: Wave 3 | Blocked by: Todos 4, 5 | Blocks: final verification
  References: `total_scrap.py:553-601`, `scrap_sns_server.py:112-169`, `scrap_sns_server.py:1102-1118`, `scrap_sns_server.py:1165-1169`, `tests/integration/test_run_scrap_stats.py:348-538`, `web_viewer/script.js:83`, `web_viewer/script.js:1007`
  Acceptance criteria: A bounded run or mocked run emits progress lines that `_scrap_progress_message_from_line()` maps into progress events. Long image phases are visible as image-processing messages instead of a silent gap.
  QA scenarios: Happy: run progress parser/integration tests, then start the local server with `npm run view` or equivalent, trigger a bounded scrap/probe, and `curl -s "http://localhost:5000/api/scrap-progress?run_id=<id>&after=0"` expecting image-stage messages; Failure: mocked download failure increments failure count and does not stop the entire scrape unless existing behavior already would; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-6-progress-green.txt`
  Commit: only if explicitly requested; use `cp` skill | `fix(progress): report image download stage counts`

### Wave 4 - Integration and data/viewer proof
- [ ] 7. Run final SNS collection/image integration proof.
  What to do / Must NOT do: Exercise the changed flow through the closest faithful surface. Prefer a bounded fixture/probe for image identity and orchestration plus a real local server progress/API check. If live SNS collection is run, do not delete user data or generated image files. Record latest output counts and image generation delta.
  Parallelization: Wave 4 | Blocked by: Todos 3, 5, 6 | Blocks: completion
  References: Project rule completion criteria in `AGENTS.md`; `total_scrap.py:633-648`; `scrap_sns_server.py:1080-1156`; `web_viewer/script.js:1007`; `utils/query-sns.mjs`
  Acceptance criteria: `merge_results()` -> image target selection -> `download_images()` -> mode-appropriate local image validation succeeds; update-mode image creation count matches posts whose `build_post_key(post)` is absent from the pre-run total rather than full historical LinkedIn signed URL churn; latest total JSON count matches viewer/API count; progress endpoint includes image-stage logs; OpenCLI cleanup proof remains GREEN.
  QA scenarios: Happy: `node utils/query-sns.mjs stats` plus local server/API/viewer check for latest total count, and captured progress output containing image-stage messages; Failure: fixture with existing LinkedIn signed URL query change does not create a second local image file; Evidence `.omo/evidence/scrap-sns-update-image-opencli/task-7-final-integration.txt`
  Commit: only if explicitly requested; use `cp` skill | `fix(scrap): stabilize update image processing and opencli cleanup`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE internally. Report results to the user; user acceptance is outside the agent-executed verification proof.
- [ ] F1. Plan compliance audit
  - Verify every completed change maps to one of the Must have items and none violates Must NOT have.
  - Evidence: `.omo/evidence/scrap-sns-update-image-opencli/f1-plan-compliance.md`
- [ ] F2. Code quality review
  - Review diffs for small scope, no drive-by refactors, no broad repair/backfill feature, and no fragile query stripping for non-LinkedIn media.
  - Evidence: `.omo/evidence/scrap-sns-update-image-opencli/f2-code-quality.md`
- [ ] F3. Real manual QA
  - Drive local server/progress surface and a bounded image-processing scenario. Capture API output and, if viewer surface changed or latest posts are inspected, browser screenshot.
  - Evidence: `.omo/evidence/scrap-sns-update-image-opencli/f3-manual-qa.md`
- [ ] F4. Scope fidelity
  - Confirm no new repair/backfill command/mode, no deletion of existing generated images, and no unrelated viewer/tag behavior changes.
  - Evidence: `.omo/evidence/scrap-sns-update-image-opencli/f4-scope-fidelity.md`

## Commit strategy
- Commit only if the user explicitly asks for commit. If committing, prefer one commit per logical concern:
  1. `fix(opencli): close linkedin browser session after collection`
  2. `fix(images): stabilize linkedin local image identity`
  3. `fix(images): restrict update downloads to current targets`
  4. `fix(progress): report image download stage counts`
- If the implementation is small and tests are tightly coupled, a single commit is acceptable only when the user requested commit:
  - `fix(scrap): stabilize update image processing and opencli cleanup`
- Per project rule, if committing, use the `cp` skill workflow rather than direct `git add/commit`.
- Do not commit plan-only files unless the user asks to preserve the plan in git.

## Success criteria
- LinkedIn OpenCLI browser session cleanup is proven on success and failure without stopping the entire OpenCLI daemon.
- Normal `update` mode no longer performs image processing across every historical merged post when only current-run/new posts need images.
- In `update`, image download targets are exactly posts whose `build_post_key(post)` is absent from the latest pre-run total, with existing `local_images` preserved and missing historical `local_images` left untouched.
- In `update`, validation does not force historical missing image links to be repaired; strict media-to-local linking validation applies to image target posts, while full output validation checks that declared local image paths exist.
- `all` mode can process the full dataset without duplicating local image files just because LinkedIn signed URL query params changed.
- `get_local_image_paths()`, `collect_preserved_local_images()`, `download_images()`, and `validate_local_image_links()` use one consistent image identity rule.
- Image progress lines appear in the existing scrap progress stream.
- No new repair/backfill mode or broader post recovery redesign is introduced.
- Tests and real-surface checks produce artifacts under `.omo/evidence/scrap-sns-update-image-opencli/`.
