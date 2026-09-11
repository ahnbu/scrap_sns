"""이미 붙은 자료 카드(web·file) 자동 태그를 새 범위(제목 + 앞 800자 + 볼트 분류)로 맞춘다.

규칙은 utils/auto_tag.migrate_library_tags() 한 곳에 있다. 이 스크립트는 입출력만 한다.

- 대상: 목록에 보이는 자료(인덱스에서 `library_overlap_of` 가 없는 것) 중 SNS 글과 URL 이
  겹치지 않는 것. 겹침 노트는 원문 SNS 카드와 태그 키를 공유한다.
- 기본은 `--dry-run`(건수만 출력). `--apply` 일 때만 쓴다. 쓰기 전에
  `web_viewer/sns_tags_YYYYMMDD_HHMM.bak.json` 으로 복사하고(local-only, git 제외),
  원자적으로 바꾼다. 멱등이라 다시 돌려도 변경이 0 이면 끝난 것이다.
- SNS 키가 하나라도 바뀌면 쓰지 않고 멈춘다(exit 2).

Usage:
    python scripts/migrate_library_auto_tags.py            # dry-run
    python scripts/migrate_library_auto_tags.py --apply

계획: _docs/20260911_02 (W3 T3-c)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.auto_tag import build_rules, migrate_library_tags  # noqa: E402
from utils.library_index import build_library_posts  # noqa: E402
from utils.post_meta import build_post_key, canonicalize_url  # noqa: E402

KST = timezone(timedelta(hours=9))
VIEWER = os.path.join(ROOT, "web_viewer")
FIXTURE_VAULT = os.path.join(ROOT, "tests", "fixtures", "golden", "library", "vault")


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _latest_total_file():
    files = [
        path for path in glob.glob(os.path.join(ROOT, "output_total", "total_full_*.json"))
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    ]
    if not files:
        raise FileNotFoundError("output_total/total_full_YYYYMMDD.json 이 없다")
    return sorted(files, reverse=True)[0]


def _sns_keys(total_path):
    data = _load(total_path, {})
    posts = data.get("posts", data) if isinstance(data, dict) else data
    keys = set()
    for post in posts or []:
        for value in (canonicalize_url(post), post.get("url")):
            if value:
                keys.add(value)
    return keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 dry-run)")
    args = parser.parse_args()

    tags_path = os.path.join(VIEWER, "sns_tags.json")
    tags = _load(tags_path, {})
    rules = build_rules(_load(os.path.join(VIEWER, "sns_tag_catalog.json"), {}))
    index = _load(os.path.join(VIEWER, "sns_library_index.json"), {}).get("posts") or []
    user_metadata = _load(os.path.join(VIEWER, "sns_user_metadata.json"), {})
    total_path = _latest_total_file()
    sns_keys = _sns_keys(total_path)

    library = {}
    for post in index:
        if post.get("library_overlap_of"):
            continue
        key = canonicalize_url(post)
        if not key or key in sns_keys:
            continue
        entry = user_metadata.get(build_post_key(post)) if isinstance(user_metadata, dict) else None
        note = str(entry.get("note") or "").strip() if isinstance(entry, dict) else ""
        library[key] = {**post, "_user_note": note}

    # 검증 표본 볼트 노트의 원문 URL. 검증 전용 서버가 운영 태그 파일에 남긴 키다(계획 F11).
    # 실제 SNS 글·자료와 겹치는 것은 빼고 넘긴다.
    fixture_keys = set()
    for post in build_library_posts(FIXTURE_VAULT):
        url = canonicalize_url(post)
        if url.startswith(("http://", "https://")):
            fixture_keys.add(url)
            fixture_keys.add(re.sub(r"^https?://(?:www\.)?threads\.net/", "https://www.threads.com/", url))
    junk_keys = fixture_keys - sns_keys - set(library)

    result, summary = migrate_library_tags(tags, library, rules, junk_keys=junk_keys)
    sns_changed = [key for key in tags if key not in library and result.get(key) != tags.get(key)
                   and "sns-library-verify-" not in key and key not in junk_keys]
    summary.update({
        "mode": "apply" if args.apply else "dry-run",
        "total_file": os.path.basename(total_path),
        "rule_count": len(rules),
        "sns_changed_keys": len(sns_changed),
    })

    if sns_changed:
        summary["error"] = "SNS 키가 바뀐다 - 쓰지 않는다"
        print(json.dumps(summary, ensure_ascii=False))
        return 2

    if args.apply and (summary["changed_keys"] or summary["junk_keys"]):
        stamp = datetime.now(KST).strftime("%Y%m%d_%H%M")
        backup = os.path.join(VIEWER, f"sns_tags_{stamp}.bak.json")
        shutil.copyfile(tags_path, backup)
        tmp_path = f"{tags_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=4, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, tags_path)
        summary["backup"] = os.path.relpath(backup, ROOT).replace("\\", "/")

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
