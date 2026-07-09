---
slug: scrap-sns-update-image-opencli
status: metis-iterated
intent: clear
review_required: false
pending-action: deliver .omo/plans/scrap-sns-update-image-opencli.md
approach: Plan only. Exclude a new post+image repair/backfill feature, but include shared image identity and update/all behavior fixes needed to prevent duplicate image generation.
---

# Draft: scrap-sns-update-image-opencli

## Components (topology ledger)
| id | outcome | status | evidence path |
| --- | --- | --- | --- |
| C1 | LinkedIn OpenCLI browser session is released after collection finishes or fails. | active | scripts/linkedin_opencli_shadow_collect.mjs:60-62,185,369-374 |
| C2 | Normal update mode downloads images only for posts absent from the latest pre-run total file. | active | total_scrap.py:553-601,633-648 |
| C3 | all mode and shared image validation preserve existing local images when LinkedIn signed URL query parameters change. | active | total_scrap.py:90-93,103-122,125-149 |
| C4 | Image processing emits progress logs visible through the existing scrap progress stream parser and API. | active | scrap_sns_server.py:112-169,1102-1118 |
| C5 | New post+image repair/backfill feature remains out of scope, while current all/update merge behavior is respected. | active | thread_scrap.py:117-145, linkedin_scrap.py:158-205,295-385 |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| OpenCLI cleanup scope | Use `opencli browser <session> close`, not `daemon stop`. | `daemon stop` can affect unrelated OpenCLI activity; the defect is a session/tab lease cleanup. | Yes |
| New repair/backfill feature | Do not add it in this plan. | User stated it is not the priority and should be treated as a broader post+image repair/backfill feature if ever done. | Yes |
| Update image target definition | In `mode="update"`, image download targets are posts whose `utils.post_meta.build_post_key(post)` value was absent from the latest pre-run `output_total/total_full_*.json`. If no previous total exists, all merged posts are first-run targets. `sequence_id` must not be used for this comparison. | This prevents normal update from becoming a historical image repair/backfill pass and uses the repo's durable post key helper. | Yes |
| Existing post image handling in update | Preserve already linked `local_images`; do not fill missing historical `local_images`. | Preservation avoids data loss; filling missing historical images is repair/backfill. | Yes |
| Validation split | Strict "existing local file must be linked" validation applies to image target posts. Full merged output validation in update mode must be one-way: every `local_images` entry points to an existing file, without requiring missing historical images to be linked. | Current full-dataset strict validation can accidentally require backfill. | Yes |
| LinkedIn image key normalization | Only `licdn.com`/`media.licdn.com` image URLs use `scheme + host + path` as the identity key; non-LinkedIn URLs keep query strings. | Current full URL hash causes duplicate local files when only LinkedIn signed query params change. | Yes |
| Progress surface | Print image-stage logs from `total_scrap.py` and make `_scrap_progress_message_from_line()` accept them; do not change `/api/scrap-progress` response shape. | Server only surfaces stdout/log lines that its parser maps. | Yes |

## Findings (cited - path:lines)
- `scripts/linkedin_opencli_shadow_collect.mjs:60-62` wraps OpenCLI browser commands, `:185` opens a background browser session, and `:369-374` exits without a cleanup path.
- `total_scrap.py:90-93` hashes the full image URL for local file names, so LinkedIn signed URL query churn produces new file names for the same image.
- `total_scrap.py:103-122` preserves prior local images by exact original URL, so changed signed query params miss existing local files.
- `total_scrap.py:125-149` validates local links by recomputing the full-URL-derived path, so validation must use the same stable identity rule as download/preserve and must not force historical backfill in update mode.
- `utils/post_meta.py:65-76` provides `build_post_key(post)`, the durable key rule to use for update target comparison. `sequence_id` is a local ordering value and must not be used.
- `total_scrap.py:553-601` downloads images by iterating the supplied posts, and `total_scrap.py:633-648` currently passes all merged posts regardless of `mode`.
- `scrap_sns_server.py:112-169` maps stdout/log lines into progress messages; image-stage stdout must be explicitly accepted there or it can be dropped.
- `scrap_sns_server.py:1102-1118` forwards `total_scrap.py` stdout into progress-event append logic.
- `thread_scrap.py:117-145` contains a limited Simple-from-Full backfill path when Simple data is missing; this is existing post-list recovery behavior, not the new image repair feature.
- `linkedin_scrap.py:158-205` and `:295-385` merge current OpenCLI results with previous LinkedIn full data in both update/all flows, preserving identity/order metadata.
- Existing tests cover local image preservation at `tests/unit/test_total_scrap_local_images.py:8-74`, orchestration call order at `tests/unit/test_total_scrap_orchestration.py:149-193`, and progress parsing/integration at `tests/integration/test_run_scrap_stats.py:348-538`.

## Decisions (with rationale)
- Include shared image identity fixes in scope. Reason: without this, `all` mode can recreate the same duplicate-image problem even if normal `update` mode is narrowed.
- Exclude new repair/backfill feature. Reason: user clarified this is a separate post+image repair/backfill capability, not the current priority.
- Define update image targets by comparing `build_post_key(post)` against keys from the latest total file captured before scraping starts. Reason: current `merge_results()` returns only a merged list, and the repo already has a durable post key helper.
- Preserve existing `local_images` for existing posts without treating missing `local_images` as work to repair in update mode. Reason: preservation avoids data loss; filling missing historical images is repair/backfill and remains out of scope.
- Keep progress logging in the existing progress stream but update parser coverage. Reason: stdout alone may be ignored unless `_scrap_progress_message_from_line()` maps the new image-stage lines.
- Require failing-first proof before production changes in the execution plan. Reason: behavior changes touch persistent output data and browser automation cleanup.

## Scope IN
- OpenCLI browser session cleanup after LinkedIn collection success or failure.
- Update-mode image target scoping based on durable identities absent from the pre-run total file.
- Stable LinkedIn image identity/key logic used consistently by download, preserve, and validation paths.
- Validation behavior split so update-mode full output checks do not become repair/backfill requirements.
- all-mode behavior that can scan the full dataset without duplicating local files due to signed URL churn.
- Image-stage progress logs and parser support for target count, kept existing count, newly downloaded count, skipped count, and failures.
- Verification plan for JSON output, image count behavior, progress API visibility, and viewer reflection per project rules.

## Scope OUT (Must NOT have)
- No new standalone repair/backfill command or mode.
- No redesign of Threads/X/LinkedIn post recovery behavior.
- No update-mode scan of historical posts solely to fill missing `local_images`.
- No full historical image redownload.
- No deletion or cleanup of previously over-generated image files unless separately requested.
- No API response shape change for `/api/scrap-progress`.
- No unrelated viewer UI or tag behavior changes.

## Open questions
- None blocking. The user approved plan-file creation and clarified the scope split.

## Approval gate
status: approved
approved_by_user: 2026-07-09 KST, "좋아, 이것을 반영해서 계획문서 작성해줘"
metis_review_1: ITERATE, patched by defining update targets, image key rule, progress parser coverage, commit policy, and anti-backfill criteria.
