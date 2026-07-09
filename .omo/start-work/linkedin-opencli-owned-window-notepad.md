# Ultrawork Notepad - execute LinkedIn OpenCLI owned-window plan
Started: 2026-07-09T00:00:00+09:00

## Plan (exhaustively detailed)
1. Bootstrap ultrawork/start-work/programming instructions.
2. Create Boulder state and evidence/ledger directories.
3. Delegate Wave 1 T1/T2/T3 in parallel.
4. Integrate Wave 1 results and mark completed only after verification.
5. Delegate Wave 2 Node implementation T4.
6. Delegate Python owned-window and bound-validation implementation T5/T6 with conflict-safe ownership.
7. Delegate focused automated verification T7.
8. Delegate LinkedIn-only real-surface QA T8.
9. Delegate full update and viewer QA T9.
10. Delegate final audit T10 and final verification wave F1-F4.
11. Run required review/debugging gate and report.

## Success criteria + QA scenarios
- Deliverable: Execute the approved `.omo/plans/linkedin-opencli-owned-window.md` plan end-to-end.
- Tier: HEAVY because it changes auth/session/browser/OpenCLI integration and requires real viewer QA.
- Criterion 1: Node collector externally bound session cleanup is fixed. Scenario: `node --check scripts/linkedin_opencli_shadow_collect.mjs` and `pytest tests/unit/test_opencli_cleanup.py -q`; PASS exit 0; evidence `.omo/evidence/linkedin-opencli-owned-window/t4-node-green.txt`. RED: T2 node cleanup test fails before implementation.
- Criterion 2: Python LinkedIn collection owns exactly one Chrome HWND and replaces persistent whoami. Scenario: `pytest tests/integration/test_linkedin_opencli_pipeline.py -q`; PASS exit 0; evidence `.omo/evidence/linkedin-opencli-owned-window/t5-t6-python-green.txt`. RED: T5/T6 tests fail before implementation.
- Criterion 3: Focused suite passes. Scenario: `node --check scripts/linkedin_opencli_shadow_collect.mjs; pytest tests/unit/test_opencli_cleanup.py tests/integration/test_linkedin_opencli_pipeline.py -q; node utils/query-sns.mjs --help`; PASS exit 0; evidence `.omo/evidence/linkedin-opencli-owned-window/t7-focused-green.txt`.
- Criterion 4: Real LinkedIn update and full viewer QA pass. Scenario: delegated QA runs `python linkedin_scrap.py --mode update`, `python total_scrap.py --mode update`, `npm run view`, browser verification at `http://localhost:5000/`; PASS by evidence files and cleanup receipts.

## Now
Run final F1-F4 and review/debugging gate.

## Todo
- Create `.omo/boulder.json`, `.omo/start-work/ledger.jsonl`, evidence dir.
- Dispatch T1/T2/T3 workers.
- Wait and integrate Wave 1.

## Findings
- Skills used: `omo:ultrawork` for evidence-driven execution, `omo:start-work` because user requested plan execution, `omo:programming` because Python code will be changed by workers.
- Python reference loaded: `programming/references/python/README.md`.
- Existing plan path: `D:/vibe-coding/scrap_sns/.omo/plans/linkedin-opencli-owned-window.md`.
- Boulder did not exist before this run.
- Worktree note: project instructions say current branch direct work is default and worktree only on explicit request; this run uses current workspace and records dirty-worktree evidence.
- Wave 1 DoneClaims received for T1, T2, T3.
- Wave 1 independent verifier verdict: confirmed.
- T1/T2/T3 plan checkboxes marked complete.

## Learnings

## Plan amendment
- User requested T5 HWND ambiguity correction while T4 worker was running.
- Integrated: baseline diff must have exactly one new visible Chrome HWND before recording `owned_hwnd`.
- Integrated: 0 or 2+ candidates must fail without closing any Chrome window.
- Integrated: ambiguous candidates must be logged to evidence with title/HWND/process info.
- Integrated: WM_CLOSE only after an owned handle is recorded.

## T4 DoneClaim
- T4 worker completed Node collector ownership split.
- Changed: scripts/linkedin_opencli_shadow_collect.mjs and evidence/ledger.
- Verification reported: `node --check scripts/linkedin_opencli_shadow_collect.mjs` exit 0; `pytest tests/unit/test_opencli_cleanup.py -q` exit 0, 3 passed.
- Cleanup: no runtime resource spawned.
- T4 independent verifier verdict: confirmed.
- T4 plan checkbox marked complete.
- T5/T6 worker completed Python owned-window lifecycle and bound validation.
- T5/T6 first verifier rejected focus failure path; follow-up worker added RED/GREEN focus failure test and fix.
- T5/T6 second verifier verdict: confirmed.
- T5/T6 plan checkboxes marked complete.
- T7 worker completed focused automated verification: node check, py_compile, focused pytest 22 passed, query-sns help.
- T7 first verifier found evidence valid but ledger/notepad stale. Ledger and notepad were corrected.
- T8 real-surface QA blocked: `python linkedin_scrap.py --mode update` exited 1 because OpenCLI bound session attached to existing `https://my-bookstations.vercel.app/` Chrome page instead of LinkedIn saved-posts. Auth-required was not the cause. QA cleanup restored OpenCLI daemon to not running.
- Debugging hypotheses: H1 focus helper returned success but OS foreground did not actually switch; H2 OpenCLI bind ignores foreground window and reuses existing session/tab state; H3 correct window was foregrounded but another Chrome window became active between focus and bind.
- T8 debug/fix completed: bind stdout URL validation/retry and daemon-status parsing were fixed, wrong-bind cleanup before bound_session success was added, real `python linkedin_scrap.py --mode update` exited 0, and latest LinkedIn full output contained posts.
- T8 re-verifier verdict: confirmed. Real QA evidence shows 63 pages, 608 unique IDs, parsed 608, latest LinkedIn full JSON 611 posts, daemon returned to baseline, and no LinkedIn collection window remained.
- T9 QA executor dispatched: `019f4637-12f2-7423-b0f9-bbbc151cb2d5`.
- T9 PASS: full update exit 0, latest total JSON 1771 posts, API count 1771, viewer top count 1771, `linkedin` search showed cards, OpenCLI debug banner 0, no OpenCLI process/session tab/LinkedIn collection window remained.
- T9 gate reviewer verdict: confirmed. `safe-trash.cmd` old-output cleanup warning is not a T9 blocker because update exit 0 and viewer/API/JSON counts match.
- T10 PASS: final status evidence saved to `.omo/evidence/linkedin-opencli-owned-window/t10-final-status.txt`; source/tests/output/plan-evidence files classified; no commit/stage/security-gate because commit was not requested.

## User-requested plan amendment verification
- T5 HWND ambiguity rule updated: 0/2+ candidates fail without closing Chrome; candidate info logged; WM_CLOSE only after owned handle recorded.
