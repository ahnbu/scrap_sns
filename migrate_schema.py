"""Normalize legacy records into the current schema.

종전에는 Threads 레코드만 봤다. 그래서 유튜브·링크드인·X 는 검사 대상이 0건이라
에러 없이 통과했고, 「스키마 점검 통과」가 그 플랫폼에 대해서는 아무 뜻이 없었다
(2026-09-06 발견). 지금은 플랫폼을 가리지 않는다.

`--platform` 으로 좁힐 수 있지만 기본값은 전체다 - 좁히는 쪽을 명시적으로 만든다.
계획: _docs/20260906_01 (P0)
"""

import argparse
import glob
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from utils.post_schema import normalize_post, validate_post


THREADS_ALIASES = ("thread", "threads")


def _platform_of(post: dict) -> str:
    return str(post.get("sns_platform") or "").lower()


def _in_scope(post: dict, platform: str) -> bool:
    """platform 이 빈 값이면 전 플랫폼이 대상이다."""
    if not platform:
        return True
    wanted = platform.lower()
    actual = _platform_of(post)
    if wanted in THREADS_ALIASES:
        return actual in THREADS_ALIASES
    return actual == wanted


def migrate_file(path: Path, apply: bool, platform: str = "") -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    posts = data.get("posts", data) if isinstance(data, dict) else data
    changed = 0
    still_bad = []

    for idx, post in enumerate(posts):
        if not _in_scope(post, platform):
            continue

        before_missing = validate_post(post)
        if not before_missing:
            continue

        normalized = normalize_post(post)
        if not normalized.get("source"):
            normalized["source"] = "legacy_migration"

        after_missing = validate_post(normalized)
        if after_missing:
            still_bad.append((idx, normalized.get("platform_id") or normalized.get("code"), after_missing))
            continue

        posts[idx] = normalized
        changed += 1

    if apply and changed:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    in_scope = [post for post in posts if _in_scope(post, platform)]
    by_platform = Counter(_platform_of(post) or "(unknown)" for post in in_scope)
    return {
        "file": str(path),
        "changed": changed,
        "total_in_scope": len(in_scope),
        "by_platform": dict(sorted(by_platform.items())),
        "still_bad": len(still_bad),
        "still_bad_samples": still_bad[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--platform",
        default="",
        help="특정 플랫폼만 검사(threads/linkedin/youtube/x). 기본값은 전 플랫폼",
    )
    args = parser.parse_args()

    paths = [Path(path) for path in glob.glob(args.target)]
    if not paths:
        print(f"[ERROR] no files match {args.target}", file=sys.stderr)
        raise SystemExit(1)

    total_changed = 0
    for path in paths:
        result = migrate_file(path, args.apply, args.platform)
        prefix = "[APPLY]" if args.apply else "[DRY]"
        print(
            f"{prefix} {result['file']}: changed={result['changed']}/{result['total_in_scope']} "
            f"still_bad={result['still_bad']}"
        )
        # 플랫폼별 건수를 반드시 찍는다. 어떤 플랫폼이 0건으로 조용히 빠졌는지
        # 출력만 보고 알 수 있어야 "점검 통과"가 뜻을 갖는다.
        counts = " ".join(f"{name}={count}" for name, count in result["by_platform"].items())
        print(f"  scanned: {counts or '(none)'}")
        for idx, code, missing in result["still_bad_samples"]:
            print(f"  still_bad: idx={idx} code={code} missing={missing}")
        total_changed += result["changed"]

    print(f"=== TOTAL changed: {total_changed} ===")


if __name__ == "__main__":
    main()
