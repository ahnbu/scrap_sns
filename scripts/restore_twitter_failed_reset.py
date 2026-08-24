"""Restore X records that were reset but could not be re-collected.

``reset_twitter_full_tweet_scan.py`` clears ``username``/``full_text`` for every
``full_tweet_scan`` record because the legacy collector could have poisoned any
of them. Records that then fail re-collection would be left blank, which is
worse than the pre-reset state for the records that were never poisoned.

This restores those from a backup copy, but keeps the ``date`` fix: ``date`` is
recomputed from ``created_at`` rather than copied, since the crawl-date
contamination is exactly what the reset was for.

Only records whose backup ``username`` and ``display_name`` are consistent are
restored automatically -- a mismatch is the signature of the author-overwrite
bug, and those must not be revived.
"""

from __future__ import annotations

import argparse
import glob
import json
import os

OUTPUT_DIR = "output_twitter/python"
PATTERNS = ("twitter_py_simple_*.json", "twitter_py_full_*.json")


def latest_file(output_dir, pattern):
    files = sorted(glob.glob(os.path.join(output_dir, pattern)), reverse=True)
    return files[0] if files else None


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, data):
    with open(path, "w", encoding="utf-8-sig") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def index_by_id(posts):
    return {str(p.get("platform_id") or p.get("id") or ""): p for p in posts}


def build_display_name_map(posts):
    """username -> display_name, for records that are internally consistent."""
    mapping = {}
    for post in posts:
        username = (post.get("username") or "").strip()
        display = (post.get("display_name") or "").strip()
        if username and display:
            mapping.setdefault(username, set()).add(display)
    return mapping


def restorable(backup_post, display_map):
    """A backup record is trustworthy when its author fields agree.

    The legacy bug rewrote username but never display_name, so a username that
    carries several different display names across the file is a poisoned one.
    """
    username = (backup_post.get("username") or "").strip()
    if not username:
        return False, "backup 에도 username 없음"
    if len(display_map.get(username, set())) > 1:
        return False, f"username '{username}' 이 display_name 여러 개를 가짐 (오염 흔적)"
    if not (backup_post.get("full_text") or "").strip():
        return False, "backup 에 본문 없음"
    return True, ""


def restore_file(path, backup_path, apply_changes):
    data = load_json(path)
    posts = data.get("posts", [])
    backup_posts = load_json(backup_path).get("posts", [])
    backup_index = index_by_id(backup_posts)
    display_map = build_display_name_map(backup_posts)

    restored = []
    skipped = []
    for post in posts:
        if (post.get("username") or "").strip() or (post.get("full_text") or "").strip():
            continue
        pid = str(post.get("platform_id") or post.get("id") or "")
        backup_post = backup_index.get(pid)
        if not backup_post:
            skipped.append((pid, "backup 에 해당 id 없음"))
            continue

        ok, reason = restorable(backup_post, display_map)
        if not ok:
            skipped.append((pid, reason))
            continue

        post["username"] = backup_post["username"]
        post["full_text"] = backup_post["full_text"]
        post["url"] = f"https://x.com/{backup_post['username']}/status/{pid}"
        post["is_detail_collected"] = True
        created_at = str(post.get("created_at") or backup_post.get("created_at") or "")
        if created_at:
            post["date"] = created_at[:10]
        restored.append((pid, backup_post["username"]))

    if apply_changes and restored:
        data["posts"] = posts
        save_json(path, data)

    return {"path": path, "restored": restored, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="Restore reset-but-uncollected X records.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] 재수집 실패 레코드 복원")

    for pattern in PATTERNS:
        path = latest_file(args.output_dir, pattern)
        if not path:
            continue
        backup_path = os.path.join(args.backup_dir, os.path.basename(path))
        if not os.path.exists(backup_path):
            print(f"   ⚠️ 백업 없음: {backup_path}")
            continue

        result = restore_file(path, backup_path, args.apply)
        print(f"\n   파일: {os.path.basename(path)}")
        print(f"   복원 {len(result['restored'])}건 / 건너뜀 {len(result['skipped'])}건")
        for pid, username in result["restored"]:
            print(f"      ✅ {pid} → @{username}")
        for pid, reason in result["skipped"]:
            print(f"      ⏭️ {pid}: {reason}")

    if not args.apply:
        print("\n   dry-run 이므로 파일을 쓰지 않았습니다. --apply 로 반영하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
