"""벤치마킹 후보 풀을 코드로 채운다. 내가 켠 설정은 보존한다.

계정 관리는 두 층이다(SPEC D10).

    후보 풀   = 세 소스를 합쳐 코드가 채운다
    수집 대상 = 그중 화면에서 켠 것 (status == "active")

소스 3개
--------
  주  `output_total/total_full_*.json` 저자 집계 — 실제 계정 주소, 내가 몇 건
      저장했나, 최신 저장일이 자동으로 붙는다. 후보 판정의 1차 신호다
  보조 `scripts/data/benchmark_seed.json` — SPEC D8 이 확정한 25계정 명단
  보조 `_제작자별_상세` 프론트매터 — 멀티채널 주소

동기화 규칙 — 덮어쓰지 않는다
-----------------------------
  - 다시 돌려도 `status` · `limit` · `memo` · `purpose` 는 **보존**
  - `status: excluded` 인 계정은 **다시 올리지 않는다**
    (없으면 뺀 계정이 소스에 남아 있는 한 매번 되살아난다 — themodellers)
  - 소스에서 사라진 계정도 목록에서 지우지 않는다
    (이미 수집한 글이 가리킬 계정을 잃는다)

주소 유효성 (SPEC D10)
----------------------
형태는 구분하지 않되, 유효성은 넣기 전에 확인한다. 확인에 실패하면 그 칸을
비우고 「주소 미확인」으로 두어 켤 수 없게 한다. `--verify` 없이 돌리면 확인을
건너뛰고 소스 값을 그대로 쓴다(오프라인 재실행용).

매칭 키 (SPEC D12)
------------------
계정 주소와 별개로 `match_keys` 를 적재한다. 게시물의 저장된 값과 직접 비교할
유일한 키다.
  - youtube : channel_id(UC...) — username 이 채널 표시명이라 @handle 과 안 이어진다
  - threads/x : username
  - linkedin : 저장글의 불투명 ID(ACoAA...) — vanity slug 와 다른 값이다

사용법
------
    python scripts/sync_benchmark_accounts.py --dry-run
    python scripts/sync_benchmark_accounts.py --verify
    python scripts/sync_benchmark_accounts.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

SEED_PATH = os.path.join(REPO_ROOT, "scripts", "data", "benchmark_seed.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "web_viewer", "benchmark_accounts.json")
CREATOR_DIR = os.path.join(
    os.path.expanduser("~"), "cowork", "90_자료수집", "_제작자별_상세"
)

# 사용자가 화면에서 바꾸는 값. 동기화가 절대 덮지 않는다.
USER_OWNED_FIELDS = ("status", "limit", "memo", "purpose")
DEFAULT_LIMIT = 5

PLATFORM_KEYS = ("youtube", "threads", "linkedin", "x")
# 지금 계정 단위 수집이 되는 플랫폼. 화면의 「수집 가능」 배지가 이 값을 쓴다.
COLLECTABLE_PLATFORMS = {"youtube", "linkedin"}


# --------------------------------------------------------------- 공통 유틸

def load_env() -> None:
    env_path = os.path.join(os.path.expanduser("~"), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def load_json(path: str, fallback=None):
    if not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4, sort_keys=True)
    os.replace(tmp_path, path)


def strip_at(value: str) -> str:
    return str(value or "").lstrip("@").strip()


def latest_total_file() -> str | None:
    pattern = os.path.join(REPO_ROOT, "output_total", "total_full_*.json")
    files = sorted(
        path for path in glob.glob(pattern)
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    )
    return files[-1] if files else None


# ----------------------------------------------------- 소스 1: 수집 데이터

def collect_author_stats() -> dict:
    """{(platform, username_lower): {...}} 저자별 저장 건수·최신 저장일·채널ID."""
    path = latest_total_file()
    if not path:
        return {}
    data = load_json(path, {}) or {}
    posts = data.get("posts", []) if isinstance(data, dict) else data

    def new_entry() -> dict:
        return {
            "saved_count": 0,
            "last_saved_at": "",
            "display_names": set(),
            "channel_ids": set(),
            "usernames": set(),
        }

    stats: dict[tuple[str, str], dict] = defaultdict(new_entry)
    for post in posts:
        platform = str(post.get("sns_platform") or "").lower()
        username = str(post.get("username") or "").strip()
        if not platform or not username:
            continue
        key = (platform, username.lower())
        entry = stats[key]
        entry["saved_count"] += 1
        date = str(post.get("date") or post.get("created_at") or "")[:10]
        if date > entry["last_saved_at"]:
            entry["last_saved_at"] = date
        entry["display_names"].add(str(post.get("display_name") or username))
        entry["usernames"].add(username)
        channel_id = str(post.get("channel_id") or "").strip()
        if channel_id:
            entry["channel_ids"].add(channel_id)
    return stats


def find_author(stats: dict, platform: str, needles: list[str]) -> dict | None:
    """이름·핸들 조각으로 저자를 찾는다.

    이건 **후보 풀을 채울 때의 탐색**이지 게시물 매칭이 아니다. 매칭은
    여기서 찾아낸 match_keys 로만 한다(SPEC D12) - 이름 문자열 매칭을
    런타임 판정에 쓰지 않는다.
    """
    needles = [n.lower() for n in needles if n]
    if not needles:
        return None
    for (plat, username_lower), entry in stats.items():
        if plat != platform:
            continue
        haystack = " ".join(
            [username_lower] + [name.lower() for name in entry["display_names"]]
        )
        if any(needle in haystack for needle in needles):
            return entry
    return None


# ------------------------------------------------ 소스 2: 제작자 프로필 파일

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def parse_creator_profiles() -> dict:
    """{정규화 이름: {platform: 주소}}. 프론트매터의 youtube/threads/linkedin/x."""
    profiles: dict = {}
    if not os.path.isdir(CREATOR_DIR):
        return profiles
    for name in os.listdir(CREATOR_DIR):
        if not name.endswith(".md"):
            continue
        path = os.path.join(CREATOR_DIR, name)
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                text = handle.read(6000)
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        front = text.split("---", 2)[1] if text.count("---") >= 2 else ""
        channels = {}
        for platform in PLATFORM_KEYS:
            match = re.search(rf"^{platform}:\s*(.+)$", front, re.MULTILINE)
            if not match:
                continue
            raw = match.group(1).strip().strip('"').strip("'")
            link = LINK_RE.search(raw)
            channels[platform] = link.group(2) if link else raw
        if channels:
            profiles[os.path.splitext(name)[0]] = channels
    return profiles


def profile_channels_for(profiles: dict, name: str) -> dict:
    needle = name.lower()
    for key, channels in profiles.items():
        if needle and needle in key.lower():
            return channels
    return {}


# ------------------------------------------------------------ 주소 유효성

def verify_youtube_handle(handle: str, api_key: str) -> tuple[bool, str, str]:
    """(유효한가, channel_id, 채널명)."""
    normalized = handle if handle.startswith("@") else f"@{handle}"
    params = urllib.parse.urlencode(
        {"part": "snippet", "forHandle": normalized, "key": api_key}
    )
    url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001
        print(f"      [WARN] {normalized} 조회 실패: {error}")
        return False, "", ""
    items = payload.get("items") or []
    if not items:
        return False, "", ""
    item = items[0]
    return True, str(item.get("id") or ""), str((item.get("snippet") or {}).get("title") or "")


def verify_url_opens(url: str) -> bool:
    """페이지가 열리는지만 본다. 로그인 벽은 여기서 판정하지 않는다."""
    request_obj = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; scrap_sns/1.0)"},
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=15) as response:
            return 200 <= response.status < 400
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ 본체

def build_account(seed: dict, stats: dict, profiles: dict, verify: bool, api_key: str) -> dict:
    name = seed["name"]
    # 저장글의 표시명이 한글 이름과 다른 사람이 있다 - LinkedIn 은 영문 표기가
    # 흔하다(빌더 조쉬 → "Josh Kim"). 별칭이 없으면 그 사람의 저장글을 못 찾아
    # match_keys 가 비고, 결국 R5·R8 이 그 플랫폼에서 성립하지 않는다.
    aliases = [name] + list(seed.get("aliases") or [])
    channels = dict(seed.get("channels") or {})

    # 제작자 파일에 있는 주소로 빈 칸을 메운다(소스에 있는 것을 덮지 않는다).
    for platform, value in profile_channels_for(profiles, name).items():
        if platform in PLATFORM_KEYS and not channels.get(platform):
            tail = str(value).rstrip("/").split("/")[-1]
            if tail:
                channels[platform] = tail

    match_keys: dict[str, list[str]] = {}
    unverified: list[str] = []
    stats_hit = {"saved_count": 0, "last_saved_at": ""}

    for platform in PLATFORM_KEYS:
        handle = str(channels.get(platform) or "").strip()
        if not handle:
            continue

        if platform == "youtube":
            entry = find_author(stats, "youtube", aliases + [strip_at(handle)])
            if entry:
                stats_hit = _merge_stats(stats_hit, entry)
                # 저장글에서 나온 channel_id 가 가장 확실한 매칭 키다.
                match_keys.setdefault("youtube", []).extend(sorted(entry["channel_ids"]))
            if verify and api_key:
                ok, channel_id, title = verify_youtube_handle(handle, api_key)
                if not ok:
                    print(f"      [MISS] {name} youtube {handle} — 주소 미확인, 칸을 비운다")
                    channels.pop("youtube", None)
                    unverified.append("youtube")
                    continue
                if channel_id:
                    match_keys.setdefault("youtube", []).append(channel_id)
                print(f"      [OK]   {name} youtube {handle} → {title}")
                time.sleep(0.1)

        elif platform in ("threads", "x"):
            username = strip_at(handle)
            entry = find_author(stats, platform, [username] + aliases)
            if entry:
                stats_hit = _merge_stats(stats_hit, entry)
                match_keys.setdefault(platform, []).extend(sorted(entry["usernames"]))
            else:
                match_keys.setdefault(platform, []).append(username)
            if verify:
                url = (
                    f"https://www.threads.com/@{username}"
                    if platform == "threads"
                    else f"https://x.com/{username}"
                )
                if not verify_url_opens(url):
                    print(f"      [MISS] {name} {platform} {handle} — 주소 미확인, 칸을 비운다")
                    channels.pop(platform, None)
                    unverified.append(platform)
                    continue

        elif platform == "linkedin":
            entry = find_author(stats, "linkedin", aliases)
            if entry:
                stats_hit = _merge_stats(stats_hit, entry)
                # 저장글의 불투명 ID(ACoAA...)가 매칭 키다. slug 와 다른 값이라
                # 이걸 안 넣으면 LinkedIn 은 R5·R8 이 성립하지 않는다(SPEC D12).
                match_keys.setdefault("linkedin", []).extend(sorted(entry["usernames"]))
            slug = handle.rstrip("/").split("/")[-1]
            if slug and slug not in match_keys.get("linkedin", []):
                match_keys.setdefault("linkedin", []).append(slug)
            if verify and not verify_url_opens(f"https://www.linkedin.com/in/{slug}/"):
                # LinkedIn 은 비로그인에서 막는 경우가 많다. 주소를 비우지 않고
                # 표시만 남긴다 - 비우면 실제로 유효한 계정을 못 켜게 된다.
                print(f"      [WARN] {name} linkedin {slug} — 비로그인 확인 실패(주소는 유지)")

    for platform in list(match_keys):
        match_keys[platform] = sorted({key for key in match_keys[platform] if key})

    account = {
        "id": seed["id"],
        "name": name,
        "group": seed.get("group", ""),
        "status": seed.get("status", "off"),
        "purpose": seed.get("purpose", "형식학습"),
        "limit": seed.get("limit", DEFAULT_LIMIT),
        "channels": channels,
        "match_keys": match_keys,
        "collectable": sorted(set(channels) & COLLECTABLE_PLATFORMS),
        "unverified": sorted(set(unverified)),
        "memo": seed.get("memo", ""),
        "saved_count": stats_hit["saved_count"],
        "last_saved_at": stats_hit["last_saved_at"],
        "sources": ["seed"],
    }
    if stats_hit["saved_count"]:
        account["sources"].append("scrap_sns")
    if profile_channels_for(profiles, name):
        account["sources"].append("creator_profile")
    return account


def _merge_stats(current: dict, entry: dict) -> dict:
    return {
        "saved_count": current["saved_count"] + entry["saved_count"],
        "last_saved_at": max(current["last_saved_at"], entry["last_saved_at"]),
    }


def merge_preserving_user_settings(existing: list, incoming: list) -> tuple[list, dict]:
    by_id = {str(account.get("id")): account for account in existing if account.get("id")}
    result = []
    report = {"kept": 0, "added": 0, "skipped_excluded": 0, "orphaned": 0}

    for account in incoming:
        account_id = account["id"]
        previous = by_id.pop(account_id, None)
        if previous is None:
            result.append(account)
            report["added"] += 1
            continue
        if str(previous.get("status")) == "excluded":
            # 뺀 계정은 다시 올리지 않는다. 소스에 남아 있어도 마찬가지다(R10).
            result.append(previous)
            report["skipped_excluded"] += 1
            continue
        merged = dict(account)
        for field in USER_OWNED_FIELDS:
            if field in previous:
                merged[field] = previous[field]
        result.append(merged)
        report["kept"] += 1

    # 소스에서 사라진 계정도 지우지 않는다. 이미 수집한 글이 가리킬 대상을 잃는다.
    for leftover in by_id.values():
        leftover = dict(leftover)
        leftover["orphaned"] = True
        result.append(leftover)
        report["orphaned"] += 1

    result.sort(key=lambda item: str(item.get("id")))
    return result, report


def main() -> int:
    parser = argparse.ArgumentParser(description="벤치마킹 후보 풀 동기화")
    parser.add_argument("--dry-run", action="store_true", help="결과만 출력하고 저장하지 않는다")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="주소가 실제로 열리는지 확인하고, 실패하면 칸을 비운다(SPEC D10)",
    )
    args = parser.parse_args()

    seed = load_json(SEED_PATH, {}) or {}
    seed_accounts = seed.get("accounts") or []
    if not seed_accounts:
        print(f"[ERROR] 시드가 비었다: {SEED_PATH}", file=sys.stderr)
        return 1

    api_key = ""
    if args.verify:
        load_env()
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            print("[WARN] YOUTUBE_API_KEY 가 없어 유튜브 확인을 건너뛴다")

    print(f"소스 1 수집 데이터: {os.path.basename(latest_total_file() or '(없음)')}")
    stats = collect_author_stats()
    print(f"   저자 {len(stats)}명")
    profiles = parse_creator_profiles()
    print(f"소스 2 제작자 프로필: {len(profiles)}명 (주소 보유)")
    print(f"소스 3 시드 명단: {len(seed_accounts)}계정\n")

    incoming = []
    for entry in seed_accounts:
        incoming.append(build_account(entry, stats, profiles, args.verify, api_key))

    existing_doc = load_json(OUTPUT_PATH, {"accounts": []}) or {"accounts": []}
    existing = existing_doc.get("accounts") or []
    merged, report = merge_preserving_user_settings(existing, incoming)

    by_status = defaultdict(int)
    for account in merged:
        by_status[account.get("status", "off")] += 1

    print(
        f"\n결과 {len(merged)}계정 — "
        + " ".join(f"{name}={count}" for name, count in sorted(by_status.items()))
    )
    print(
        f"   신규 {report['added']} · 설정 보존 {report['kept']} · "
        f"excluded 유지 {report['skipped_excluded']} · 소스에서 사라짐 {report['orphaned']}"
    )
    missing = [a["name"] for a in merged if a.get("unverified")]
    if missing:
        print(f"   ⚠️ 주소 미확인이 있는 계정: {', '.join(missing)}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일을 건드리지 않고 종료한다.")
        return 0

    atomic_write_json(OUTPUT_PATH, {"accounts": merged})
    print(f"\n저장: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
