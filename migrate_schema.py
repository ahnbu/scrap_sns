"""Normalize legacy Threads records into the current schema."""

import argparse
import glob
import json
import shutil
import sys
from pathlib import Path

from utils.post_schema import normalize_post, validate_post


def migrate_file(path: Path, apply: bool) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    posts = data.get("posts", data) if isinstance(data, dict) else data
    changed = 0
    still_bad = []

    for idx, post in enumerate(posts):
        if (post.get("sns_platform") or "").lower() not in ("thread", "threads"):
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

    total_threads = sum(
        1 for post in posts if (post.get("sns_platform") or "").lower() in ("thread", "threads")
    )
    return {
        "file": str(path),
        "changed": changed,
        "total_threads": total_threads,
        "still_bad": len(still_bad),
        "still_bad_samples": still_bad[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    paths = [Path(path) for path in glob.glob(args.target)]
    if not paths:
        print(f"[ERROR] no files match {args.target}", file=sys.stderr)
        raise SystemExit(1)

    total_changed = 0
    for path in paths:
        result = migrate_file(path, args.apply)
        prefix = "[APPLY]" if args.apply else "[DRY]"
        print(
            f"{prefix} {result['file']}: changed={result['changed']}/{result['total_threads']} "
            f"still_bad={result['still_bad']}"
        )
        for idx, code, missing in result["still_bad_samples"]:
            print(f"  still_bad: idx={idx} code={code} missing={missing}")
        total_changed += result["changed"]

    print(f"=== TOTAL changed: {total_changed} ===")


if __name__ == "__main__":
    main()
