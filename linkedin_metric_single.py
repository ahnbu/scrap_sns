"""LinkedIn 참여지표 consumer - WAVE 2에서 상시 실행된다.

계획: _docs/20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획.md 3.3절

producer(linkedin_scrap.py)는 로그인 세션으로 저장글 목록을 받아 본문·저자·URL을
채우지만 지표는 응답에 없다(계획 2.2절). 이 consumer가 그 뒤를 이어받아
**로그인하지 않고** 공개 페이지에서 지표만 읽는다.

Threads·X의 *_scrap_single.py와 같은 자리에 있지만 인증을 쓰지 않으므로
auth_required 시그널을 내지 않는다. 실패는 일반 종료코드로만 보고한다.

대상 선정은 utils/linkedin_metrics.select_targets 가 담당하며, 1회 상한을 둬
「업데이트」 한 번이 지나치게 길어지지 않게 한다(계획 3.4절).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from scripts.linkedin_metric_backfill import (  # noqa: E402
    apply_metrics,
    clear_failure,
    failure_counts,
    latest_full_file,
    load_failures,
    load_full,
    record_failure,
    save_failures,
    save_full,
)
from utils.linkedin_metrics import (  # noqa: E402
    DEFAULT_RUN_LIMIT,
    extract_activity_id,
    fetch_metrics,
    new_anonymous_context,
    polite_sleep,
    select_targets,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="LinkedIn 참여지표 상시 갱신 (비로그인 consumer)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RUN_LIMIT,
        help=f"1회 처리 상한 (기본 {DEFAULT_RUN_LIMIT})",
    )
    parser.add_argument("--min-delay", type=float, default=4.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--save-every", type=int, default=25)
    args = parser.parse_args(argv)

    print("🔎 [LinkedIn] 참여지표 갱신 시작 (비로그인)", flush=True)

    full_path = latest_full_file()
    if not full_path:
        print("ℹ️ [LinkedIn] full 파일이 없어 지표 갱신을 건너뜁니다.", flush=True)
        return 0

    container, posts = load_full(full_path)
    failures = load_failures()

    targets = select_targets(
        posts, limit=args.limit, failure_counts=failure_counts(failures)
    )
    if not targets:
        print("✅ [LinkedIn] 갱신할 지표 대상이 없습니다.", flush=True)
        return 0

    print(f"🎯 [LinkedIn] 지표 갱신 대상 {len(targets)}건", flush=True)

    total = len(targets)
    ok = 0
    failed = 0
    started = time.time()

    with sync_playwright() as playwright:
        # headless 고정. 창이 뜨면 사용자 포커스를 뺏는다(계획 3.3절).
        browser = playwright.chromium.launch(headless=True)
        context = new_anonymous_context(browser)
        page = context.new_page()

        try:
            for index, post in enumerate(targets, start=1):
                activity_id = extract_activity_id(post.get("url"))
                if not activity_id:
                    failed += 1
                    continue

                try:
                    metrics = fetch_metrics(page, activity_id)
                except Exception as exc:  # noqa: BLE001 - 사유만 기록한다
                    metrics = None
                    reason = type(exc).__name__
                else:
                    reason = "no-metrics-in-dom"

                if metrics:
                    apply_metrics(post, metrics)
                    clear_failure(failures, activity_id)
                    ok += 1
                    print(
                        f"   ⚡ [Metric] [{activity_id}] "
                        f"like={metrics['like_count']} comment={metrics['comment_count']}",
                        flush=True,
                    )
                else:
                    record_failure(failures, activity_id, post.get("url", ""), reason)
                    failed += 1
                    print(f"   ⚠️ [Metric] [{activity_id}] 실패 ({reason})", flush=True)

                if index % args.save_every == 0:
                    save_full(full_path, container, posts)
                    save_failures(failures)

                if index < total:
                    polite_sleep(args.min_delay, args.max_delay)
        finally:
            save_full(full_path, container, posts)
            save_failures(failures)
            browser.close()

    elapsed = (time.time() - started) / 60
    print(
        f"✅ [LinkedIn] 지표 갱신 완료 - 성공 {ok} / 실패 {failed} / 대상 {total} "
        f"({elapsed:.1f}분)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
