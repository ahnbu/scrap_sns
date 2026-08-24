"""Assert that the legacy ``full_tweet_scan`` contamination is gone.

Exits 0 when every assertion holds, 1 otherwise, so the check can gate a
pipeline without anyone reading the output.

Baseline measured on 2026-08-24 before the reset:
  - ``kana_option`` carried 13 distinct display names (16 tweets, wrong author)
  - X records had only 62 distinct bodies out of 95
  - 61 records had ``date`` set to the crawl date instead of the post date
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os

OUTPUT_DIR = "output_twitter/python"
TOTAL_DIR = "output_total"


def latest_file(directory, pattern):
    files = sorted(glob.glob(os.path.join(directory, pattern)), reverse=True)
    return files[0] if files else None


def load_posts(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)
    return data.get("posts", []) if isinstance(data, dict) else data


def x_posts(posts):
    return [p for p in posts if str(p.get("sns_platform") or "").lower() == "x"]


def main():
    parser = argparse.ArgumentParser(description="Verify the X full_tweet_scan reset.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--total-dir", default=TOTAL_DIR)
    parser.add_argument(
        "--min-unique-text",
        type=int,
        default=90,
        help="Minimum distinct bodies expected across X records (baseline was 62 of 95).",
    )
    args = parser.parse_args()

    simple_path = latest_file(args.output_dir, "twitter_py_simple_*.json")
    total_path = latest_file(args.total_dir, "total_full_*.json")
    if not simple_path or not total_path:
        print("❌ 대상 파일을 찾을 수 없습니다.")
        return 1

    posts = load_posts(simple_path)
    total_x = x_posts(load_posts(total_path))

    kana_names = {
        p.get("display_name") for p in posts if p.get("username") == "kana_option"
    }
    unique_bodies = len({(p.get("full_text") or "")[:40] for p in posts})
    date_mismatch = sum(
        1
        for p in posts
        if (p.get("created_at") or "") and p.get("date") != str(p["created_at"])[:10]
    )
    empty_user = sum(1 for p in posts if not (p.get("username") or "").strip())
    empty_text = sum(1 for p in posts if not (p.get("full_text") or "").strip())

    checks = [
        (
            "kana_option display_name 고유 개수 (기준 13 → 1 이하)",
            len(kana_names) <= 1,
            len(kana_names),
        ),
        (
            f"X 고유 본문 개수 (기준 62 → {args.min_unique_text} 이상)",
            unique_bodies >= args.min_unique_text,
            unique_bodies,
        ),
        (
            "date != created_at[:10] 건수 (기준 61 → 0)",
            date_mismatch == 0,
            date_mismatch,
        ),
        (
            "username 이 빈 레코드 (재수집 실패 잔재, 기대 0)",
            empty_user == 0,
            empty_user,
        ),
        (
            "full_text 가 빈 레코드 (재수집 실패 잔재, 기대 0)",
            empty_text == 0,
            empty_text,
        ),
        (
            f"통합본 X 건수 (기대 {len(posts)})",
            len(total_x) == len(posts),
            len(total_x),
        ),
    ]

    print(f"원천: {os.path.basename(simple_path)} ({len(posts)}건)")
    print(f"통합: {os.path.basename(total_path)} (X {len(total_x)}건)")
    print()

    failed = 0
    for label, passed, actual in checks:
        mark = "✅" if passed else "❌"
        print(f"{mark} {label} → 실측 {actual}")
        if not passed:
            failed += 1

    if failed:
        print(f"\n{failed}개 단언 실패")
        if kana_names:
            print(f"   kana_option display_name: {sorted(n for n in kana_names if n)}")
        dup = collections.Counter((p.get("full_text") or "")[:40] for p in posts)
        for text, count in dup.most_common(3):
            if count > 1:
                users = {p.get("username") for p in posts if (p.get("full_text") or "").startswith(text)}
                print(f"   중복 {count}건 | {text[:40]!r} | username: {sorted(u for u in users if u)}")
        return 1

    print("\n전체 단언 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
