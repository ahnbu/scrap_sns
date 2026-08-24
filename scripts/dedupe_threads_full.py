"""Clean up duplicated Threads records left by the pre-fix detail collector.

Before commit ``42171a6`` (2026-06-23) the detail collector swapped a record's
code for the original post's code when a repost URL redirected, which produced
three shapes of duplicate. All of them predate that fix; this script clears the
backlog it never backfilled.

Types handled (detected from the file itself, no code list is passed in):

  1. same ``platform_id`` twice        -> keep the richest record, delete the rest
  2. same ``pk``, different code       -> keep the richest, mark the rest as alias
  3. different ``pk``, same author+body -> two members of one merged chain; keep
                                          the richest, mark the rest as alias

Aliases are marked, never deleted: ``total_scrap.py`` already drops
``detail_status == "duplicate_of_canonical"`` at merge time, and keeping the row
preserves the mapping from the alias code to the canonical one.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os

OUTPUT_DIR = "output_threads/python"
FULL_PATTERN = "threads_py_full_*.json"
SIMPLE_PATTERN = "threads_py_simple_*.json"
ALIAS_STATUS = "duplicate_of_canonical"
TEXT_KEY_LEN = 200


def latest_file(output_dir, pattern):
    files = sorted(glob.glob(os.path.join(output_dir, pattern)), reverse=True)
    return files[0] if files else None


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, data):
    with open(path, "w", encoding="utf-8-sig") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_code(post):
    return post.get("code") or post.get("platform_id")


def richness(post):
    """Sort key that puts the record we want to keep first.

    More media beats longer text beats the earlier post beats a stable code
    ordering, so the choice never depends on file order.
    """
    return (
        -len(post.get("media") or []),
        -len(post.get("full_text") or ""),
        post.get("taken_at") or 0,
        str(get_code(post) or ""),
    )


def pick_canonical(posts):
    return sorted(posts, key=richness)[0]


def find_type1(posts):
    """Same platform_id more than once -> (canonical, [duplicates])."""
    groups = collections.defaultdict(list)
    for post in posts:
        code = get_code(post)
        if code:
            groups[str(code)].append(post)

    result = []
    for code, rows in groups.items():
        if len(rows) < 2:
            continue
        canonical = pick_canonical(rows)
        result.append((canonical, [r for r in rows if r is not canonical]))
    return result


def find_type2(posts):
    """Same pk under different codes -> (canonical, [aliases])."""
    groups = collections.defaultdict(list)
    for post in posts:
        pk = str(post.get("pk") or "")
        if pk:
            groups[pk].append(post)

    result = []
    for pk, rows in groups.items():
        if len(rows) < 2:
            continue
        if len({str(get_code(r)) for r in rows}) < 2:
            continue
        canonical = pick_canonical(rows)
        result.append((canonical, [r for r in rows if r is not canonical]))
    return result


def find_type3(posts, already_handled):
    """Same author and body under different pks -> (canonical, [aliases])."""
    groups = collections.defaultdict(list)
    for post in posts:
        if id(post) in already_handled:
            continue
        username = post.get("username")
        text = (post.get("full_text") or "").strip()[:TEXT_KEY_LEN]
        if username and text:
            groups[(username, text)].append(post)

    result = []
    for _key, rows in groups.items():
        if len(rows) < 2:
            continue
        if len({str(r.get("pk") or "") for r in rows}) < 2:
            continue
        canonical = pick_canonical(rows)
        result.append((canonical, [r for r in rows if r is not canonical]))
    return result


def merge_media_into(canonical, duplicates):
    """Fold the media of records we are about to delete into the survivor.

    The duplicates hold the same post, but not always the same downloaded
    images: one copy can carry a ``local_images`` entry the survivor lacks, and
    deleting it outright orphans that file. Merge both lists before dropping.
    """
    merged_fields = []
    for field in ("media", "local_images"):
        combined = list(canonical.get(field) or [])
        seen = set(combined)
        for duplicate in duplicates:
            for value in duplicate.get(field) or []:
                if value not in seen:
                    combined.append(value)
                    seen.add(value)
        if combined != (canonical.get(field) or []):
            canonical[field] = combined
            merged_fields.append(field)
    return merged_fields


def mark_alias(post, canonical):
    post["detail_status"] = ALIAS_STATUS
    post["duplicate_of"] = get_code(canonical)
    post["canonical_code"] = get_code(canonical)
    if canonical.get("username"):
        post["canonical_username"] = canonical.get("username")


def plan_changes(posts):
    """Return (indices to delete, [(alias post, canonical post)])."""
    delete_ids = set()
    media_merged = 0
    type1 = find_type1(posts)
    for canonical, duplicates in type1:
        if merge_media_into(canonical, duplicates):
            media_merged += 1
        for duplicate in duplicates:
            delete_ids.add(id(duplicate))

    survivors = [p for p in posts if id(p) not in delete_ids]

    aliases = []
    handled = set()
    for canonical, rows in find_type2(survivors):
        for row in rows:
            aliases.append((row, canonical))
            handled.add(id(row))
        handled.add(id(canonical))

    for canonical, rows in find_type3(survivors, handled):
        for row in rows:
            aliases.append((row, canonical))

    return delete_ids, aliases, len(type1), media_merged


def process_full(path, apply_changes):
    data = load_json(path)
    posts = data.get("posts", [])
    delete_ids, aliases, type1_groups, media_merged = plan_changes(posts)

    type2_groups = len({id(canonical) for _alias, canonical in aliases})

    kept = [p for p in posts if id(p) not in delete_ids]
    alias_codes = {}
    for alias, canonical in aliases:
        mark_alias(alias, canonical)
        alias_codes[str(get_code(alias))] = str(get_code(canonical))

    if apply_changes:
        data["posts"] = kept
        data.setdefault("metadata", {})
        data["metadata"]["total_count"] = len(kept)
        save_json(path, data)

    return {
        "path": path,
        "before": len(posts),
        "after": len(kept),
        "type1_groups": type1_groups,
        "deleted": len(delete_ids),
        "alias_groups": type2_groups,
        "alias_marked": len(aliases),
        "alias_codes": alias_codes,
        "media_merged": media_merged,
    }


def process_simple(path, alias_codes, apply_changes):
    data = load_json(path)
    posts = data.get("posts", [])
    marked = 0
    for post in posts:
        code = str(get_code(post) or "")
        canonical = alias_codes.get(code)
        if not canonical or post.get("detail_status") == ALIAS_STATUS:
            continue
        post["detail_status"] = ALIAS_STATUS
        post["duplicate_of"] = canonical
        post["canonical_code"] = canonical
        marked += 1

    if apply_changes and marked:
        data["posts"] = posts
        save_json(path, data)

    return {"path": path, "total": len(posts), "marked": marked}


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Threads full/simple DBs.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    apply_changes = args.apply
    print(f"[{'APPLY' if apply_changes else 'DRY-RUN'}] Threads 중복 정리")

    full_path = latest_file(args.output_dir, FULL_PATTERN)
    if not full_path:
        print("❌ full 파일을 찾을 수 없습니다.")
        return 1

    result = process_full(full_path, apply_changes)
    print(f"\n   파일: {os.path.basename(result['path'])}")
    print(f"   유형1 platform_id 완전중복: {result['type1_groups']}그룹 / 삭제 {result['deleted']}건")
    print(f"   유형2·3 alias 표시: {result['alias_groups']}그룹 / {result['alias_marked']}건")
    print(f"   삭제 전 media·local_images 병합: {result['media_merged']}그룹")
    print(f"   총 건수: {result['before']} → {result['after']}")
    for alias, canonical in sorted(result["alias_codes"].items()):
        print(f"      alias {alias} → canonical {canonical}")

    simple_path = latest_file(args.output_dir, SIMPLE_PATTERN)
    if simple_path:
        simple_result = process_simple(simple_path, result["alias_codes"], apply_changes)
        print(f"\n   파일: {os.path.basename(simple_result['path'])}")
        print(f"   전체 {simple_result['total']}건 / alias 표시 {simple_result['marked']}건")

    if not apply_changes:
        print("\n   dry-run 이므로 파일을 쓰지 않았습니다. --apply 로 반영하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
