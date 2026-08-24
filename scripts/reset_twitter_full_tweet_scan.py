"""Reset legacy ``full_tweet_scan`` X records so they can be re-collected.

The deleted pre-``ee9fb37`` detail collector overwrote ``username``, ``url`` and
``full_text`` with values read from whatever page the browser happened to show,
leaving 36 records carrying another account's body text and 16 of them pointing
at the wrong author. ``display_name`` was never overwritten, so it still holds
the correct author.

This script clears the poisoned fields and marks the records for re-collection.
``twitter_scrap_single.py`` then refetches each tweet by id and rewrites
``username``, ``url`` and ``full_text`` from the CLI payload.

``date`` is re-synced here on purpose: ``twitter_scrap_single.py`` only rewrites
``date`` when ``created_at`` is missing, and ``created_at`` is preserved, so the
re-collection would leave the crawl-date contamination untouched.
"""

from __future__ import annotations

import argparse
import glob
import json
import os

OUTPUT_DIR = "output_twitter/python"
TARGET_SOURCE = "full_tweet_scan"
FILE_PATTERNS = ("twitter_py_simple_*.json", "twitter_py_full_*.json")


def latest_file(output_dir, pattern):
    files = sorted(glob.glob(os.path.join(output_dir, pattern)), reverse=True)
    return files[0] if files else None


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, data):
    with open(path, "w", encoding="utf-8-sig") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def reset_post(post):
    """Reset one record in place. Return the list of changed field names."""
    changed = []

    platform_id = str(post.get("platform_id") or post.get("id") or "").strip()
    if not platform_id:
        return changed

    target_url = f"https://x.com/i/status/{platform_id}"
    if post.get("url") != target_url:
        post["url"] = target_url
        changed.append("url")

    if post.get("username"):
        post["username"] = ""
        changed.append("username")

    if post.get("full_text"):
        post["full_text"] = ""
        changed.append("full_text")

    if post.get("is_detail_collected") is not False:
        post["is_detail_collected"] = False
        changed.append("is_detail_collected")

    created_at = str(post.get("created_at") or "")
    if created_at:
        expected_date = created_at[:10]
        if post.get("date") != expected_date:
            post["date"] = expected_date
            changed.append("date")

    return changed


def reset_file(path, apply_changes):
    data = load_json(path)
    posts = data.get("posts", [])

    targets = [post for post in posts if post.get("source") == TARGET_SOURCE]
    field_counts = {}
    for post in targets:
        for field in reset_post(post):
            field_counts[field] = field_counts.get(field, 0) + 1

    if apply_changes and targets:
        data["posts"] = posts
        save_json(path, data)

    return {
        "path": path,
        "total": len(posts),
        "targets": len(targets),
        "fields": field_counts,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reset legacy full_tweet_scan X records for re-collection."
    )
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    apply_changes = args.apply
    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(f"[{mode}] source == '{TARGET_SOURCE}' 레코드 리셋")

    results = []
    for pattern in FILE_PATTERNS:
        path = latest_file(args.output_dir, pattern)
        if not path:
            print(f"   ⚠️ 대상 파일 없음: {pattern}")
            continue
        result = reset_file(path, apply_changes)
        results.append(result)
        print(f"\n   파일: {os.path.basename(result['path'])}")
        print(f"   전체 {result['total']}건 / 대상 {result['targets']}건")
        for field, count in sorted(result["fields"].items()):
            print(f"      - {field}: {count}건 변경")
        if not result["fields"]:
            print("      - 변경 없음")

    if not apply_changes:
        print("\n   dry-run 이므로 파일을 쓰지 않았습니다. --apply 로 반영하세요.")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
