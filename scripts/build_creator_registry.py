"""제작자 레지스트리 생성기 → `web_viewer/sns_creators.json`.

입력 셋 (계획 W4 T4-a)
---------------------
  1. 볼트 제작자 프로필 `_제작자별_상세/*.md` — 채널 주소가 가장 정확한 연결 재료다.
     파싱은 `sync_benchmark_accounts.parse_creator_profiles()` 를 그대로 쓴다.
  2. 벤치마킹 계정 `web_viewer/benchmark_accounts.json` — **읽기만** 한다. 채널 핸들이
     같으면 같은 사람으로 보고 `match_keys` 를 합친다(이승필 링크드인 불투명 ID 등).
  3. 확정 연결 `web_viewer/sns_creator_links.json` — 여기서는 통계에만 쓴다. 연결은
     서버가 적재 때 합치므로(utils.creator_registry.apply_links) 레지스트리에 굽지 않는다.

키 규칙
-------
  threads·x : URL → 소문자 핸들
  youtube   : `@handle` → `verify_youtube_handle()` 로 채널 ID(UC...). 키는 ~/.env.
              한 번 확인한 값은 보존한다 - 병행 세션에서 확인한 키가 다음 동기화에
              사라진 결함이 있었다(sync_benchmark_accounts._preserve_verified_youtube_keys).
  linkedin  : slug 는 수집 데이터의 불투명 ID 와 접점이 없어 **자동 연결하지 않는다**.
              벤치마킹 계정과 slug 가 같을 때 그 계정의 불투명 ID 를 물려받을 뿐이다.

사용법
------
    python scripts/build_creator_registry.py            # 유튜브 확인 포함, 저장
    python scripts/build_creator_registry.py --offline  # 외부 조회 없이(이전 확인값만)
    python scripts/build_creator_registry.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from sync_benchmark_accounts import (  # noqa: E402
    CREATOR_DIR,
    atomic_write_json,
    latest_total_file,
    load_env,
    load_json,
    parse_creator_profiles,
    verify_youtube_handle,
)
from utils.benchmark_match import normalize_key  # noqa: E402
from utils.creator_registry import (  # noqa: E402
    apply_links,
    build_creator_match_index,
    handle_from_channel,
    load_links,
    load_registry,
    match_creator_id,
    now_kst_iso,
)
from utils.library_index import split_frontmatter  # noqa: E402

OUTPUT_PATH = os.environ.get("SNS_CREATORS_PATH", "").strip() or os.path.join(
    REPO_ROOT, "web_viewer", "sns_creators.json"
)
LINKS_PATH = os.environ.get("SNS_CREATOR_LINKS_PATH", "").strip() or os.path.join(
    REPO_ROOT, "web_viewer", "sns_creator_links.json"
)
BENCHMARK_PATH = os.path.join(REPO_ROOT, "web_viewer", "benchmark_accounts.json")
SNS_PLATFORMS = ("threads", "linkedin", "x", "twitter", "youtube")


def _profile_stems() -> list[str]:
    if not os.path.isdir(CREATOR_DIR):
        return []
    return sorted(os.path.splitext(n)[0] for n in os.listdir(CREATOR_DIR) if n.endswith(".md"))


def _profile_title(stem: str) -> str:
    path = os.path.join(CREATOR_DIR, f"{stem}.md")
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            front, _ = split_frontmatter(handle.read(8000))
    except OSError:
        return stem
    title = front.get("title")
    return str(title).strip() if isinstance(title, str) and title.strip() else stem


def build_creators(verify: bool, api_key: str) -> tuple[list[dict], dict]:
    previous = {c["id"]: c for c in load_registry(OUTPUT_PATH)}
    parsed = parse_creator_profiles()
    report = {"youtube_api_calls": 0, "youtube_verified": 0, "youtube_unverified": [], "benchmark_merged": []}
    creators = []

    for stem in _profile_stems():
        entry = parsed.get(stem) or {}
        channels = {}
        for platform, value in (entry.get("channels") or {}).items():
            key = handle_from_channel(platform, value)
            if key:
                channels[platform] = key
        match_keys: dict[str, list[str]] = {}
        for platform in ("threads", "x"):
            if channels.get(platform):
                match_keys[platform] = [channels[platform]]

        youtube_verified = dict((previous.get(stem) or {}).get("youtube_verified") or {})
        unverified = []
        handle = channels.get("youtube")
        if handle:
            channel_id = youtube_verified.get(handle.lower(), "")
            if not channel_id and verify and api_key:
                report["youtube_api_calls"] += 1
                ok, channel_id, _title = verify_youtube_handle(handle, api_key)
                time.sleep(0.1)
                channel_id = channel_id if ok else ""
            if channel_id:
                youtube_verified = {handle.lower(): channel_id}
                match_keys["youtube"] = [channel_id]
                report["youtube_verified"] += 1
            else:
                unverified.append("youtube")
                report["youtube_unverified"].append(stem)

        creators.append(
            {
                "id": stem,
                "name": _profile_title(stem),
                "aliases": list(entry.get("aliases") or []),
                "status": "active",
                "profile": True,
                "channels": channels,
                "match_keys": match_keys,
                "youtube_verified": youtube_verified,
                "benchmark_account": None,
                "unverified": unverified,
                "sources": ["vault_profile"],
            }
        )

    # 벤치마킹 계정 — 채널 핸들이 같으면 같은 사람. 이름으로는 잇지 않는다.
    accounts = (load_json(BENCHMARK_PATH, {}) or {}).get("accounts") or []
    for account in accounts:
        if not isinstance(account, dict) or account.get("status") == "excluded":
            continue
        account_handles = {
            platform: handle_from_channel(platform, value)
            for platform, value in (account.get("channels") or {}).items()
        }
        for creator in creators:
            same = [
                platform
                for platform, key in creator["channels"].items()
                if key and account_handles.get(platform)
                and normalize_key(key) == normalize_key(account_handles[platform])
            ]
            if not same:
                continue
            if creator["benchmark_account"] is None:
                creator["benchmark_account"] = account["id"]
            for platform, keys in (account.get("match_keys") or {}).items():
                bucket = creator["match_keys"].setdefault(platform, [])
                for key in keys or []:
                    if key and key not in bucket:
                        bucket.append(key)
            creator["sources"].append(f"benchmark:{account['id']}")
            report["benchmark_merged"].append(f"{creator['id']}←{account['id']}({','.join(same)})")
            break

    for creator in creators:
        creator["match_keys"] = {p: sorted(set(k)) for p, k in creator["match_keys"].items() if k}
    return creators, report


def multi_platform_stats(creators: list[dict]) -> dict:
    """제작자별로 통합본에서 매칭되는 SNS 플랫폼 수. 「여러 계정이 한 사람으로 합쳐진 인원」."""
    path = latest_total_file()
    posts = ((load_json(path, {}) or {}).get("posts") or []) if path else []
    index = build_creator_match_index(creators)
    platforms: dict[str, set] = defaultdict(set)
    matched_posts = 0
    for post in posts:
        creator_id = match_creator_id(post, index)
        if creator_id:
            matched_posts += 1
            platform = str(post.get("sns_platform") or "").lower()
            platforms[creator_id].add("x" if platform == "twitter" else platform)
    return {
        "matched_posts": matched_posts,
        "creators_with_posts": len(platforms),
        "multi_platform_creators": sorted(cid for cid, found in platforms.items() if len(found) >= 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="제작자 레지스트리 생성")
    parser.add_argument("--offline", action="store_true", help="유튜브 채널 ID 외부 확인을 하지 않는다")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않는다")
    args = parser.parse_args()

    api_key = ""
    if not args.offline:
        load_env()
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            print("[WARN] YOUTUBE_API_KEY 가 없어 유튜브 확인을 건너뛴다(이전 확인값만 쓴다)")

    creators, report = build_creators(verify=not args.offline, api_key=api_key)
    channel_counts = defaultdict(int)
    for creator in creators:
        for platform in creator["channels"]:
            channel_counts[platform] += 1

    base = multi_platform_stats(creators)
    linked = multi_platform_stats(apply_links(creators, load_links(LINKS_PATH)))
    print(f"제작자 {len(creators)}명 · 채널 " + " ".join(f"{p}={n}" for p, n in sorted(channel_counts.items())))
    print(
        f"유튜브 채널 ID 확인 {report['youtube_verified']}명 (이번 조회 {report['youtube_api_calls']}건, "
        f"미확인 {len(report['youtube_unverified'])}명)"
    )
    print(f"벤치마킹 계정 합침 {len(report['benchmark_merged'])}건: {', '.join(report['benchmark_merged'])}")
    print(
        f"통합본 매칭 글 {base['matched_posts']}건 · 글이 있는 제작자 {base['creators_with_posts']}명 · "
        f"여러 플랫폼으로 합쳐진 인원 {len(base['multi_platform_creators'])}명"
    )
    print(f"확정 연결 반영 시 여러 플랫폼 인원 {len(linked['multi_platform_creators'])}명")

    if args.dry_run:
        print("[DRY-RUN] 저장하지 않는다")
        return 0
    atomic_write_json(OUTPUT_PATH, {"generated_at": now_kst_iso(), "creators": creators})
    print(f"저장: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
