"""제작자 레지스트리 — 여러 플랫폼 계정을 한 사람으로 묶는다.

왜 이 파일이 필요한가
---------------------
뷰어는 같은 사람의 Threads·LinkedIn·YouTube 글을 서로 다른 인물로 본다. 볼트에는
제작자 프로필(`_제작자별_상세/`)이 이미 있고, 거기 적힌 채널 주소가 가장 정확한
연결 재료다(SPEC D5 층 2). 여기서는 그 레지스트리를 읽고, 사용자가 뷰어에서
확정한 연결(`sns_creator_links.json`)을 합쳐 글 → 제작자 판정을 한다.

벤치마킹 계정 파일(`benchmark_accounts.json`)에 제작자를 넣지 않는다 - 켜진 계정은
수집기 3곳이 계정째 긁는다(F24). 스키마(`channels`·`match_keys`)만 같게 해서
판정 엔진(`utils/benchmark_match.py`)을 그대로 쓴다.

이름으로 잇지 않는다(SPEC 20260906_01 D12). 판정 키는 채널 핸들·채널 ID·
불투명 ID 뿐이다. 이름·본문 링크로 찾은 것은 후보로만 둔다(F23 동명이인 실측).

서버(`scrap_sns_server._load_latest_posts`)·생성기(`scripts/build_creator_registry.py`)
가 같이 쓴다. 계획: _docs/20260911_01 (W4 T4-a~T4-c)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.benchmark_match import build_match_index, match_account_id, normalize_key  # noqa: E402

KST = timezone(timedelta(hours=9))
LINK_PLATFORMS = ("threads", "x", "linkedin", "youtube")
LINK_SOURCES = ("user", "self_declared")
# 판정 인덱스에 넣는 채널. 핸들이 글의 username 과 같은 값인 플랫폼만이다 -
# youtube 채널 칸은 @handle 이라 글의 채널 표시명과 우연히 겹칠 수 있고,
# linkedin 칸은 slug 라 글의 불투명 ID 와 접점이 없다(계획 T4-a).
_INDEX_CHANNEL_PLATFORMS = ("threads", "x")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def is_safe_creator_id(value) -> bool:
    """경로로 쓰일 수 없는 모양인지. 제작자 id 는 볼트 프로필 파일명(확장자 제외)이다."""
    text = str(value or "")
    if not text or len(text) > 120 or text != text.strip():
        return False
    if text in (".", "..") or text.startswith(".") or ".." in text:
        return False
    if any(ch in text for ch in '/\\:*?"<>|') or _CONTROL_RE.search(text):
        return False
    return True


def handle_from_channel(platform: str, value) -> str:
    """프로필 채널 칸(주소 또는 핸들) → 판정 키. 못 읽으면 빈 문자열.

    threads·x 는 소문자 핸들(@ 없음), youtube 는 `@handle`, linkedin 은 slug.
    """
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    link = re.search(r"\]\(([^)]+)\)", raw)
    if link:
        raw = link.group(1)
    if raw.lower().startswith(("http://", "https://")):
        parts = urlsplit(raw)
        segments = [unquote(s) for s in parts.path.split("/") if s]
        if platform in ("threads", "youtube"):
            at = next((s for s in segments if s.startswith("@")), "")
            if not at:
                return ""
            raw = at
        elif platform == "x":
            raw = segments[0] if segments else ""
        elif platform == "linkedin":
            if "in" in segments and segments.index("in") + 1 < len(segments):
                raw = segments[segments.index("in") + 1]
            else:
                return ""
        else:
            return ""
    raw = raw.strip().rstrip("/")
    if platform == "youtube":
        handle = raw.lstrip("@")
        return f"@{handle}" if re.fullmatch(r"[A-Za-z0-9._-]{2,}", handle) else ""
    if platform in ("threads", "x"):
        return normalize_key(raw)
    if platform == "linkedin":
        return raw.lower()
    return ""


def load_json(path: str, fallback):
    if not path or not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_registry(path: str) -> list[dict]:
    data = load_json(path, {}) or {}
    creators = data.get("creators") if isinstance(data, dict) else None
    return [c for c in (creators or []) if isinstance(c, dict) and c.get("id")]


def load_links(path: str) -> list[dict]:
    data = load_json(path, {}) or {}
    links = data.get("links") if isinstance(data, dict) else None
    out = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        platform = str(link.get("platform") or "").lower()
        key = str(link.get("key") or "").strip()
        creator_id = str(link.get("creator_id") or "")
        if platform in LINK_PLATFORMS and key and is_safe_creator_id(creator_id):
            out.append({**link, "platform": platform, "key": key, "creator_id": creator_id})
    return out


def apply_links(creators: list[dict], links: list[dict]) -> list[dict]:
    """확정 연결을 레지스트리에 합친다. 원본 목록은 바꾸지 않는다.

    레지스트리에 없는 제작자 id 로 온 연결(프로필 없는 두 저자를 잇는 경우)은 새
    제작자를 만든다 - 이름은 연결을 저장할 때 받은 표시명이다.
    """
    merged = [
        {**c, "match_keys": {k: list(v) for k, v in (c.get("match_keys") or {}).items()}}
        for c in creators
    ]
    by_id = {c["id"]: c for c in merged}
    for link in links:
        creator = by_id.get(link["creator_id"])
        if creator is None:
            creator = {
                "id": link["creator_id"],
                "name": link.get("name") or link["creator_id"],
                "status": "active",
                "channels": {},
                "match_keys": {},
                "profile": False,
                "sources": ["links"],
            }
            merged.append(creator)
            by_id[creator["id"]] = creator
        keys = creator["match_keys"].setdefault(link["platform"], [])
        if link["key"] not in keys:
            keys.append(link["key"])
        creator.setdefault("linked_accounts", []).append(
            {"platform": link["platform"], "key": link["key"], "source": link.get("source") or "user"}
        )
    return merged


def build_creator_match_index(creators: list[dict]) -> dict:
    """{(platform, key): creator_id}. 먼저 온 제작자가 이긴다(프로필 있는 쪽이 앞)."""
    ordered = sorted(creators, key=lambda c: (not c.get("profile"), str(c.get("id"))))
    records = [
        {
            "id": c["id"],
            "status": "active",
            "match_keys": c.get("match_keys") or {},
            "channels": {
                platform: value
                for platform, value in (c.get("channels") or {}).items()
                if platform in _INDEX_CHANNEL_PLATFORMS
            },
        }
        for c in ordered
    ]
    return build_match_index(records)


def match_creator_id(post: dict, index: dict) -> str | None:
    return match_account_id(post, index)


def validate_link_request(payload) -> tuple[dict | None, str]:
    """`POST /api/save-creator-links` 입력 검증. (정규화된 요청, 오류 메시지)."""
    if not isinstance(payload, dict):
        return None, "expected JSON object"
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 10:
        return None, "accounts must be a list of 1-10 items"
    normalized = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            return None, f"accounts[{index}] must be an object"
        platform = str(account.get("platform") or "").strip().lower()
        if platform == "twitter":
            platform = "x"
        key = str(account.get("key") or "").strip()
        if platform not in LINK_PLATFORMS:
            return None, f"accounts[{index}].platform must be one of {list(LINK_PLATFORMS)}"
        if not key or len(key) > 200 or _CONTROL_RE.search(key):
            return None, f"accounts[{index}].key is invalid"
        normalized.append({"platform": platform, "key": key})
    creator_id = payload.get("creator_id")
    if creator_id in (None, ""):
        first = normalized[0]
        creator_id = f"link_{first['platform']}_{normalize_key(first['key'])}"[:120]
    creator_id = str(creator_id)
    if not is_safe_creator_id(creator_id):
        return None, "creator_id is invalid"
    source = str(payload.get("source") or "user")
    if source not in LINK_SOURCES:
        return None, f"source must be one of {list(LINK_SOURCES)}"
    name = str(payload.get("name") or "").strip()[:120]
    if _CONTROL_RE.search(name):
        return None, "name is invalid"
    return {"creator_id": creator_id, "name": name, "accounts": normalized, "source": source}, ""


def merge_link_request(existing_links: list[dict], request: dict) -> tuple[list[dict], int]:
    """요청을 연결 목록에 더한다. (새 목록, 새로 더한 수). 같은 연결은 다시 넣지 않는다."""
    links = list(existing_links)
    seen = {(l["creator_id"], l["platform"], normalize_key(l["key"])) for l in links}
    added = 0
    for account in request["accounts"]:
        marker = (request["creator_id"], account["platform"], normalize_key(account["key"]))
        if marker in seen:
            continue
        seen.add(marker)
        links.append(
            {
                "creator_id": request["creator_id"],
                "name": request["name"],
                "platform": account["platform"],
                "key": account["key"],
                "source": request["source"],
                "created_at": now_kst_iso(),
            }
        )
        added += 1
    return links, added
