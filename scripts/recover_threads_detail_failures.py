from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from thread_scrap_single import (
    AUTH_FILE,
    FAILURES_FILE,
    OUTPUT_DIR,
    _assert_threads_schema,
    collect_one,
    get_post_code,
    merge_thread_items,
)
from utils.post_schema import normalize_post
from utils.threads_http_adapter import (
    build_threads_headers,
    fetch_thread_html,
    load_threads_cookies,
)


def find_latest_file(output_dir, pattern):
    files = glob.glob(os.path.join(output_dir, pattern))
    if not files:
        return None
    files.sort(reverse=True)
    return files[0]


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, payload):
    with open(path, "w", encoding="utf-8-sig") as file:
        json.dump(payload, file, ensure_ascii=False, indent=4)


def get_failure_count(failure_info):
    if not isinstance(failure_info, dict):
        return 0
    try:
        return int(failure_info.get("fail_count") or failure_info.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def select_targets(full_posts, failures, codes=None, min_fail_count=3, limit=None):
    code_filter = set(codes or [])
    targets = []
    for index, post in enumerate(full_posts):
        code = get_post_code(post)
        if not code:
            continue
        if code_filter:
            if code not in code_filter:
                continue
        elif get_failure_count(failures.get(code)) < min_fail_count:
            continue
        if post.get("is_merged_thread") is True:
            continue
        username = post.get("user") or post.get("username")
        if not username:
            continue
        targets.append({"index": index, "code": code, "username": username, "post": post})
        if limit and len(targets) >= limit:
            break
    return targets


def build_recovered_post(existing_post, items, target_code):
    merged = merge_thread_items(items)
    if not merged:
        return None

    merged["sequence_id"] = existing_post.get("sequence_id")
    merged["crawled_at"] = existing_post.get("crawled_at") or datetime.now().isoformat()
    merged["platform_id"] = existing_post.get("platform_id") or target_code
    merged["code"] = existing_post.get("code") or target_code
    merged["url"] = existing_post.get("url") or merged.get("url")
    merged["root_code"] = existing_post.get("root_code") or target_code
    merged["is_detail_collected"] = True
    merged["is_merged_thread"] = True
    return normalize_post(merged)


def mark_simple_collected(simple_posts, recovered_codes):
    changed = 0
    for post in simple_posts:
        code = get_post_code(post)
        if not code:
            continue
        if code and not post.get("code"):
            post["code"] = code
            changed += 1
        if code in recovered_codes and post.get("is_detail_collected") is not True:
            post["is_detail_collected"] = True
            changed += 1
    return changed


def recover_failures(
    output_dir=OUTPUT_DIR,
    failures_file=FAILURES_FILE,
    auth_file=AUTH_FILE,
    codes=None,
    limit=None,
    min_fail_count=3,
    dry_run=False,
    cookie_loader=load_threads_cookies,
    header_builder=build_threads_headers,
    fetch_fn=fetch_thread_html,
):
    full_path = find_latest_file(output_dir, "threads_py_full_*.json")
    simple_path = find_latest_file(output_dir, "threads_py_simple_*.json")
    if not full_path:
        raise RuntimeError(f"threads full DB를 찾을 수 없습니다: {output_dir}")

    full_data = load_json(full_path, {"metadata": {}, "posts": []})
    simple_data = load_json(simple_path, {"metadata": {}, "posts": []})
    failures = load_json(failures_file, {}) or {}

    full_posts = full_data.get("posts", [])
    simple_posts = simple_data.get("posts", [])
    targets = select_targets(
        full_posts,
        failures,
        codes=codes,
        min_fail_count=min_fail_count,
        limit=limit,
    )

    cookies = cookie_loader(auth_file=auth_file)
    if not cookies:
        raise RuntimeError(f"Threads 인증 쿠키를 찾을 수 없습니다: {auth_file}")
    headers = header_builder()

    recovered_codes = []
    results = []

    for target in targets:
        code = target["code"]
        items = collect_one(
            code,
            target["username"],
            cookies,
            headers,
            fetch_fn=fetch_fn,
            snapshot_saver=None,
        )
        item_count = len(items)
        status = "skipped"
        if item_count > 1:
            status = "recoverable"
            if not dry_run:
                recovered = build_recovered_post(target["post"], items, code)
                if recovered:
                    full_posts[target["index"]] = recovered
                    recovered_codes.append(code)
                    failures.pop(code, None)
                    status = "updated"
        results.append({"code": code, "items": item_count, "status": status})

    updated_count = len(recovered_codes)
    if not dry_run and updated_count > 0:
        full_data["posts"] = full_posts
        full_data.setdefault("metadata", {})
        full_data["metadata"].update(
            {
                "updated_at": datetime.now().isoformat(),
                "total_count": len(full_posts),
            }
        )
        _assert_threads_schema(full_posts, "recover_full")
        save_json(full_path, full_data)

        if simple_path:
            mark_simple_collected(simple_posts, set(recovered_codes))
            simple_data["posts"] = simple_posts
            simple_data.setdefault("metadata", {})
            simple_data["metadata"].update(
                {
                    "updated_at": datetime.now().isoformat(),
                    "total_count": len(simple_posts),
                }
            )
            _assert_threads_schema(simple_posts, "recover_simple")
            save_json(simple_path, simple_data)

        with open(failures_file, "w", encoding="utf-8") as file:
            json.dump(failures, file, ensure_ascii=False, indent=4)

    return {
        "dry_run": dry_run,
        "target_count": len(targets),
        "recoverable_count": sum(1 for result in results if result["items"] > 1),
        "updated_count": updated_count,
        "full_path": full_path,
        "simple_path": simple_path,
        "results": results,
    }


def parse_codes(values):
    if not values:
        return None
    codes = []
    for value in values:
        codes.extend([part.strip() for part in value.split(",") if part.strip()])
    return codes or None


def main():
    parser = argparse.ArgumentParser(
        description="Recover Threads detail failures blocked by fail_count limits."
    )
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--failures-file", default=FAILURES_FILE)
    parser.add_argument("--auth-file", default=AUTH_FILE)
    parser.add_argument("--codes", nargs="*", help="Target code list or comma-separated codes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-fail-count", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = recover_failures(
        output_dir=args.output_dir,
        failures_file=args.failures_file,
        auth_file=args.auth_file,
        codes=parse_codes(args.codes),
        limit=args.limit,
        min_fail_count=args.min_fail_count,
        dry_run=args.dry_run,
    )

    print(
        f"[Recover] targets={result['target_count']} "
        f"recoverable={result['recoverable_count']} "
        f"updated={result['updated_count']} "
        f"write={'false' if result['dry_run'] else 'true'}"
    )
    for item in result["results"]:
        if item["items"] > 1:
            print(f"recoverable: {item['code']} items={item['items']} status={item['status']}")


if __name__ == "__main__":
    main()
