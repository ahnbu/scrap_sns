---
slug: linkedin-opencli-collection-surface
status: planned
intent: clear
pending-action: write .omo/plans/linkedin-opencli-collection-surface.md
approach: Restore the pre-OpenCLI user experience by isolating the LinkedIn OpenCLI collection surface from the user's SNS Scrap Chrome window, closing only the collection-owned target after success/failure, then unbinding/closing the OpenCLI browser session and stopping the daemon so the user window has no Chrome debugging banner.
---

# Draft: linkedin-opencli-collection-surface

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| C1 | LinkedIn OpenCLI collection surface is opened in an isolated collection-owned target, not by reusing the user's SNS Scrap tab/window. | active | `scripts/linkedin_opencli_shadow_collect.mjs:193`, OpenCLI `tab close --help` |
| C2 | Collection-owned target is closed on success and failure without closing SNS Scrap or unrelated user tabs. | active | OpenCLI `browser open` returns `page`; `browser tab close [targetId]` syntax verified |
| C3 | Browser debug attachment cleanup still runs after target cleanup: `unbind -> close -> daemon stop`. | active | `linkedin_scrap.py:185-188`, `scripts/linkedin_opencli_shadow_collect.mjs:64-67` |
| C4 | User-facing QA verifies only the correct outcome: SNS Scrap Chrome window has no OpenCLI debugging banner after collection. | active | User correction in current thread |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| assumption | adopted default | rationale | reversible? |
|---|---|---|---|
| Is "no LinkedIn tab in user Chrome" a direct completion criterion? | No. It is an implementation smell to prevent, not the user-facing check. | User clarified the user-facing criterion is the debug banner; LinkedIn collection should not use the user Chrome surface in the first place. | yes |
| Should implementation close arbitrary Chrome tabs/windows by title or URL? | No. Close only the targetId returned by OpenCLI for this collection run. | Avoids damaging the user's active SNS Scrap tab or unrelated browsing state. | yes |
| Should `unbind/close/daemon stop` remain? | Yes, after collection target cleanup. | It removes debug attachment/session/daemon state but is not enough to close the actual collection surface. | yes |
| Should the plan require full SNS scraping for every verification run? | No for fast RED/GREEN; yes for one final user-surface QA or a minimized `/api/run-scrap` update run if safe. | Full scraping is slow and intrusive; final browser-surface evidence is still mandatory. | yes |

## Findings (cited - path:lines)
- OpenCLI introduction changed LinkedIn from Playwright window lifecycle to OpenCLI browser session lifecycle. In commit `585a380`, `linkedin_scrap.py` used `chromium.launch`, `context.new_page()`, and `browser.close()`. In commit `02cd5fe`, `scripts/linkedin_opencli_shadow_collect.mjs` used `browser(session, ["open", url, "--window", "background"], ...)`.
- Current update path: `scrap_sns_server.py:1075-1110` starts `total_scrap.py --mode <mode>`; `total_scrap.py:351-411` starts `python -u linkedin_scrap.py --mode {mode}`; `linkedin_scrap.py:116-140` starts `scripts/linkedin_opencli_shadow_collect.mjs`.
- Current OpenCLI collection surface creation is centralized at `scripts/linkedin_opencli_shadow_collect.mjs:193`.
- Current JS cleanup at `scripts/linkedin_opencli_shadow_collect.mjs:64-67` runs only `unbind` and `close`.
- Current Python cleanup at `linkedin_scrap.py:185-188` runs `cleanup_opencli_browser_session()` and then `stop_opencli_daemon()`.
- OpenCLI CLI confirms targeted tab closing syntax: `opencli browser <session> tab close [targetId]`, where `targetId` is returned by `browser open`, `browser tab new`, or `browser tab list`.

## Decisions (with rationale)
- Restore the collection surface lifecycle, not just debug attachment cleanup.
- Treat `browser open`'s returned `page` targetId as the authoritative collection-owned target.
- Close only that collection-owned target in `finally`, before `unbind -> close -> daemon stop`.
- Do not search user's Chrome windows/tabs by title, URL, or active state.
- Do not make "LinkedIn tab absent from user Chrome" the user-facing completion criterion; the user-facing criterion is "SNS Scrap Chrome window has no OpenCLI debugging banner."

## Scope IN
- `scripts/linkedin_opencli_shadow_collect.mjs`: capture `browser open` return payload, preserve the `page` targetId, and close that target in `finally`.
- `linkedin_scrap.py`: ensure parent cleanup order still runs even if the JS collector exits non-zero, and add tests around cleanup behavior if the contract changes.
- `tests/integration/test_linkedin_opencli_pipeline.py` or a new focused test file: lock cleanup order and page-target behavior without relying on real LinkedIn.
- Evidence under `.omo/evidence/linkedin-opencli-collection-surface/`: RED/GREEN outputs and final browser-surface evidence.

## Scope OUT (Must NOT have)
- Do not close SNS Scrap tab.
- Do not close arbitrary Chrome windows.
- Do not close tabs by URL/title matching.
- Do not use OS-level window killing, `taskkill`, Alt+F4, or browser-process termination as the product fix.
- Do not change LinkedIn parsing, saved-post merge logic, image handling, or tag sync.
- Do not use "daemon not running" alone as completion proof; the user-facing Chrome banner must be checked.

## Open questions
- None blocking. If the worker discovers OpenCLI cannot force a separate window/profile with current CLI options, use the targetId lifecycle as the required minimum and record the limitation; do not fall back to closing user-visible tabs by URL.

## Approval gate
status: planned
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
Original user request explicitly asked to write the plan document. This draft records the decision-complete approach and does not authorize implementation.
