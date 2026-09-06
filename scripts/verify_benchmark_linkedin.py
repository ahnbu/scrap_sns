"""LinkedIn 벤치마킹 수집이 통합본까지 도달했는지 기계 판정한다.

수집 프로세스가 성공했다는 것과 화면에 나온다는 것은 다르다. 이 레포는
그 사이에서 여러 번 샜다 - `merge_results()` 에 소스 한 줄을 안 넣어
수집은 되는데 통합본에 영원히 안 들어간 사례가 linkedin_own·youtube_user
두 번 있었다. 그래서 판정 기준을 「최신 통합본에 있는가」로 잡는다.

  L1 최신 통합본에 LinkedIn 벤치마킹 레코드가 있다
  L2 그 레코드 전부에 benchmark_accounts 가 붙어 있다
  L3 code(activity id) 기준 중복이 없다
  L4 url·created_at 이 전부 채워져 있다
  L5 LinkedIn 전체 좋아요 결측률이 기준치를 넘지 않는다

Usage: python scripts/verify_benchmark_linkedin.py [--max-missing-rate 0.10]
계획: _docs/20260906_03 (W3)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL_DIR = os.path.join(PROJECT_ROOT, "output_total")

checks: list[tuple[str, bool]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}{f' — {detail}' if detail else ''}")


def latest_total() -> str | None:
    files = sorted(glob.glob(os.path.join(TOTAL_DIR, "total_full_*.json")))
    return files[-1] if files else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-missing-rate", type=float, default=0.10,
                        help="LinkedIn 좋아요 결측 허용 비율 (기본 0.10)")
    args = parser.parse_args()

    path = latest_total()
    if not path:
        record("L1 최신 통합본에 LinkedIn 벤치마킹 레코드가 있다", False, "통합본 없음")
        return 1

    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    posts = data.get("posts", data) if isinstance(data, dict) else data
    print(f"통합본: {os.path.basename(path)} · 전체 {len(posts)}건")

    bench = [
        p for p in posts
        if p.get("sns_platform") == "linkedin" and p.get("is_saved") is False
    ]
    record("L1 최신 통합본에 LinkedIn 벤치마킹 레코드가 있다",
           len(bench) > 0, f"{len(bench)}건")

    no_account = [p for p in bench if not (p.get("benchmark_accounts") or [])]
    record("L2 그 레코드 전부에 benchmark_accounts 가 붙어 있다",
           len(bench) > 0 and not no_account,
           f"누락 {len(no_account)}건")

    codes = [str(p.get("code") or "") for p in bench]
    dupes = len(codes) - len(set(codes))
    record("L3 code 기준 중복이 없다", dupes == 0 and "" not in codes,
           f"중복 {dupes}건 · 빈 code {codes.count('')}건")

    missing_url = [p for p in bench if not p.get("url")]
    missing_date = [p for p in bench if not p.get("created_at")]
    record("L4 url·created_at 이 전부 채워져 있다",
           not missing_url and not missing_date,
           f"url 누락 {len(missing_url)} · created_at 누락 {len(missing_date)}")

    all_linkedin = [p for p in posts if p.get("sns_platform") == "linkedin"]
    missing_like = [p for p in all_linkedin if p.get("like_count") in (None, "")]
    rate = (len(missing_like) / len(all_linkedin)) if all_linkedin else 1.0
    record("L5 LinkedIn 좋아요 결측률이 기준치 이하다",
           rate <= args.max_missing_rate,
           f"{len(missing_like)}/{len(all_linkedin)} = {rate:.1%} (허용 {args.max_missing_rate:.0%})")

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
