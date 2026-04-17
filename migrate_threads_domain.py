from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
TAGS_PATH = PROJECT_ROOT / "web_viewer" / "sns_tags.json"


def normalize_threads_url(value: str) -> str:
    if not isinstance(value, str):
        return value
    return (
        value.replace("https://www.threads.net/", "https://www.threads.com/")
        .replace("http://www.threads.net/", "https://www.threads.com/")
        .replace("https://threads.net/", "https://www.threads.com/")
        .replace("http://threads.net/", "https://www.threads.com/")
        .replace("https://threads.com/", "https://www.threads.com/")
        .replace("http://threads.com/", "https://www.threads.com/")
    )


def extract_code_from_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        return ""
    for marker in ("/post/", "/t/"):
        if marker in key:
            return key.split(marker, 1)[1].split("/", 1)[0]
    if "://" not in key:
        return key
    return ""


def canonicalize_legacy_key(key: str, canonical_by_code: dict[str, str]) -> str:
    if not isinstance(key, str) or not key:
        return key

    normalized = normalize_threads_url(key)
    code = extract_code_from_key(key)
    if code and code in canonical_by_code:
        return canonical_by_code[code]
    return normalized


def rewrite_threads_urls_in_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_threads_url(value)
    if isinstance(value, list):
        return [rewrite_threads_urls_in_value(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_threads_urls_in_value(item) for key, item in value.items()}
    return value


def migrate_url_key_dict(data: dict[str, list[str]], canonical_by_code: dict[str, str]) -> dict[str, list[str]]:
    migrated: dict[str, list[str]] = {}
    for key, value in data.items():
        if key == "undefined":
            continue

        target = canonicalize_legacy_key(key, canonical_by_code)
        if target not in migrated:
            migrated[target] = []
            for tag in data.get(target, []):
                if tag and str(tag).strip() and tag not in migrated[target]:
                    migrated[target].append(tag)

        existing = migrated.get(target, [])
        merged = []
        seen = set()
        for tag in [*existing, *(value or [])]:
            if not tag or not str(tag).strip():
                continue
            if tag in seen:
                continue
            merged.append(tag)
            seen.add(tag)
        migrated[target] = merged

    return migrated


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def try_load_json(path: Path) -> Any | None:
    try:
        return load_json(path)
    except json.JSONDecodeError:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")


def latest_total_file() -> Path:
    files = sorted(
        path
        for path in PROJECT_ROOT.glob("output_total/total_full_*.json")
        if re.fullmatch(r"total_full_\d{8}", path.stem)
    )
    if not files:
        raise FileNotFoundError("output_total/total_full_*.json not found")
    return files[-1]


def build_canonical_by_code(posts: list[dict[str, Any]]) -> dict[str, str]:
    canonical_by_code: dict[str, str] = {}
    for post in posts:
        platform = str(post.get("sns_platform", "")).lower()
        if "thread" not in platform:
            continue
        code = str(post.get("platform_id") or post.get("code") or "").strip()
        username = str(post.get("username") or post.get("user") or "").strip()
        url = normalize_threads_url(str(post.get("url") or post.get("post_url") or ""))
        if not code:
            continue
        if username:
            canonical_by_code[code] = f"https://www.threads.com/@{username}/post/{code}"
        elif url:
            canonical_by_code[code] = url
    return canonical_by_code


def collect_json_files() -> list[Path]:
    files = []
    files.extend(
        sorted(
            path
            for path in PROJECT_ROOT.glob("output_total/total_full_*.json")
            if re.fullmatch(r"total_full_\d{8}", path.stem)
        )
    )
    files.extend(
        sorted(
            path
            for path in (PROJECT_ROOT / "output_threads" / "python").glob("**/*.json")
            if ".bak" not in path.name
        )
    )
    return files


def create_backup(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.{timestamp}.bak")
    backup.write_bytes(path.read_bytes())
    return backup


def count_tag_legacy_keys(tags: dict[str, Any], canonical_by_code: dict[str, str]) -> int:
    pending = 0
    for key in tags:
        if key == "undefined":
            pending += 1
            continue
        if canonicalize_legacy_key(key, canonical_by_code) != key:
            pending += 1
    return pending


def count_unresolved_code_collisions(tags: dict[str, Any], canonical_by_code: dict[str, str]) -> int:
    usernames_by_code: dict[str, set[str]] = defaultdict(set)
    for key in tags:
        code = extract_code_from_key(key)
        if not code:
            continue
        if "/post/" not in key:
            continue
        try:
            username = key.split("@", 1)[1].split("/post/", 1)[0]
        except IndexError:
            continue
        usernames_by_code[code].add(username)

    return sum(
        1 for code, usernames in usernames_by_code.items() if len(usernames) > 1 and code not in canonical_by_code
    )


def scan_file_rewrites(paths: list[Path]) -> int:
    pending = 0
    for path in paths:
        original = try_load_json(path)
        if original is None:
            continue
        rewritten = rewrite_threads_urls_in_value(copy.deepcopy(original))
        if rewritten != original:
            pending += 1
    return pending


def apply_file_rewrites(paths: list[Path]) -> int:
    changed = 0
    for path in paths:
        original = try_load_json(path)
        if original is None:
            continue
        rewritten = rewrite_threads_urls_in_value(copy.deepcopy(original))
        if rewritten == original:
            continue
        create_backup(path)
        write_json(path, rewritten)
        changed += 1
    return changed


def apply_tag_rewrite(canonical_by_code: dict[str, str]) -> tuple[int, int]:
    if not TAGS_PATH.exists():
        return 0, 0

    original = load_json(TAGS_PATH)
    migrated = migrate_url_key_dict(original, canonical_by_code)
    pending = count_tag_legacy_keys(original, canonical_by_code)
    if migrated != original:
        create_backup(TAGS_PATH)
        write_json(TAGS_PATH, migrated)
        return pending, 1
    return pending, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Threads URLs from .net to .com")
    parser.add_argument("--apply", action="store_true", help="apply file rewrites")
    parser.add_argument("--dry-run", action="store_true", help="show pending changes")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("choose --dry-run or --apply")

    latest = latest_total_file()
    latest_data = load_json(latest)
    posts = latest_data if isinstance(latest_data, list) else latest_data.get("posts", [])
    canonical_by_code = build_canonical_by_code(posts)
    json_files = collect_json_files()
    tags = load_json(TAGS_PATH) if TAGS_PATH.exists() else {}

    pending_files = scan_file_rewrites(json_files)
    pending_tags = count_tag_legacy_keys(tags, canonical_by_code) if isinstance(tags, dict) else 0
    unresolved_collisions = count_unresolved_code_collisions(tags, canonical_by_code) if isinstance(tags, dict) else 0

    print(f"latest file: {latest}")
    print(f"file rewrite pending: {pending_files}")
    print(f"tag legacy key pending: {pending_tags}")
    print(f"unresolved code collision: {unresolved_collisions}")

    if args.dry_run and not args.apply:
        return

    changed_files = apply_file_rewrites(json_files)
    changed_tag_keys, changed_tag_files = apply_tag_rewrite(canonical_by_code)

    print(f"applied file rewrites: {changed_files}")
    print(f"applied tag key rewrites: {changed_tag_keys}")
    print(f"tag files updated: {changed_tag_files}")


if __name__ == "__main__":
    main()
