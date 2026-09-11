"""볼트(`90_자료수집`)의 자료 노트를 뷰어의 글 형식으로 바꾼다.

왜 이 파일이 필요한가
---------------------
뷰어는 SNS 글만 보여준다. 실제로 참고하는 자료 상당수는 웹·파일로 배포돼 볼트에
쌓여 있는데 뷰어 검색에 걸리지 않는다. 볼트가 정본이고(SPEC D1) 뷰어는 읽기만
한다 - 여기서 만드는 것은 언제든 다시 만들 수 있는 파생 목록이다.

서버(`scrap_sns_server._load_latest_posts`)와 CLI(`python -m utils.library_index`)가
같은 함수를 쓴다. 규칙이 두 곳으로 갈라지면 화면과 CLI 건수가 어긋난다.

자료 노트 고르는 법 (SPEC F32)
-----------------------------
  `_`·`.`로 시작하지 않는 최상위 폴더 바로 아래의 `.md`(재귀하지 않는다) 중
  frontmatter 에 `topic`·`creator` 가 모두 있고 `type: creator` 가 아닌 것.
  폴더 목록으로 고르지 않는다 - 스킬 산출물 폴더가 섞여도 frontmatter 가 걸러낸다.

🔴 frontmatter 구분선은 **줄 단위로** 찾는다. `text.split("---")` 는 본문·경로 안의
   `-----` 에서 잘린다 - 실제로 `session_path: ...90-----/...` 인 노트 19건이
   조용히 빠졌다(2026-09-11 실측).

계획: _docs/20260911_01 (W2 T2-a·T2-b)
"""

from __future__ import annotations

import argparse
import bisect
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.post_meta import build_post_key  # noqa: E402

KST =timezone(timedelta(hours=9))
DEFAULT_VAULT_ROOT = os.path.join(os.path.expanduser("~"), "cowork", "90_자료수집")
LIBRARY_PLATFORMS = ("web", "file")

_FRONT_RE = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s+-\s*(.*)$")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
# 추적용 쿼리. 같은 글이 공유 경로에 따라 다른 URL 이 되는 원인이다.
_TRACKING_PARAM_RE = re.compile(
    r"^(utm_.*|fbclid|gclid|igsh|igshid|si|xmt|slof|ref|ref_src|rcm|trk|trkcampaign|"
    r"lipi|mibextid|source|feature|s|t)$",
    re.IGNORECASE,
)


def get_vault_root() -> str:
    """볼트 경로. `SNS_LIBRARY_VAULT` 로 바꿔 끼울 수 있다.

    검증·테스트가 운영 볼트 대신 표본 폴더를 읽게 하는 유일한 통로다
    (`SNS_BENCHMARK_ACCOUNTS_PATH` 와 같은 방식).
    """
    override = os.environ.get("SNS_LIBRARY_VAULT", "").strip()
    return os.path.abspath(override) if override else DEFAULT_VAULT_ROOT


# ------------------------------------------------------------ frontmatter

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def split_frontmatter(text: str) -> tuple[dict, str]:
    """(frontmatter dict, 본문). 볼트가 쓰는 YAML 부분집합만 읽는다.

    `key: value`, `key:` 아래 `  - item` 목록, `key: [a, b]` 인라인 목록.
    PyYAML 을 들이지 않는다 - 레포 의존성에 없고, 필요한 모양이 이 셋뿐이다.
    """
    text = str(text or "")
    match = _FRONT_RE.match(text)
    if not match:
        return {}, text.lstrip("﻿")

    front: dict = {}
    current_list_key = None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        item = _LIST_ITEM_RE.match(line)
        if item and current_list_key:
            value = _unquote(item.group(1))
            if value:
                front[current_list_key].append(value)
            continue
        key_match = _KEY_RE.match(line)
        if not key_match:
            current_list_key = None
            continue
        key, raw = key_match.group(1), key_match.group(2).strip()
        if not raw:
            front[key] = []
            current_list_key = key
            continue
        current_list_key = None
        if raw.startswith("[") and raw.endswith("]") and not raw.startswith("[["):
            front[key] = [_unquote(part) for part in raw[1:-1].split(",") if part.strip()]
        else:
            front[key] = _unquote(raw)
    return front, text[match.end():]


def _scalar(front: dict, key: str) -> str:
    value = front.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "").strip()


def parse_wikilink(value) -> tuple[str, str]:
    """`[[대상|표시]]` → (대상 파일명, 표시명). 위키링크가 아니면 (값, 값)."""
    text = str(value or "").strip()
    match = _WIKILINK_RE.search(text)
    if not match:
        return text, text
    target = match.group(1).strip().replace("\\", "/").split("/")[-1]
    if target.lower().endswith(".md"):
        target = target[:-3]
    display = (match.group(2) or "").strip() or target
    return target, display


# ------------------------------------------------------------ URL 대조 키

def url_key(url) -> str:
    """같은 글을 가리키는 URL 을 같은 문자열로 만든다.

    유튜브 영상 ID · 스레드 글 코드 · 링크드인 활동 ID · X 상태 ID 는 플랫폼 키로,
    그 밖의 URL 은 추적 파라미터를 뗀 정규 URL 로. http(s) 가 아니면 빈 문자열.
    """
    raw = str(url or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return ""
    parts = urlsplit(raw)
    host = parts.netloc.lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    query = dict(parse_qsl(parts.query))

    if host in ("youtube.com", "youtu.be", "music.youtube.com"):
        video_id = ""
        if host == "youtu.be":
            video_id = parts.path.strip("/").split("/")[0]
        elif query.get("v"):
            video_id = query["v"]
        else:
            shorts = re.match(r"^/(?:shorts|live|embed)/([A-Za-z0-9_-]{6,})", parts.path)
            video_id = shorts.group(1) if shorts else ""
        if video_id:
            return f"youtube:{video_id}"

    if host.startswith("threads."):
        post = re.search(r"/post/([A-Za-z0-9_-]+)", parts.path)
        if post:
            return f"threads:{post.group(1)}"

    if host.endswith("linkedin.com"):
        activity = re.search(r"(?:activity|ugcPost|share)(?:[-:]|%3A)(\d{15,})", raw)
        if activity:
            return f"linkedin:{activity.group(1)}"

    if host in ("x.com", "twitter.com"):
        status = re.search(r"/status/(\d+)", parts.path)
        if status:
            return f"x:{status.group(1)}"

    kept = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAM_RE.match(k)]
    path = parts.path.rstrip("/") or "/"
    return "url:" + urlunsplit(("https", host, path, urlencode(kept), ""))


def post_url_keys(post: dict) -> set:
    """수집 글 한 건이 가질 수 있는 대조 키 전부."""
    keys = set()
    for field in ("url", "canonical_url", "post_url"):
        key = url_key(post.get(field))
        if key:
            keys.add(key)
    platform = str(post.get("sns_platform") or "").strip().lower()
    identifier = str(post.get("platform_id") or post.get("code") or "").strip()
    if identifier:
        if platform in ("threads", "thread"):
            keys.add(f"threads:{identifier}")
        elif platform == "youtube":
            keys.add(f"youtube:{identifier}")
        elif platform == "linkedin":
            keys.add(f"linkedin:{identifier}")
        elif platform in ("x", "twitter"):
            keys.add(f"x:{identifier}")
    return keys


# ------------------------------------------------------------ 노트 선별·변환

def iter_note_paths(vault_root: str) -> list[str]:
    """선별 후보 `.md` 경로. frontmatter 판정 전 단계라 파일을 열지 않는다."""
    if not os.path.isdir(vault_root):
        return []
    paths = []
    for entry in sorted(os.scandir(vault_root), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        for child in sorted(os.scandir(entry.path), key=lambda item: item.name):
            if child.is_file() and child.name.lower().endswith(".md"):
                paths.append(child.path)
    return paths


def vault_state(vault_root: str) -> tuple:
    """(후보 파일 수, 최대 수정시각 ns). 서버 캐시 키에 들어간다.

    내용을 읽지 않고 stat 만 한다 - 300건 남짓이라 요청마다 해도 되지만 서버는
    30초에 한 번만 부른다(`scrap_sns_server._get_library_state`).
    """
    paths = iter_note_paths(vault_root)
    max_mtime = 0
    for path in paths:
        try:
            max_mtime = max(max_mtime, os.stat(path).st_mtime_ns)
        except OSError:
            continue
    return (len(paths), max_mtime)


def obsidian_url(path: str) -> str:
    """제작자 카드와 같은 형식이다(`scrap_sns_server.creator_profile`)."""
    return "obsidian://open?path=" + quote(os.path.abspath(path).replace("\\", "/"), safe="")


def _to_kst_text(value) -> str:
    """frontmatter `created` → `YYYY-MM-DD HH:MM:SS`. 못 읽으면 빈 문자열."""
    text = str(value or "").strip().replace("T", " ")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", text)
    if not match:
        return ""
    hour = int(match.group(2) or 0)
    minute = int(match.group(3) or 0)
    second = int(match.group(4) or 0)
    return f"{match.group(1)} {hour:02d}:{minute:02d}:{second:02d}"


_SOURCE_LINK_RES = (
    re.compile(r"!?\[\[([^\]|#]*_sources/[^\]|#]+)(?:[|#][^\]]*)?\]\]"),
    re.compile(r"\]\((<?)([^)>]*_sources/[^)>]+)>?\)"),
)


def _find_source_file(front: dict, body: str, note_path: str) -> str:
    """노트가 링크한 `_sources/` 의 비-md 원본 파일 절대경로. 없으면 빈 문자열."""
    targets = []
    for key in ("source_file", "original_file"):
        value = _scalar(front, key)
        if value:
            targets.append(parse_wikilink(value)[0] if "[[" in value else value)
            match = _WIKILINK_RE.search(value)
            if match:
                targets.append(match.group(1).strip())
    for pattern in _SOURCE_LINK_RES:
        for match in pattern.finditer(body):
            targets.append(match.group(match.lastindex))
    note_dir = os.path.dirname(note_path)
    for target in targets:
        target = str(target or "").strip().replace("%20", " ")
        if not target or target.lower().endswith(".md"):
            continue
        for base in (note_dir, os.path.dirname(note_dir)):
            candidate = os.path.normpath(os.path.join(base, target))
            if os.path.isfile(candidate):
                return candidate
    return ""


def note_to_post(note_path: str, vault_root: str) -> dict | None:
    """자료 노트 한 건 → 뷰어 글 dict. 자료 노트가 아니면 None."""
    try:
        with open(note_path, "r", encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
        mtime = os.stat(note_path).st_mtime
    except OSError:
        return None

    front, body = split_frontmatter(text)
    topic = _scalar(front, "topic")
    creator_raw = _scalar(front, "creator")
    if not topic or not creator_raw or _scalar(front, "type") == "creator":
        return None

    source_url = _scalar(front, "source_url")
    is_web = source_url.lower().startswith(("http://", "https://"))
    key = url_key(source_url) if is_web else ""
    stem = os.path.splitext(os.path.basename(note_path))[0]
    # 영구 키(`web:…`·`file:…`)가 된다. 별표·메모가 이 값에 붙는다(SPEC D6).
    platform_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] if is_web else stem
    creator_key, creator_display = parse_wikilink(creator_raw)
    relative = os.path.relpath(note_path, vault_root).replace("\\", "/")
    note_link = obsidian_url(note_path)
    crawled_at = datetime.fromtimestamp(mtime, KST).replace(tzinfo=None).isoformat(timespec="seconds")
    created_at = _to_kst_text(_scalar(front, "created")) or crawled_at.replace("T", " ")
    tags = front.get("tags") if isinstance(front.get("tags"), list) else (
        [front["tags"]] if front.get("tags") else []
    )
    source_file = _find_source_file(front, body, note_path)

    return {
        "sns_platform": "web" if is_web else "file",
        "platform_id": platform_id,
        "username": creator_key,
        "display_name": creator_display,
        "full_text": body.lstrip("\r\n"),
        "url": source_url if is_web else note_link,
        "created_at": created_at,
        "date": created_at[:10],
        "crawled_at": crawled_at,
        # 「저장」 필터에 자료가 들어간다. 별표가 아니다 - 별표는 post_key 기준
        # 사용자 메타의 favorite 이다(계획 W2 T2-a).
        "is_saved": True,
        "is_own_post": False,
        "media": [],
        "local_images": [],
        "library_title": _scalar(front, "title") or stem,
        "library_path": relative,
        "library_topic": topic,
        "library_tags": [str(tag) for tag in tags if str(tag).strip()],
        "library_source_type": _scalar(front, "source_type"),
        "library_creator": creator_key,
        "library_obsidian_url": note_link,
        "library_has_source_file": bool(source_file),
        "library_source_file_url": obsidian_url(source_file) if source_file else "",
        "library_url_key": key,
    }


def build_library_posts(vault_root: str | None = None) -> list[dict]:
    vault_root = vault_root or get_vault_root()
    posts = []
    for path in iter_note_paths(vault_root):
        post = note_to_post(path, vault_root)
        if post:
            posts.append(post)
    return posts


# ------------------------------------------------------------ 수집 글과 잇기

def assign_sort_seq(library_posts: list[dict], sns_posts: list[dict]) -> None:
    """「로컬수집순」 자리. 자료를 SNS 수집 시각 사이에 끼워 넣는다.

    순번(`sequence_id`)은 통합본 최대값 뒤에 붙으므로 그대로 정렬하면 자료
    280여 건이 기본 화면 맨 위를 통째로 덮는다. SNS 글은 수집 순서대로 순번이
    매겨지고(`crawled_at` 2,845/2,922건 보유) 자료는 `created` 가 볼트에 넣은
    날이라, 둘을 같은 시간축에 놓는다. 값은 "그 시각까지 수집된 SNS 글의 최대
    순번 + 0.5" 다.
    """
    timeline = sorted(
        (str(post.get("crawled_at") or "").replace(" ", "T"), post.get("sequence_id") or 0)
        for post in sns_posts
        if post.get("crawled_at")
    )
    times, running_max = [], []
    current = 0
    for moment, seq in timeline:
        current = max(current, int(seq or 0))
        times.append(moment)
        running_max.append(current)
    for post in library_posts:
        moment = str(post.get("created_at") or "").replace(" ", "T")
        if moment.endswith("T00:00:00"):
            # 날짜만 적힌 노트는 그날 수집분 뒤에 둔다.
            moment = moment[:10] + "T23:59:59"
        index = bisect.bisect_right(times, moment)
        post["sort_seq"] = (running_max[index - 1] if index else 0) + 0.5


def link_library_posts(library_posts: list[dict], sns_posts: list[dict], start_seq: int) -> tuple[list, list]:
    """(목록에 올릴 자료, 원문 SNS 카드가 이미 있는 겹침 자료).

    겹침 자료는 카드로 만들지 않는다(SPEC D4) - 원문 SNS 글에 `library_notes` 로
    연결만 하고 상세 조회용으로 보관한다. 순번은 둘 다에게 준다(읽기 모달이
    `/api/post/<seq>` 로 본문을 받는다).
    """
    by_key: dict[str, dict] = {}
    for post in sorted(sns_posts, key=lambda item: item.get("sequence_id") or 0):
        for key in post_url_keys(post):
            by_key.setdefault(key, post)

    visible, overlaps = [], []
    for offset, note in enumerate(library_posts):
        note["sequence_id"] = start_seq + offset
        target = by_key.get(note.get("library_url_key") or "")
        if target is None:
            visible.append(note)
            continue
        note["library_overlap_of"] = build_post_key(target)
        target.setdefault("library_notes", []).append(
            {
                "sequence_id": note["sequence_id"],
                "title": note.get("library_title") or "",
                "path": note.get("library_path") or "",
            }
        )
        overlaps.append(note)
    assign_sort_seq(visible, sns_posts)
    return visible, overlaps


# ------------------------------------------------------------ 인덱스 파일

def write_index_file(path: str, visible: list, overlaps: list, vault_root: str) -> None:
    """`web_viewer/sns_library_index.json`. CLI(`utils/query-sns.mjs`)가 읽는다.

    git 에서 뺀다 - 볼트에서 언제든 재생성되고 본문을 담아 수 MB 다(계획 §4).
    """
    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "vault_root": vault_root.replace("\\", "/"),
        "note_count": len(visible) + len(overlaps),
        "visible_count": len(visible),
        "overlap_count": len(overlaps),
        "posts": visible + overlaps,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(tmp_path, path)


def orphan_metadata_keys(user_metadata: dict, library_posts: list[dict]) -> list[str]:
    """사용자 메타에만 있고 인덱스에 없는 `web:`·`file:` 키.

    파일 자료의 영구 키가 파일명이라, 옵시디언에서 이름을 바꾸면 별표·메모가
    떨어진다. 조용히 사라지지 않게 드러낸다(계획 §7 리스크).
    """
    live = {f"{post['sns_platform']}:{post['platform_id']}" for post in library_posts}
    return sorted(
        key for key in (user_metadata or {})
        if key.startswith(("web:", "file:")) and key not in live
    )


def _latest_total_posts(project_root: str) -> tuple[str, list]:
    pattern = os.path.join(project_root, "output_total", "total_full_*.json")
    files = sorted(p for p in glob.glob(pattern) if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(p)))
    if not files:
        return "", []
    with open(files[-1], "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return files[-1], data.get("posts", []) if isinstance(data, dict) else data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="볼트 자료 인덱스 생성")
    parser.add_argument("--vault", default=None, help="볼트 경로 (기본: SNS_LIBRARY_VAULT 또는 ~/cowork/90_자료수집)")
    parser.add_argument("--write", action="store_true", help="web_viewer/sns_library_index.json 을 쓴다")
    args = parser.parse_args(argv)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vault_root = os.path.abspath(args.vault) if args.vault else get_vault_root()
    total_path, sns_posts = _latest_total_posts(project_root)
    library = build_library_posts(vault_root)
    start_seq = max((int(p.get("sequence_id") or 0) for p in sns_posts), default=0) + 1
    visible, overlaps = link_library_posts(library, sns_posts, start_seq)

    counts = {"web": 0, "file": 0}
    for post in visible:
        counts[post["sns_platform"]] += 1
    print(f"볼트: {vault_root}")
    print(f"통합본: {os.path.basename(total_path) or '(없음)'} {len(sns_posts)}건")
    print(f"자료 노트 {len(library)}건 = 목록 {len(visible)} (웹 {counts['web']} · 파일 {counts['file']}) + 겹침 {len(overlaps)}")

    metadata_path = os.path.join(project_root, "web_viewer", "sns_user_metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8-sig") as handle:
            orphans = orphan_metadata_keys(json.load(handle), library)
        for key in orphans:
            print(f"⚠️ 사용자 메타에만 있는 자료 키(이름이 바뀌었나?): {key}")

    if args.write:
        out = os.path.join(project_root, "web_viewer", "sns_library_index.json")
        write_index_file(out, visible, overlaps, vault_root)
        print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
