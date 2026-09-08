"""벤치마킹 계정의 LinkedIn 글을 계정 단위로 수집한다.

왜 이 파일이 필요한가
---------------------
`linkedin_scrap_by_user.py` 는 계정 하나를 손으로 지정해 긁는 독립 도구다.
벤치마킹 계정 목록(`web_viewer/benchmark_accounts.json`)을 **한 번도 읽지 않는다.**
그래서 화면에서 계정을 켜고 「수집 가능」 배지가 붙어도 아무도 안 긁었다 —
SPEC 은 LinkedIn 을 수집 가능으로 분류했는데 연결부가 없었다(수행계획 R-2).

이 파일이 그 연결부다. 수집 자체는 기존 도구에 맡기고, 여기서는
「켠 계정 고르기 → 호출 → 표식 붙여 통합본용 파일로 모으기」만 한다.
`youtube_scrap.py --channel` 이 같은 일을 하며, 그쪽 구조를 그대로 따랐다.

계획: _docs/20260906_03 (W3)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

from utils.benchmark_store import (
    KEEP_LIMIT,
    atomic_save_json,
    load_existing_posts,
    merge_and_cap,
    report_removed,
)
from utils.common import load_json
from utils.post_schema import normalize_post

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(PROJECT_ROOT, "web_viewer", "benchmark_accounts.json")
USER_DATA_ROOT = os.path.join(PROJECT_ROOT, "output_linkedin_user")
OUTPUT_DIR = os.path.join(USER_DATA_ROOT, "python")
DEFAULT_LIMIT = 5


def load_active_linkedin_accounts():
    """켜져 있고 LinkedIn 주소가 있는 계정만.

    `youtube_scrap.py:load_active_benchmark_accounts()` 와 같은 규칙이다 -
    status 가 active 가 아닌 계정은 수집 대상이 아니다.
    """
    override = os.environ.get("SNS_BENCHMARK_ACCOUNTS_PATH", "").strip()
    path = os.path.abspath(override) if override else ACCOUNTS_PATH
    data = load_json(path, {}) or {}
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        return []
    return [
        account for account in accounts
        if account.get("status") == "active"
        and (account.get("channels") or {}).get("linkedin")
    ]


def latest_full_file(slug: str):
    """그 계정 폴더의 최신 full 파일. 수집기가 계정별 폴더에 쌓는다."""
    directory = os.path.join(USER_DATA_ROOT, slug)
    if not os.path.isdir(directory):
        return None
    prefix = f"linkedin_{slug}_full_"
    files = [
        f for f in os.listdir(directory)
        if f.startswith(prefix) and f.endswith(".json") and "_total" not in f
    ]
    if not files:
        return None
    return os.path.join(directory, sorted(files)[-1])


def run_collector(slug: str, limit: int, dry_run: bool) -> bool:
    """기존 수집기를 그대로 부른다. 수집 로직을 여기서 다시 짜지 않는다."""
    command = [
        sys.executable, "-u", "linkedin_scrap_by_user.py",
        "--user", slug,
        "--limit", str(limit),
    ]
    print(f"   ▶ {' '.join(command)}")
    if dry_run:
        print("     (dry-run — 실행하지 않음)")
        return True
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"   ⚠️ 수집기가 {result.returncode} 로 끝났다 — 이 계정은 건너뛴다")
        return False
    return True


def to_standard(raw: dict, account: dict, slug: str) -> dict:
    """수집기 레코드를 표준 스키마로 옮기고 벤치마킹 표식을 붙인다.

    `is_saved=False` 와 `benchmark_accounts` 가 없으면 뷰어의
    `보임 = is_saved OR 켜진 계정` 판정에서 내 저장글과 구분되지 않는다.
    """
    post = dict(raw)
    # 수집기는 images 로 담는다. 표준은 media 다 — LEGACY_FIELD_MAP 에 없어
    # 여기서 옮기지 않으면 이미지가 통째로 사라진다.
    if post.get("images") and not post.get("media"):
        post["media"] = post.pop("images")
    post.pop("images", None)
    post["sns_platform"] = "linkedin"
    post["is_saved"] = False
    post["benchmark_accounts"] = [account.get("id")]
    post["source"] = f"benchmark:{account.get('id')}"
    post["is_own_post"] = False
    normalized = normalize_post(post)
    if not normalized.get("url") and normalized.get("code"):
        normalized["url"] = f"https://www.linkedin.com/feed/update/urn:li:activity:{normalized['code']}/"
    if not normalized.get("display_name"):
        normalized["display_name"] = account.get("name") or slug
    return normalized


def collect(limit_override: int | None, dry_run: bool, only: str | None):
    accounts = load_active_linkedin_accounts()
    if only:
        accounts = [a for a in accounts if a.get("id") == only]
    if not accounts:
        print("ℹ️ 켜진 LinkedIn 벤치마킹 계정이 없습니다.")
        return 0

    print(f"🎯 대상 계정 {len(accounts)}개")
    merged: list[dict] = []
    seen_codes: set[str] = set()
    collected_accounts = 0

    for account in accounts:
        slug = str((account.get("channels") or {}).get("linkedin") or "").strip()
        if not slug:
            continue
        limit = limit_override or int(account.get("limit") or DEFAULT_LIMIT)
        print(f"\n📌 {account.get('name') or account.get('id')} ({slug}) · 최대 {limit}편")

        if not run_collector(slug, limit, dry_run):
            continue

        full_file = latest_full_file(slug)
        if not full_file:
            print(f"   ⚠️ 산출물을 찾지 못했다: {os.path.join(USER_DATA_ROOT, slug)}")
            continue

        data = load_json(full_file, [])
        raw_posts = data.get("posts", []) if isinstance(data, dict) else (data or [])
        # 최신 limit 편만 통합본에 넣는다. 계정 폴더에는 과거 수집분이 쌓여 있어
        # 그대로 넣으면 상한이 무의미해진다.
        picked = raw_posts[:limit]
        added = 0
        for raw in picked:
            code = str(raw.get("code") or "")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            merged.append(to_standard(raw, account, slug))
            added += 1
        collected_accounts += 1
        print(f"   ✅ {added}편 ({os.path.basename(full_file)})")

    # 이번 수집분만 저장하면 직전 수집분이 통합본에서 사라진다 - merge_results()
    # 가 이 폴더의 최신 파일 하나만 읽기 때문이다. 쌓아서 저장한다.
    # 계획: _docs/20260908_01 (W1)
    existing = load_existing_posts(OUTPUT_DIR, "linkedin_user_full_")
    if not merged and not existing:
        print("\nℹ️ 통합본에 넣을 글이 없습니다.")
        return 0

    posts, removed = merge_and_cap(existing, merged)
    report_removed(removed)

    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(OUTPUT_DIR, f"linkedin_user_full_{stamp}.json")
    payload = {
        "metadata": {
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "crawl_mode": "benchmark",
            "platform": "linkedin",
            "account_count": collected_accounts,
            "post_count": len(posts),
            "new_count": len(merged),
            "keep_limit": KEEP_LIMIT,
        },
        "posts": posts,
    }
    if not atomic_save_json(out_path, payload):
        return 0
    print(
        f"\n💾 저장: {out_path} (누적 {len(posts)}편 · 이번 {len(merged)}편"
        f" · 계정 {collected_accounts}개)"
    )
    return len(posts)


def main():
    parser = argparse.ArgumentParser(
        description="벤치마킹 계정의 LinkedIn 글 수집 (계정 단위)"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="계정별 상한을 강제한다. 생략하면 계정 설정값(기본 5)")
    parser.add_argument("--only", type=str, default=None,
                        help="계정 id 하나만 돌린다. 연결부 검증용")
    parser.add_argument("--dry-run", action="store_true",
                        help="수집기를 부르지 않고 대상만 출력한다")
    args = parser.parse_args()

    count = collect(args.limit, args.dry_run, args.only)
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
