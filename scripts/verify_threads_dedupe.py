"""Assert that the Threads duplicate backlog is cleared.

Exits 0 when every assertion holds, 1 otherwise.

Baseline measured on 2026-08-24 before the cleanup:
  - threads full DB held 1,268 records
  - 20 groups shared a platform_id (21 excess records)
  - 9 groups shared a pk; 7 of those also shared the code
  - the merged total carried 1,247 threads records, because merge_results()
    silently dropped the 21 platform_id duplicates
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os

OUTPUT_DIR = "output_threads/python"
TOTAL_DIR = "output_total"
ALIAS_STATUS = "duplicate_of_canonical"


def latest_file(directory, pattern):
    files = sorted(glob.glob(os.path.join(directory, pattern)), reverse=True)
    return files[0] if files else None


def load_posts(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)
    return data.get("posts", []) if isinstance(data, dict) else data


def get_code(post):
    return post.get("code") or post.get("platform_id")


def dup_groups(values):
    counter = collections.Counter(v for v in values if v)
    return {k: v for k, v in counter.items() if v > 1}


def main():
    parser = argparse.ArgumentParser(description="Verify the Threads dedupe result.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--total-dir", default=TOTAL_DIR)
    parser.add_argument("--expected-full", type=int, default=1247)
    parser.add_argument("--expected-total", type=int, default=1244)
    parser.add_argument("--expected-alias", type=int, default=3)
    args = parser.parse_args()

    full_path = latest_file(args.output_dir, "threads_py_full_*.json")
    total_path = latest_file(args.total_dir, "total_full_*.json")
    if not full_path or not total_path:
        print("❌ 대상 파일을 찾을 수 없습니다.")
        return 1

    posts = load_posts(full_path)
    total_threads = [
        p
        for p in load_posts(total_path)
        if str(p.get("sns_platform") or "").lower() == "threads"
    ]

    code_dups = dup_groups(str(get_code(p) or "") for p in posts)
    live = [p for p in posts if p.get("detail_status") != ALIAS_STATUS]
    pk_dups = dup_groups(str(p.get("pk") or "") for p in live)
    alias_count = sum(1 for p in posts if p.get("detail_status") == ALIAS_STATUS)

    checks = [
        (
            "platform_id 중복 그룹 (기준 20 → 0)",
            len(code_dups) == 0,
            len(code_dups),
        ),
        (
            "alias 제외 후 pk 중복 그룹 (기준 9 → 0)",
            len(pk_dups) == 0,
            len(pk_dups),
        ),
        (
            f"threads full 총 건수 (기준 1268 → {args.expected_full})",
            len(posts) == args.expected_full,
            len(posts),
        ),
        (
            f"{ALIAS_STATUS} 표시 건수 (기준 0 → {args.expected_alias})",
            alias_count == args.expected_alias,
            alias_count,
        ),
        (
            f"통합본 threads 건수 (기준 1247 → {args.expected_total})",
            len(total_threads) == args.expected_total,
            len(total_threads),
        ),
    ]

    print(f"원천: {os.path.basename(full_path)} ({len(posts)}건)")
    print(f"통합: {os.path.basename(total_path)} (threads {len(total_threads)}건)")
    print()

    failed = 0
    for label, passed, actual in checks:
        mark = "✅" if passed else "❌"
        print(f"{mark} {label} → 실측 {actual}")
        if not passed:
            failed += 1

    if failed:
        print(f"\n{failed}개 단언 실패")
        for code, count in list(code_dups.items())[:5]:
            print(f"   platform_id 중복 x{count}: {code}")
        for pk, count in list(pk_dups.items())[:5]:
            codes = sorted({str(get_code(p)) for p in live if str(p.get("pk") or "") == pk})
            print(f"   pk 중복 x{count}: {pk} → {codes}")
        return 1

    print("\n전체 단언 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
