"""벤치마킹 수집이 통합본까지 도달했는지 플랫폼별로 기계 판정한다.

수집 프로세스가 성공했다는 것과 화면에 나온다는 것은 다르다. 이 레포는
그 사이에서 여러 번 샜다 - `merge_results()` 에 소스 한 줄을 안 넣어
수집은 되는데 통합본에 영원히 안 들어간 사례가 linkedin_own·youtube_user
두 번 있었다. 그래서 판정 기준을 「최신 통합본에 있는가」로 잡는다.

  L1 최신 통합본에 그 플랫폼 벤치마킹 레코드가 있다
  L2 그 레코드 전부에 benchmark_accounts 가 붙어 있다
  L3 code 기준 중복이 없다
  L4 url·created_at 이 전부 채워져 있다
  L5 그 플랫폼 전체 좋아요 결측률이 기준치를 넘지 않는다
  L6 created_at 이 KST naive 형식이고 미래 시각이 없다

Usage:
  python scripts/verify_benchmark_platform.py --platform linkedin
  python scripts/verify_benchmark_platform.py --platform threads
계획: _docs/20260906_03 (W3·W4)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL_DIR = os.path.join(PROJECT_ROOT, "output_total")
KST_NAIVE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

checks: list[tuple[str, bool]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}{f' — {detail}' if detail else ''}")


def latest_total() -> str | None:
    files = sorted(glob.glob(os.path.join(TOTAL_DIR, "total_full_*.json")))
    return files[-1] if files else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["linkedin", "threads", "youtube"])
    parser.add_argument("--max-missing-rate", type=float, default=0.10,
                        help="좋아요 결측 허용 비율 (기본 0.10)")
    args = parser.parse_args()
    platform = args.platform

    path = latest_total()
    if not path:
        record(f"L1 최신 통합본에 {platform} 벤치마킹 레코드가 있다", False, "통합본 없음")
        return 1

    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    posts = data.get("posts", data) if isinstance(data, dict) else data
    print(f"통합본: {os.path.basename(path)} · 전체 {len(posts)}건 · 플랫폼 {platform}")

    bench = [
        p for p in posts
        if p.get("sns_platform") == platform and p.get("is_saved") is False
    ]
    record(f"L1 최신 통합본에 {platform} 벤치마킹 레코드가 있다",
           len(bench) > 0, f"{len(bench)}건")

    no_account = [p for p in bench if not (p.get("benchmark_accounts") or [])]
    record("L2 그 레코드 전부에 benchmark_accounts 가 붙어 있다",
           len(bench) > 0 and not no_account, f"누락 {len(no_account)}건")

    codes = [str(p.get("code") or "") for p in bench]
    dupes = len(codes) - len(set(codes))
    record("L3 code 기준 중복이 없다", dupes == 0 and "" not in codes,
           f"중복 {dupes}건 · 빈 code {codes.count('')}건")

    missing_url = [p for p in bench if not p.get("url")]
    missing_date = [p for p in bench if not p.get("created_at")]
    record("L4 url·created_at 이 전부 채워져 있다",
           not missing_url and not missing_date,
           f"url 누락 {len(missing_url)} · created_at 누락 {len(missing_date)}")

    same_platform = [p for p in posts if p.get("sns_platform") == platform]
    missing_like = [p for p in same_platform if p.get("like_count") in (None, "")]
    rate = (len(missing_like) / len(same_platform)) if same_platform else 1.0
    record("L5 좋아요 결측률이 기준치 이하다",
           rate <= args.max_missing_rate,
           f"{len(missing_like)}/{len(same_platform)} = {rate:.1%} (허용 {args.max_missing_rate:.0%})")

    # 하류에 UTC 를 흘리면 날짜 정렬·필터·검색이 9시간 어긋난다. X 가 그 결함을
    # 5개월간 안고 있었다(_docs/20260905_01). 형식과 미래 시각으로 잡는다.
    tomorrow = datetime.now() + timedelta(days=1)
    bad_format = [p for p in bench if not KST_NAIVE.match(str(p.get("created_at") or ""))]
    future = []
    for post in bench:
        try:
            when = datetime.strptime(str(post.get("created_at")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if when > tomorrow:
            future.append(post)
    record("L6 created_at 이 KST naive 형식이고 미래 시각이 없다",
           not bad_format and not future,
           f"형식 위반 {len(bad_format)} · 미래 시각 {len(future)}")

    by_account: dict[str, int] = {}
    for post in bench:
        for account_id in (post.get("benchmark_accounts") or []):
            by_account[account_id] = by_account.get(account_id, 0) + 1
    if by_account:
        print("계정별: " + " · ".join(f"{k} {v}" for k, v in sorted(by_account.items())))

    failed = [name for name, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
