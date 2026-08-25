"""YouTube 저장 영상(재생목록) 수집기.

계획서: _docs/20260824_05_유튜브-저장영상-수집-반영-계획.md

다른 플랫폼과 달리 로그인 세션이 아니라 YouTube Data API 키로 동작한다.
자막은 yt-dlp + bgutil PO token provider(HTTP 서버 모드)로 취득하며,
provider 가 죽어 있으면 자막만 건너뛰고 메타 수집은 계속한다.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from utils.common import load_json, save_json
from utils.post_schema import normalize_post

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output_youtube")
OUTPUT_PYTHON_DIR = os.path.join(OUTPUT_DIR, "python")
TRANSCRIPT_DIR = os.path.join(OUTPUT_DIR, "transcripts")
SUMMARY_DIR = os.path.join(OUTPUT_DIR, "summaries")

# 계획서 2.1 — 대상 재생목록 전체를 생략 없이 하드코딩한다.
PLAYLISTS = [
    {"id": "PLed50f9DS0U_2zUeb8wnx9eZE8KujNUrw", "name": "drive7"},
    {"id": "PLed50f9DS0U84I1iUexAcbbftO8Wfu0Uk", "name": "ai.new2"},
    {"id": "PL-CeeIoxo5BbEiL6dQzgz4QBzgEcE7Jz8", "name": "기획new"},
]
# 계획서 4.7 — 1차 실행은 파일럿 1개만. 전량은 --playlists all 로 명시 지정한다.
DEFAULT_PLAYLISTS = ["drive7"]

RECENT_MONTHS = 6
UNAVAILABLE_TITLES = {"Deleted video", "Private video"}

API_BASE = "https://www.googleapis.com/youtube/v3"
POT_PROVIDER_URL = "http://127.0.0.1:4416"
POT_PROVIDER_DIR = os.path.join(os.path.expanduser("~"), "bgutil-ytdlp-pot-provider", "server")
POT_PROVIDER_ENTRY = os.path.join(POT_PROVIDER_DIR, "build", "main.js")
POT_READY_TIMEOUT_SECONDS = 90

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 요약 모델은 Flash 로 고정한다. 전역 GEMINI_MODEL 은 다른 용도(gemini-2.5-pro)로 설정돼
# 있어서 그대로 상속하면 단순 요약에 Pro 요금이 붙는다. 바꾸려면 --summary-model 을 쓴다.
SUMMARY_MODEL = "gemini-flash-latest"
SUMMARY_PROMPT = (
    "다음은 유튜브 영상의 자막 전문이다. 이 영상이 무엇을 다루는지 한국어 평문으로 "
    "3~5문장, 400자 이내로 요약하라. 불릿·헤딩·마크다운 기호를 쓰지 말고 문장만 출력하라.\n\n"
)
SUMMARY_MAX_CHARS = 400
SUMMARY_RETRY_DELAYS = [2, 4, 8]
TRANSCRIPT_WORKERS = 4


# ---------------------------------------------------------------- env / util

def load_env():
    """~/.env 를 읽어 필요한 키만 os.environ 에 채운다(값은 출력하지 않는다)."""
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
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def now_kst_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_api_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def to_local_naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone(timedelta(hours=9))).replace(tzinfo=None)


def sha1_of(text):
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- YouTube API

def api_get(path, params, api_key):
    query = dict(params)
    query["key"] = api_key
    response = requests.get(f"{API_BASE}/{path}", params=query, timeout=20)
    if response.status_code == 404:
        raise RuntimeError(f"{path} 404 — 재생목록이 삭제되었거나 비공개로 바뀌었습니다: {params}")
    if response.status_code != 200:
        raise RuntimeError(f"{path} HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def fetch_playlist_items(playlist, api_key):
    items = []
    page_token = None
    while True:
        params = {
            "part": "snippet,contentDetails,status",
            "playlistId": playlist["id"],
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = api_get("playlistItems", params, api_key)
        items.extend(payload.get("items", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return items


def fetch_video_details(video_ids, api_key):
    details = {}
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start:start + 50]
        payload = api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
            api_key,
        )
        for item in payload.get("items", []):
            details[item["id"]] = item
    return details


def pick_thumbnail(thumbnails):
    for key in ("maxres", "standard", "high", "medium", "default"):
        entry = (thumbnails or {}).get(key)
        if entry and entry.get("url"):
            return entry["url"]
    return ""


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- PO provider

def provider_alive():
    for endpoint in ("/ping", "/get_pot"):
        try:
            response = requests.get(f"{POT_PROVIDER_URL}{endpoint}", timeout=3)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def ensure_provider():
    """provider 를 확인하고 필요하면 띄운다. (사용 가능 여부, 우리가 띄웠는지) 반환."""
    if provider_alive():
        print("   ✅ PO token provider 이미 실행 중 (포트 4416)")
        return True, None

    if not os.path.exists(POT_PROVIDER_ENTRY):
        print(f"   ❌ PO token provider 를 찾을 수 없습니다: {POT_PROVIDER_ENTRY}")
        return False, None

    print("   🚀 PO token provider 기동 중...")
    creation_flags = 0x08000000 if sys.platform == "win32" else 0
    process = subprocess.Popen(
        ["node", POT_PROVIDER_ENTRY],
        cwd=POT_PROVIDER_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    deadline = time.time() + POT_READY_TIMEOUT_SECONDS
    started = time.time()
    while time.time() < deadline:
        if provider_alive():
            print(f"   ✅ PO token provider 준비 완료 ({time.time() - started:.0f}초)")
            return True, process
        time.sleep(1)

    print(f"   ❌ PO token provider 가 {POT_READY_TIMEOUT_SECONDS}초 내 응답하지 않았습니다. 자막 수집을 건너뜁니다.")
    try:
        process.terminate()
    except Exception:
        pass
    return False, None


def stop_provider(process):
    if process is None:
        return
    try:
        process.terminate()
        print("   🛑 수집기가 띄운 PO token provider 를 종료했습니다.")
    except Exception:
        pass


# ---------------------------------------------------------------- transcript

VTT_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->")
VTT_TAG_RE = re.compile(r"<[^>]+>")


def clean_vtt(raw_text):
    lines = []
    previous = None
    for line in str(raw_text).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if VTT_TIMESTAMP_RE.match(line) or "-->" in line:
            continue
        if line.isdigit():
            continue
        line = html.unescape(VTT_TAG_RE.sub("", line)).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines)


def transcript_path_for(video_id):
    return os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")


def download_transcript(video_id, scratch_dir):
    """yt-dlp 로 자동 자막을 받아 정제 텍스트를 반환. (status, text) 반환."""
    target = transcript_path_for(video_id)
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as handle:
            return "ok", handle.read()

    os.makedirs(scratch_dir, exist_ok=True)
    output_template = os.path.join(scratch_dir, f"{video_id}.%(ext)s")
    command = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs", "ko-orig,ko,en",
        "--sub-format", "vtt",
        "--extractor-args", "youtube:player_client=web_safari",
        "-o", output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180, check=False,
        )
    except subprocess.TimeoutExpired:
        return "failed", ""

    produced = sorted(glob.glob(os.path.join(scratch_dir, f"{video_id}*.vtt")))
    if not produced:
        combined = f"{completed.stdout}\n{completed.stderr}"
        if "PO token" in combined:
            return "blocked", ""
        return "no_subtitle", ""

    with open(produced[0], "r", encoding="utf-8", errors="replace") as handle:
        cleaned = clean_vtt(handle.read())

    for path in produced:
        try:
            os.remove(path)
        except OSError:
            pass

    if not cleaned:
        return "no_subtitle", ""

    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(cleaned)
    return "ok", cleaned


# ---------------------------------------------------------------- summary

def summary_path_for(video_id):
    return os.path.join(SUMMARY_DIR, f"{video_id}.json")


def load_cached_summary(video_id, transcript_sha1):
    path = summary_path_for(video_id)
    if not os.path.exists(path):
        return None
    cached = load_json(path, {})
    if not isinstance(cached, dict):
        return None
    if cached.get("transcript_sha1") != transcript_sha1:
        return None
    return cached.get("summary") or None


def store_summary(video_id, model, transcript_sha1, summary):
    save_json(
        summary_path_for(video_id),
        {
            "video_id": video_id,
            "model": model,
            "generated_at": now_kst_iso(),
            "summary": summary,
            "transcript_sha1": transcript_sha1,
        },
    )


def request_gemini_summary(transcript, model, api_key):
    body = {
        "contents": [{"parts": [{"text": SUMMARY_PROMPT + transcript[:120000]}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            # gemini-flash-latest 는 thinking 모델이라 기본값으로 두면 사고 토큰이
            # 출력 예산을 먹어 요약이 잘려 나온다(실측: 9토큰 질문에 thinking 26토큰).
            # 단순 요약에는 사고가 필요 없고 출력 요금만 늘므로 끈다.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    response = requests.post(
        GEMINI_ENDPOINT.format(model=model),
        params={"key": api_key},
        json=body,
        timeout=90,
    )
    if response.status_code != 200:
        raise RuntimeError(f"gemini HTTP {response.status_code}: {response.text[:200]}")
    payload = response.json()
    parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("gemini 응답에 텍스트가 없습니다")
    return text[:SUMMARY_MAX_CHARS]


def summarize(video_id, transcript, model, api_key, refresh):
    """(summary, status) 반환. 429 등 실패는 지수 백오프 3회 후 포기한다."""
    if not transcript:
        return "", "no_transcript"

    transcript_sha1 = sha1_of(transcript)
    if not refresh:
        cached = load_cached_summary(video_id, transcript_sha1)
        if cached:
            return cached, "ok"

    if not api_key:
        return "", "failed"

    for attempt, delay in enumerate(SUMMARY_RETRY_DELAYS + [None]):
        try:
            summary = request_gemini_summary(transcript, model, api_key)
            store_summary(video_id, model, transcript_sha1, summary)
            return summary, "ok"
        except Exception as error:
            if delay is None:
                print(f"      ⚠️ 요약 실패 {video_id}: {error}")
                return "", "failed"
            time.sleep(delay)
    return "", "failed"


# ---------------------------------------------------------------- collection

def select_playlists(selector):
    if selector.strip().lower() == "all":
        return list(PLAYLISTS)
    wanted = [name.strip() for name in selector.split(",") if name.strip()]
    chosen = [entry for entry in PLAYLISTS if entry["name"] in wanted]
    unknown = sorted(set(wanted) - {entry["name"] for entry in chosen})
    if unknown:
        raise SystemExit(f"알 수 없는 재생목록 이름: {', '.join(unknown)}")
    return chosen


def find_latest_full_file():
    files = glob.glob(os.path.join(OUTPUT_PYTHON_DIR, "youtube_py_full_*.json"))
    return max(files, key=os.path.getmtime) if files else None


def load_existing_posts():
    latest = find_latest_full_file()
    if not latest:
        return {}
    data = load_json(latest, {})
    posts = data.get("posts", []) if isinstance(data, dict) else data
    return {str(post.get("platform_id")): post for post in posts if post.get("platform_id")}


def collect_playlist_entries(playlists, api_key):
    cutoff = datetime.now() - timedelta(days=RECENT_MONTHS * 30)
    entries = {}
    for playlist in playlists:
        print(f"   📃 {playlist['name']} 재생목록 조회 중...")
        items = fetch_playlist_items(playlist, api_key)
        kept = 0
        for item in items:
            snippet = item.get("snippet") or {}
            title = str(snippet.get("title") or "")
            if title in UNAVAILABLE_TITLES:
                continue
            video_id = (item.get("contentDetails") or {}).get("videoId") or (
                snippet.get("resourceId") or {}
            ).get("videoId")
            if not video_id:
                continue
            added_at = to_local_naive(parse_api_datetime(snippet.get("publishedAt")))
            if added_at and added_at < cutoff:
                continue
            if video_id in entries:
                continue
            entries[video_id] = {
                "video_id": video_id,
                "playlist": playlist["name"],
                "playlist_added_at": added_at.strftime("%Y-%m-%d %H:%M:%S") if added_at else "",
            }
            kept += 1
        print(f"      전체 {len(items)}건 → 최근 {RECENT_MONTHS}개월 대상 {kept}건")
    return entries


def build_post(entry, detail, transcript_status, transcript, summary, summary_status):
    snippet = detail.get("snippet") or {}
    statistics = detail.get("statistics") or {}
    content_details = detail.get("contentDetails") or {}
    video_id = entry["video_id"]

    title = str(snippet.get("title") or "").strip()
    description = str(snippet.get("description") or "").strip()
    parts = [title, description]
    if summary:
        parts.append(f"[요약] {summary}")
    full_text = "\n\n".join(part for part in parts if part)

    published = to_local_naive(parse_api_datetime(snippet.get("publishedAt")))
    created_at = published.strftime("%Y-%m-%d %H:%M:%S") if published else ""
    thumbnail = pick_thumbnail(snippet.get("thumbnails"))
    channel = str(snippet.get("channelTitle") or "").strip() or "Unknown"

    post = {
        "platform_id": video_id,
        "sns_platform": "youtube",
        "code": video_id,
        "username": channel,
        "display_name": channel,
        "full_text": full_text,
        "media": [thumbnail] if thumbnail else [],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "created_at": created_at,
        "crawled_at": now_kst_iso(),
        "source": entry["playlist"],
        "is_detail_collected": True,
        "like_count": to_int(statistics.get("likeCount")),
        "comment_count": to_int(statistics.get("commentCount")),
        "view_count": to_int(statistics.get("viewCount")),
        "share_count": None,
        "quote_count": None,
        "bookmark_count": None,
        "playlist_added_at": entry["playlist_added_at"],
        "transcript_status": transcript_status,
        "transcript_path": (
            f"output_youtube/transcripts/{video_id}.txt" if transcript_status == "ok" else ""
        ),
        "transcript_length": len(transcript or ""),
        "summary_status": summary_status,
        "duration": content_details.get("duration") or "",
    }
    return normalize_post(post)


def run(mode, playlist_selector, refresh_summaries, summary_model=None):
    load_env()
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("❌ YOUTUBE_API_KEY 가 없습니다 (~/.env 확인). 수집을 중단합니다.")
        return 1

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_model = summary_model or SUMMARY_MODEL

    playlists = select_playlists(playlist_selector)
    print(f"🚀 YouTube Producer 시작 (모드: {mode}, 대상: {', '.join(p['name'] for p in playlists)})")

    entries = collect_playlist_entries(playlists, api_key)
    print(f"   📦 필터 통과 {len(entries)}건")

    existing = load_existing_posts()
    if mode == "update":
        pending = {vid: entry for vid, entry in entries.items() if vid not in existing}
        print(f"   🔁 update 모드: 신규 {len(pending)}건 (기존 {len(existing)}건 재사용)")
    else:
        pending = dict(entries)
        print(f"   🔁 all 모드: {len(pending)}건 전량 처리")

    details = fetch_video_details(list(pending.keys()), api_key) if pending else {}

    provider_ok, provider_process = (False, None)
    if pending:
        provider_ok, provider_process = ensure_provider()

    scratch_dir = os.path.join(OUTPUT_DIR, "_scratch")
    transcripts = {}
    if pending and provider_ok:
        print(f"   📝 자막 수집 {len(pending)}건 (병렬 {TRANSCRIPT_WORKERS})...")
        with ThreadPoolExecutor(max_workers=TRANSCRIPT_WORKERS) as pool:
            futures = {
                pool.submit(download_transcript, vid, scratch_dir): vid for vid in pending
            }
            for done, future in enumerate(futures, start=1):
                video_id = futures[future]
                try:
                    transcripts[video_id] = future.result()
                except Exception as error:
                    print(f"      ⚠️ 자막 실패 {video_id}: {error}")
                    transcripts[video_id] = ("failed", "")
                if done % 20 == 0:
                    print(f"      진행 {done}/{len(pending)}")
    elif pending:
        print("   ⚠️ PO token provider 미가동 — 자막 없이 메타만 수집합니다.")

    collected = []
    for video_id, entry in pending.items():
        detail = details.get(video_id)
        if not detail:
            continue
        transcript_status, transcript = transcripts.get(video_id, ("blocked" if not provider_ok else "failed", ""))
        summary, summary_status = summarize(
            video_id, transcript, gemini_model, gemini_key, refresh_summaries
        )
        collected.append(
            build_post(entry, detail, transcript_status, transcript, summary, summary_status)
        )

    stop_provider(provider_process)

    merged = dict(existing)
    for post in collected:
        merged[str(post["platform_id"])] = post

    posts = list(merged.values())
    posts.sort(key=lambda post: str(post.get("playlist_added_at") or ""), reverse=True)
    for index, post in enumerate(posts, start=1):
        post["sequence_id"] = index

    today = datetime.now().strftime("%Y%m%d")
    output_path = os.path.join(OUTPUT_PYTHON_DIR, f"youtube_py_full_{today}.json")
    save_json(
        output_path,
        {
            "metadata": {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(posts),
                "max_sequence_id": len(posts),
                "crawl_mode": mode,
                "playlists": [p["name"] for p in playlists],
                "new_count": len(collected),
                "transcript_available": provider_ok,
            },
            "posts": posts,
        },
    )

    ok_transcripts = sum(1 for post in posts if post.get("transcript_status") == "ok")
    ok_summaries = sum(1 for post in posts if post.get("summary_status") == "ok")
    print(f"✅ YouTube Producer 완료: 총 {len(posts)}건 (신규 {len(collected)}건)")
    print(f"   자막 {ok_transcripts}건, 요약 {ok_summaries}건")
    print(f"   저장: {output_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="YouTube 저장 영상(재생목록) 수집기")
    parser.add_argument("--mode", choices=["all", "update"], default="update")
    parser.add_argument(
        "--playlists",
        default=",".join(DEFAULT_PLAYLISTS),
        help="수집할 재생목록 이름(쉼표 구분) 또는 all. 기본값은 파일럿 대상 drive7",
    )
    parser.add_argument("--refresh-summaries", action="store_true", help="요약 캐시를 무시하고 재생성")
    parser.add_argument(
        "--summary-model",
        default=SUMMARY_MODEL,
        help=f"요약 모델(기본 {SUMMARY_MODEL}). 전역 GEMINI_MODEL 은 상속하지 않는다",
    )
    args = parser.parse_args()
    return run(args.mode, args.playlists, args.refresh_summaries, args.summary_model)


if __name__ == "__main__":
    sys.exit(main())
