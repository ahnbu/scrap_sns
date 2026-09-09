"""내 LinkedIn 글의 식별자를 activity URN → Buffer URN 으로 이관한다 (1회성).

계획: _docs/20260909_02_내글수집기-Buffer전환대응과-Threads댓글수-부풀림-수행계획.md (T3, §2.1)

왜 필요한가
-----------
2026-09-05 에 수집기가 Buffer API 로 바뀌면서 같은 글의 식별자가 통째로 달라졌다.

    옛 경로: urn:li:activity:7501590948603420672
    Buffer : urn:li:share:7501590947680591872

같은 글인데 번호가 다르다(activity URN 과 share/ugcPost URN 은 서로 다른 체계이고
산술 변환이 불가능하다). 실측 결과 기존 37건과 신규 37건의 **겹침이 0** 이다.

이관하지 않고 수집만 복구하면 `my_posts_scrap.merge_own_post()` 가 둘을 다른 글로
보아 37 + 37 = **74건**이 된다. 회귀 가드(`check_regression`)는 감소만 막고 증가는
막지 않으므로 조용히 통과하고, 뷰어에 내 글이 전부 중복 표시된다.

조인 키
-------
게시 시각(분 단위). 실측 37/37 매칭이고 기존 파일 안에 중복되는 분이 없다.
본문 대조는 쓸 수 없다 - 옛 DOM 카드 본문이 잘려 있어 60자 접두사 일치가 4/37 뿐이다.

안전장치
--------
- 원본 파일을 지우지 않는다. `--out` 으로 **새 파일**에 쓰고, 기본값은 오늘 날짜 파일이다.
- 매칭이 하나라도 빠지면 저장하지 않고 종료코드 1 로 끝낸다.
- `--dry-run` 이 기본 동작이다. 실제로 쓰려면 `--apply` 를 준다.
- 사용자 상태(별표·숨김·메모)는 `post_key` 기준이라 영향을 받는다. 실측 결과
  `web_viewer/sns_user_metadata.json` 20건 중 내 글 관련이 0건이라 유실이 없다.
  그래도 실행 시 다시 세어 0이 아니면 경고한다.

사용
----
    python scripts/migrate_own_linkedin_ids.py             # dry-run
    python scripts/migrate_own_linkedin_ids.py --apply
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.common import load_json, save_json  # noqa: E402

INSIGHT_SRC = os.path.join(r"D:\vibe-coding\sns_insight_update", "src")
OWN_DIR = os.path.join(REPO_ROOT, "output_linkedin_own", "python")
USER_META = os.path.join(REPO_ROOT, "web_viewer", "sns_user_metadata.json")

#: 조인 허용 오차. 옛 경로는 activity id 에서 게시일을 역산했고 Buffer 는 `sentAt` 을
#: 준다. 실측 최대 차이가 1초라 분 단위로 자르면 전건 맞는다.
JOIN_FORMAT = "%Y-%m-%d %H:%M"


def _force_utf8_console() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def latest_own_file() -> str | None:
    if not os.path.isdir(OWN_DIR):
        return None
    names = sorted(
        n for n in os.listdir(OWN_DIR)
        if n.startswith("linkedin_own_full_") and n.endswith(".json")
    )
    return os.path.join(OWN_DIR, names[-1]) if names else None


def join_key(value) -> str | None:
    """어떤 시각 표기든 '분 단위' 문자열로 바꾼다. 실패하면 None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.strftime(JOIN_FORMAT)


def fetch_buffer_records() -> list[dict]:
    """Buffer 수집기에서 내 LinkedIn 글을 받는다."""
    if not os.path.isdir(INSIGHT_SRC):
        raise SystemExit(f"❌ 수집기 경로를 찾을 수 없습니다: {INSIGHT_SRC}")
    if INSIGHT_SRC not in sys.path:
        sys.path.insert(0, INSIGHT_SRC)
    from sns_insight_update.collectors.buffer_cli import collect_linkedin_posts  # noqa: E402

    return [record.to_dict() for record in collect_linkedin_posts(limit=None)]


def build_mapping(old_posts: list[dict], new_records: list[dict]) -> tuple[dict, list, list]:
    """분 단위 시각으로 옛 글 ↔ 새 레코드를 잇는다.

    돌려주는 것: (platform_id -> 새 레코드, 짝을 못 찾은 옛 글, 중복 키)
    """
    buckets: dict[str, list[dict]] = {}
    for record in new_records:
        key = join_key(record.get("created_at"))
        if key:
            buckets.setdefault(key, []).append(record)

    mapping: dict[str, dict] = {}
    unmatched: list[dict] = []
    ambiguous: list[str] = []
    for post in old_posts:
        key = join_key(post.get("created_at"))
        candidates = buckets.get(key or "", [])
        if len(candidates) > 1:
            ambiguous.append(str(key))
        elif len(candidates) == 0:
            unmatched.append(post)
        else:
            mapping[str(post.get("platform_id"))] = candidates[0]
    return mapping, unmatched, ambiguous


def count_user_metadata_hits(old_posts: list[dict]) -> int:
    """이관 대상 글에 붙은 사용자 상태(별표·숨김·메모) 건수."""
    data = load_json(USER_META, default=None) or {}
    entries = data.get("posts", data) if isinstance(data, dict) else {}
    if not isinstance(entries, dict):
        return 0
    ids = {str(p.get("platform_id")) for p in old_posts}
    return sum(1 for key in entries if any(pid and pid in str(key) for pid in ids))


def migrate(old_posts: list[dict], mapping: dict) -> list[dict]:
    """식별자 3종(`platform_id`·`code`·`url`)만 바꾼다. 지표·본문은 손대지 않는다."""
    out = []
    for post in old_posts:
        migrated = dict(post)
        record = mapping.get(str(post.get("platform_id")))
        if record:
            new_id = str(record.get("platform_post_id") or "")
            new_url = str(record.get("url") or "")
            if new_id:
                migrated["platform_id"] = new_id
                migrated["code"] = new_id
            if new_url:
                migrated["url"] = new_url
        out.append(migrated)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="내 LinkedIn 글 식별자 이관 (1회성)")
    parser.add_argument("--source", default=None, help="이관할 원본 파일. 기본값은 가장 최근 파일")
    parser.add_argument("--out", default=None, help="저장 경로. 기본값은 오늘 날짜 파일")
    parser.add_argument("--apply", action="store_true", help="실제로 저장한다(기본은 dry-run)")
    args = parser.parse_args(argv)

    source = args.source or latest_own_file()
    if not source or not os.path.exists(source):
        print("❌ 이관할 원본 파일이 없습니다.", flush=True)
        return 1

    data = load_json(source, default=None) or {}
    old_posts = data.get("posts", []) if isinstance(data, dict) else (data or [])
    print(f"📂 원본: {os.path.basename(source)} ({len(old_posts)}건)", flush=True)

    new_records = fetch_buffer_records()
    print(f"📥 Buffer 수집: {len(new_records)}건", flush=True)

    mapping, unmatched, ambiguous = build_mapping(old_posts, new_records)
    print(f"🔗 매칭: {len(mapping)}/{len(old_posts)}건", flush=True)

    if ambiguous:
        print(f"❌ 같은 분에 글이 둘 이상입니다({len(ambiguous)}건): {ambiguous[:5]}", flush=True)
        return 1
    if unmatched:
        print(f"❌ 짝을 못 찾은 글 {len(unmatched)}건:", flush=True)
        for post in unmatched[:5]:
            print(f"   - {post.get('platform_id')} {post.get('created_at')}", flush=True)
        print("   시각 조인이 깨졌습니다. 저장하지 않고 멈춥니다.", flush=True)
        return 1

    hits = count_user_metadata_hits(old_posts)
    if hits:
        print(f"⚠️ 사용자 상태(별표·숨김·메모)가 {hits}건 붙어 있습니다. 이관 후 끊깁니다.", flush=True)
    else:
        print("✅ 사용자 상태 영향 0건", flush=True)

    migrated = migrate(old_posts, mapping)
    changed = sum(
        1 for before, after in zip(old_posts, migrated)
        if before.get("platform_id") != after.get("platform_id")
    )
    print(f"🔄 식별자 변경: {changed}건", flush=True)
    for before, after in list(zip(old_posts, migrated))[:3]:
        print(f"   {before.get('platform_id')} → {after.get('platform_id')}", flush=True)

    target = args.out or os.path.join(
        OWN_DIR, f"linkedin_own_full_{datetime.now().strftime('%Y%m%d')}.json"
    )
    if not args.apply:
        print(f"🧪 dry-run 입니다. 저장하지 않았습니다. 대상: {os.path.basename(target)}", flush=True)
        print("   실제로 쓰려면 --apply 를 붙이세요.", flush=True)
        return 0

    metadata = dict(data.get("metadata") or {}) if isinstance(data, dict) else {}
    metadata.update({
        "updated_at": datetime.now().isoformat(),
        "total_count": len(migrated),
        "source": "sns_insight_update/collectors/buffer_cli",
        "migrated_from": os.path.basename(source),
        "migration": "activity_urn_to_buffer_urn (_docs/20260909_02 T3)",
    })
    save_json(target, {"metadata": metadata, "posts": migrated})
    print(f"💾 저장 완료: {os.path.basename(target)} ({len(migrated)}건)", flush=True)
    print(f"   원본 {os.path.basename(source)} 은 그대로 남아 있습니다.", flush=True)
    return 0


if __name__ == "__main__":
    _force_utf8_console()
    raise SystemExit(main())
