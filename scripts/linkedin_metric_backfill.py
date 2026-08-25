"""LinkedIn 참여지표 백필 - 비로그인 공개 페이지에서 지표만 채운다.

계획: _docs/20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획.md

본문·저자·URL 은 절대 건드리지 않는다. 지표 필드와 metrics_updated_at 만 채운다.
로그인하지 않으므로 계정 리스크가 없다. 남는 위험은 IP 단위 속도 제한뿐이라
건당 지연과 배치 휴지로 낮춘다.

사용 예:
    python scripts/linkedin_metric_backfill.py --limit 30 --dry-run
    python scripts/linkedin_metric_backfill.py --limit 30
    python scripts/linkedin_metric_backfill.py            # 전량
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from utils.common import load_json, save_json  # noqa: E402
from utils.linkedin_metrics import (  # noqa: E402
    extract_activity_id,
    fetch_metrics,
    new_anonymous_context,
    polite_sleep,
    select_targets,
)

DATA_DIR = os.path.join(REPO_ROOT, "output_linkedin", "python")
FULL_GLOB = os.path.join(DATA_DIR, "linkedin_py_full_*.json")
FAILURE_FILE = os.path.join(REPO_ROOT, "scrap_failures_linkedin.json")

# 지표만 갱신하므로 이 필드 외에는 어떤 키도 쓰지 않는다.
WRITABLE_FIELDS = ("like_count", "comment_count", "metrics_updated_at")

MAX_FAILURES = 3


def latest_full_file() -> str | None:
    files = sorted(glob.glob(FULL_GLOB))
    return files[-1] if files else None


def load_full(path: str):
    """BOM 포함 JSON 을 안전하게 읽는다(utils.common.load_json 은 utf-8-sig)."""
    data = load_json(path, default=None)
    if isinstance(data, dict):
        return data, data.get("posts", [])
    return None, (data or [])


def save_full(path: str, container, posts) -> None:
    payload = posts if container is None else {**container, "posts": posts}
    save_json(path, payload, indent=2)


def load_failures() -> dict:
    data = load_json(FAILURE_FILE, default={})
    return data if isinstance(data, dict) else {}


def save_failures(failures: dict) -> None:
    save_json(FAILURE_FILE, failures, indent=2)


def failure_counts(failures: dict) -> dict:
    return {aid: entry.get("count", 0) for aid, entry in failures.items()}


def record_failure(failures: dict, activity_id: str, url: str, reason: str) -> None:
    entry = failures.get(activity_id) or {"count": 0}
    entry["count"] = entry.get("count", 0) + 1
    entry["url"] = url
    entry["reason"] = reason
    entry["last_failed_at"] = datetime.now().isoformat(timespec="milliseconds")
    failures[activity_id] = entry


def clear_failure(failures: dict, activity_id: str) -> None:
    failures.pop(activity_id, None)


def backup_full(path: str) -> str:
    """실행 전 원본을 통째로 복사한다(계획 3.7절).

    `_backup_*/` 는 .gitignore 에 이미 걸려 있어 커밋되지 않는다.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(REPO_ROOT, f"_backup_linkedin_metrics_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, os.path.basename(path))
    shutil.copy2(path, dest)

    # 무결성 확인 - 게시글 수가 다르면 백업이 깨진 것이므로 진행하지 않는다.
    _c1, original = load_full(path)
    _c2, copied = load_full(dest)
    if len(original) != len(copied):
        raise RuntimeError(
            f"백업 무결성 실패: 원본 {len(original)}건 vs 백업 {len(copied)}건"
        )
    print(f"[백업] {dest} ({len(copied)}건)", flush=True)
    return dest


def apply_metrics(post: dict, metrics: dict) -> bool:
    """지표 필드만 갱신한다. 기존 값이 있으면 새 값으로 바꾼다.

    본문·저자·URL 등 다른 키는 건드리지 않는다.
    """
    changed = False
    for field in WRITABLE_FIELDS:
        value = metrics.get(field)
        if value is None:
            continue
        if post.get(field) != value:
            post[field] = value
            changed = True
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LinkedIn 참여지표 백필 (비로그인)")
    parser.add_argument("--limit", type=int, default=0, help="처리 상한. 0이면 전량")
    parser.add_argument("--batch-size", type=int, default=50, help="배치 크기")
    parser.add_argument("--batch-pause", type=float, default=20.0, help="배치 간 휴지(초)")
    parser.add_argument("--min-delay", type=float, default=4.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--dry-run", action="store_true", help="대상만 세고 종료")
    parser.add_argument("--no-backup", action="store_true", help="백업 생략(파일럿 재실행용)")
    parser.add_argument(
        "--fail-rate-limit",
        type=float,
        default=0.20,
        help="배치 실패율이 이 값을 넘으면 중단",
    )
    args = parser.parse_args(argv)

    full_path = latest_full_file()
    if not full_path:
        print("❌ linkedin_py_full_*.json 을 찾지 못했습니다.")
        return 1
    print(f"[대상 파일] {os.path.basename(full_path)}")

    container, posts = load_full(full_path)
    failures = load_failures()

    targets = select_targets(
        posts,
        limit=None if args.limit == 0 else args.limit,
        failure_counts=failure_counts(failures),
    )
    print(f"[대상] {len(targets)}건 / 전체 LinkedIn {sum(1 for p in posts if (p.get('sns_platform') or '').lower() == 'linkedin')}건")

    if args.dry_run:
        for post in targets[:10]:
            print(f"   - {extract_activity_id(post.get('url'))} like={post.get('like_count')}")
        return 0

    if not targets:
        print("갱신할 대상이 없습니다.")
        return 0

    if not args.no_backup:
        backup_full(full_path)

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
                except Exception as exc:  # noqa: BLE001 - 실패 사유를 기록만 한다
                    metrics = None
                    reason = f"{type(exc).__name__}"
                else:
                    reason = "no-metrics-in-dom"

                if metrics:
                    apply_metrics(post, metrics)
                    clear_failure(failures, activity_id)
                    ok += 1
                    print(
                        f"[{index}/{total}] {activity_id} "
                        f"like={metrics['like_count']} comment={metrics['comment_count']}",
                        flush=True,
                    )
                else:
                    record_failure(failures, activity_id, post.get("url", ""), reason)
                    failed += 1
                    print(f"[{index}/{total}] {activity_id} 실패 ({reason})", flush=True)

                # 배치 경계 - 저장하고 실패율을 확인한다.
                if index % args.batch_size == 0 or index == total:
                    save_full(full_path, container, posts)
                    save_failures(failures)

                    processed = ok + failed
                    fail_rate = (failed / processed) if processed else 0.0
                    elapsed = time.time() - started
                    print(
                        f"--- 배치 저장 {index}/{total} "
                        f"성공 {ok} 실패 {failed} 실패율 {fail_rate:.1%} "
                        f"경과 {elapsed / 60:.1f}분",
                        flush=True,
                    )

                    if fail_rate > args.fail_rate_limit and processed >= args.batch_size:
                        print(
                            f"❌ 실패율 {fail_rate:.1%} > 한도 {args.fail_rate_limit:.0%} — 중단합니다.",
                            flush=True,
                        )
                        break

                    if index < total:
                        time.sleep(args.batch_pause)

                if index < total:
                    polite_sleep(args.min_delay, args.max_delay)
        finally:
            save_full(full_path, container, posts)
            save_failures(failures)
            browser.close()

    processed = ok + failed
    fail_rate = (failed / processed) if processed else 0.0
    print("")
    print(f"[완료] 처리 {processed}/{total} · 성공 {ok} · 실패 {failed} · 실패율 {fail_rate:.1%}")
    print(f"[소요] {(time.time() - started) / 60:.1f}분")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
