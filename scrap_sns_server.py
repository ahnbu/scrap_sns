import os
import sys
import glob
import json
import re
import gzip
import logging
import ipaddress
import secrets
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS
from utils.post_meta import META_FIELDS, build_post_meta, canonicalize_url
from utils.auto_tag import match_post as match_auto_tags
from utils.library_index import (
    LIBRARY_PLATFORMS,
    build_library_posts,
    get_vault_root,
    link_library_posts,
    vault_state,
    write_index_file,
)
from utils.benchmark_match import normalize_key
from utils.creator_registry import (
    apply_links,
    build_creator_match_index,
    is_safe_creator_id,
    load_links,
    load_registry,
    match_creator_id,
    merge_link_request,
    validate_link_request,
)

# Define project root explicitly
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
WEB_VIEWER_DIR = os.path.join(PROJECT_ROOT, 'web_viewer')
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, 'index.html')
PUBLIC_ROOT_FILES = {'favicon.ico', 'favicon.png'}

app = Flask(__name__, static_folder=None)
CORS(app)

OUTPUT_TOTAL_DIR = os.path.join(PROJECT_ROOT, "output_total")
AUTH_RENEW_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "auth_runtime", "renew.py")
AUTH_RUNTIME_DIR = os.path.join(tempfile.gettempdir(), "scrap_sns_auth_runtime")
ALLOWED_AUTH_PLATFORMS = {"linkedin", "threads", "x"}
AUTH_JOBS = {}
AUTH_JOBS_LOCK = threading.Lock()
KST = timezone(timedelta(hours=9))
SCRAP_PROGRESS_MAX_EVENTS = 80
SCRAP_PROGRESS_TAIL_INTERVAL_SECONDS = 1
SCRAP_PROGRESS_LOG_SOURCES = {
    "Threads": os.path.join(PROJECT_ROOT, "logs", "threads.log"),
    "LinkedIn": os.path.join(PROJECT_ROOT, "logs", "linkedin.log"),
    "X/Twitter": os.path.join(PROJECT_ROOT, "logs", "x_twitter.log"),
    "YouTube": os.path.join(PROJECT_ROOT, "logs", "youtube.log"),
}
SCRAP_PROGRESS_LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "scrap_progress.log")
SCRAP_PROGRESS = {
    "run_id": "",
    "running": False,
    "seq": 0,
    "events": [],
    "started_at": None,
    "started_monotonic": None,
    "updated_at": None,
    "platform_list_new_counts": {},
}
SCRAP_PROGRESS_LOCK = threading.Lock()
# 비정상 종료로 running 이 참인 채 남으면 서버 재시작 전까지 새 수집이 영구히 막힌다.
# 이 시간을 넘긴 실행은 죽은 것으로 보고 새 실행을 허용한다.
# 값 근거: logs/scrap_progress.log 실측 --mode update 완료 1~6분, 관측 최대 13분 05초.
# 그 13배 여유다. --mode all + youtube 요약이 update 보다 오래 걸리는 것을 감안했다.
SCRAP_STALE_SECONDS = 10800
_POSTS_CACHE = {
    "path": "",
    "mtime": 0,
    "size": 0,
    "metadata_path": "",
    "metadata_mtime": 0,
    "metadata_size": 0,
    "posts_full": [],
    "posts_meta": [],
    "etag": "",
    "library_state": None,
    # 원문 SNS 카드가 이미 있는 자료. 목록에는 없고 「요약」 배지 → 상세 조회로만 연다.
    "library_overlaps": {},
    "library_count": 0,
}
# 볼트 상태(후보 노트 수·최대 수정시각)를 몇 초마다 다시 볼지. 캐시 키에 들어가므로
# 이것이 없으면 볼트를 고쳐도 화면이 안 바뀐다. 300건 stat 이라 가볍지만 목록
# 요청마다 할 일은 아니다. 계획: _docs/20260911_01 (W2 T2-c, 완료 기준 60초)
LIBRARY_STATE_TTL_SECONDS = 30
_LIBRARY_STATE = {"vault": "", "checked_at": None, "state": None, "written_state": None}


def _get_library_state(now=None):
    """(볼트 경로, 후보 노트 수, 최대 수정시각 ns). 30초 안에는 직전 값을 준다."""
    vault = get_vault_root()
    now = time.monotonic() if now is None else now
    checked_at = _LIBRARY_STATE.get("checked_at")
    if (
        _LIBRARY_STATE.get("vault") == vault
        and checked_at is not None
        and now - checked_at < LIBRARY_STATE_TTL_SECONDS
    ):
        return _LIBRARY_STATE["state"]
    count, max_mtime = vault_state(vault)
    state = (vault, count, max_mtime)
    _LIBRARY_STATE.update({"vault": vault, "checked_at": now, "state": state})
    return state


def _get_creators_path():
    """제작자 레지스트리(scripts/build_creator_registry.py 산출물). 검증용으로 바꿔 끼울 수 있다."""
    override = os.environ.get("SNS_CREATORS_PATH", "").strip()
    return os.path.abspath(override) if override else os.path.join(WEB_VIEWER_DIR, "sns_creators.json")


def _get_creator_links_path():
    """사용자가 뷰어에서 확정한 계정 연결. 검증이 운영 파일을 건드리지 않게 바꿔 끼울 수 있다."""
    override = os.environ.get("SNS_CREATOR_LINKS_PATH", "").strip()
    return os.path.abspath(override) if override else os.path.join(WEB_VIEWER_DIR, "sns_creator_links.json")


def _now_kst_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def _format_scrap_elapsed(started_monotonic):
    if started_monotonic is None:
        return None
    elapsed_seconds = max(0, int(time.monotonic() - started_monotonic))
    minutes, seconds = divmod(elapsed_seconds, 60)
    return f"{minutes:02d}:{seconds:02d} 경과"


def _parse_count(raw):
    try:
        return int(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _normalize_scrap_run_id(raw):
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(raw or ""))[:64]
    return safe_id or secrets.token_urlsafe(8)


def _scrap_progress_platform_label(platform):
    value = str(platform or "").strip().lower()
    if value in {"x/twitter", "x_twitter", "twitter", "x"}:
        return "X"
    if value == "threads":
        return "Threads"
    if value == "linkedin":
        return "LinkedIn"
    if value == "youtube":
        return "YouTube"
    # 내 게시물 수집기. 계획: _docs/20260826_03 (3.4)
    if value == "myposts":
        return "내 게시물"
    return str(platform or "").strip()


def _scrap_progress_phase_label(phase):
    value = str(phase or "").strip().lower()
    if value == "producer":
        return "목록"
    if value == "consumer":
        return "상세"
    return value or "스크랩"


def _scrap_progress_message_from_line(line):
    text = str(line or "").strip()
    if not text or text.startswith("SNS_SCRAP_SUMMARY"):
        return None

    if "플랫폼별 스크래퍼 병렬 실행 시작" in text:
        return "플랫폼별 스크랩 시작"
    if "Producer wave 시작" in text:
        return "목록 수집 단계 시작"
    if "Consumer wave 시작" in text:
        return "상세 수집 단계 시작"
    if "결과 병합 및 데이터 정규화 시작" in text:
        return "결과 병합 시작"
    if "이미지 처리 시작:" in text:
        return text.lstrip("🖼️ ").strip()
    if "이미지 처리 완료:" in text:
        return text.lstrip("✅ ").strip()
    if "이미지 다운로드 완료" in text:
        return "이미지 다운로드 완료"
    if "Total Full 저장 완료" in text:
        return "통합 파일 저장 완료"

    # 지표 갱신 결과를 완료 팝업까지 올린다. 이 함수는 화이트리스트라 분기를
    # 추가하지 않으면 total_scrap.py 가 아무리 출력해도 여기서 버려진다.
    # 이 한 줄이 매 실행마다 보이면 갱신 주기 재검토 시점을 사람이 기억할
    # 필요가 없다. 계획: _docs/20260826_02 (P4, W5)
    metric_refresh_match = re.search(r"(지표 갱신\s*[0-9,]+건\s*·\s*값이 바뀐 글\s*[0-9,]+건[^\n]*)", text)
    if metric_refresh_match:
        return metric_refresh_match.group(1).strip()

    running_match = re.search(
        r"\[\+\]\s*(Threads|LinkedIn|X/Twitter|YouTube|MyPosts)\s+(Producer|Consumer)\s+실행 중",
        text,
    )
    if running_match:
        platform = _scrap_progress_platform_label(running_match.group(1))
        phase = _scrap_progress_phase_label(running_match.group(2))
        return f"{platform} {phase} 수집 시작"

    done_match = re.search(
        r"✅\s*(Threads|LinkedIn|X/Twitter|YouTube|MyPosts)\s+(Producer|Consumer)\s+완료",
        text,
    )
    if done_match:
        platform = _scrap_progress_platform_label(done_match.group(1))
        phase = _scrap_progress_phase_label(done_match.group(2))
        return f"{platform} {phase} 수집 완료"

    auth_match = re.search(
        r"🔐\s*(Threads|LinkedIn|X/Twitter|YouTube|MyPosts)\s+(Producer|Consumer)\s+인증 필요",
        text,
    )
    if auth_match:
        platform = _scrap_progress_platform_label(auth_match.group(1))
        phase = _scrap_progress_phase_label(auth_match.group(2))
        return f"{platform} {phase} 인증 필요"

    failed_match = re.search(
        r"❌\s*(Threads|LinkedIn|X/Twitter|YouTube|MyPosts)\s+(Producer|Consumer)\s+종료",
        text,
    )
    if failed_match:
        platform = _scrap_progress_platform_label(failed_match.group(1))
        phase = _scrap_progress_phase_label(failed_match.group(2))
        return f"{platform} {phase} 수집 실패"

    return None


def _scrap_progress_message_from_log_line(platform, line):
    text = str(line or "").strip()
    if not text or text.startswith("=") or text.startswith("💻"):
        return None

    platform_label = _scrap_progress_platform_label(platform)

    # 유튜브는 시작 줄에 대상 재생목록이 함께 실린다. 재생목록 3개 중 1개만
    # 보고 있었는데 완료 팝업이 "0건 추가"만 보여줘 정상 동작과 범위 누락을
    # 구분할 수 없었다. phase_start_match 보다 먼저 판정해야 한다 - 그쪽이
    # 같은 줄을 먼저 잡아 대상 정보를 버린다.
    # 계획: _docs/20260826_02 (P3, W2-d)
    youtube_scope_match = re.search(
        r"🚀\s*YouTube Producer 시작 \(모드:\s*[^,]+,\s*대상:\s*([^)]+)\)",
        text,
    )
    if youtube_scope_match:
        scope = youtube_scope_match.group(1).strip()
        return f"YouTube 목록 수집 시작 (대상: {scope})"

    phase_start_match = re.search(
        r"🚀\s*(Threads|LinkedIn|X/Twitter|YouTube|MyPosts)\s+(Producer|Consumer)\s+시작",
        text,
    )
    if phase_start_match:
        matched_platform = _scrap_progress_platform_label(phase_start_match.group(1))
        phase = _scrap_progress_phase_label(phase_start_match.group(2))
        return f"{matched_platform} {phase} 수집 시작"

    current_count_match = re.search(
        r"(?:결과 더보기|스크롤 다운).+현재\s*([0-9,]+)개",
        text,
    )
    if current_count_match:
        return f"{platform_label} 목록 수집 중 {current_count_match.group(1)}개"

    list_new_count_match = re.search(
        r"최종 데이터\s*[0-9,]+개\s*저장 중\s*\(신규:\s*([0-9,]+)개\)",
        text,
    )
    if list_new_count_match:
        new_count = _parse_count(list_new_count_match.group(1))
        if new_count > 0:
            return {
                "message": f"{platform_label} 목록 신규 {new_count}건 발견",
                "platform": platform_label,
                "list_new_count": new_count,
            }
        return None

    target_match = re.search(r"\[Target\]\s*수집대상\s*([0-9,]+)개", text)
    if target_match:
        target_count = _parse_count(target_match.group(1))
        return {
            "message": f"{platform_label} 상세 수집 대상 {target_count}건",
            "platform": platform_label,
            "detail_target_count": target_count,
        }

    detail_done_match = re.search(
        r"수집 완료:.+\(([0-9,]+)/([0-9,]+),\s*([0-9,]+)%\)",
        text,
    )
    if detail_done_match:
        return (
            f"{platform_label} 상세 수집 중 "
            f"{detail_done_match.group(1)}/{detail_done_match.group(2)} "
            f"({detail_done_match.group(3)}%)"
        )

    if "상세 수집할 새로운 항목이 없습니다" in text:
        return f"{platform_label} 상세 수집 대상 없음"
    if "업데이트 데이터 저장 완료" in text:
        return f"{platform_label} 목록 파일 저장 완료"
    if "전체 데이터 파일 저장 완료" in text or "최종 상세 데이터 동기화 완료" in text:
        return f"{platform_label} 데이터 저장 완료"
    if "기준 게시물을" in text:
        return f"{platform_label} 기준 게시물 확인 완료"

    return None


def _snapshot_scrap_log_offsets():
    offsets = {}
    for platform, path in SCRAP_PROGRESS_LOG_SOURCES.items():
        try:
            offsets[platform] = os.path.getsize(path)
        except OSError:
            offsets[platform] = 0
    return offsets


def _collect_scrap_log_progress_once(offsets, buffers):
    for platform, path in SCRAP_PROGRESS_LOG_SOURCES.items():
        position = offsets.get(platform, 0)
        try:
            size = os.path.getsize(path)
            if size < position:
                position = 0
                buffers[platform] = ""

            with open(path, "rb") as file:
                file.seek(position)
                chunk = file.read()
                offsets[platform] = file.tell()
        except OSError:
            continue

        if not chunk:
            continue

        text = buffers.get(platform, "") + chunk.decode("utf-8", errors="replace")
        if text.endswith(("\n", "\r")):
            lines = text.splitlines()
            buffers[platform] = ""
        else:
            lines = text.splitlines()
            buffers[platform] = lines.pop() if lines else text

        for line in lines:
            _append_scrap_progress(_scrap_progress_message_from_log_line(platform, line))


def _start_scrap_log_tailer(offsets):
    stop_event = threading.Event()
    buffers = {}

    def tail_logs():
        while not stop_event.wait(SCRAP_PROGRESS_TAIL_INTERVAL_SECONDS):
            _collect_scrap_log_progress_once(offsets, buffers)
        _collect_scrap_log_progress_once(offsets, buffers)

    thread = threading.Thread(target=tail_logs, name="scrap-progress-log-tailer", daemon=True)
    thread.start()
    return stop_event, thread


def _normalize_scrap_progress_info(progress):
    if not progress:
        return None
    if isinstance(progress, dict):
        info = progress.copy()
    else:
        info = {"message": str(progress)}
    message = str(info.get("message") or "").strip()
    if not message:
        return None
    info["message"] = message
    return info


def _write_scrap_progress_log_event(event):
    try:
        os.makedirs(os.path.dirname(SCRAP_PROGRESS_LOG_PATH), exist_ok=True)
        with open(SCRAP_PROGRESS_LOG_PATH, "a", encoding="utf-8") as file:
            elapsed = event.get("elapsed")
            message = event.get("message")
            if elapsed:
                file.write(f"{event.get('time')} | {elapsed} | {message}\n")
            else:
                file.write(f"{event.get('time')} | {message}\n")
    except OSError:
        logging.exception("Failed to write scrap progress log")


def _append_scrap_progress(progress, level="info"):
    info = _normalize_scrap_progress_info(progress)
    if not info:
        return

    created_event = None
    with SCRAP_PROGRESS_LOCK:
        platform = info.get("platform")
        if platform and "list_new_count" in info:
            SCRAP_PROGRESS["platform_list_new_counts"][platform] = _parse_count(
                info.get("list_new_count")
            )

        if platform and "detail_target_count" in info:
            target_count = _parse_count(info.get("detail_target_count"))
            new_count = SCRAP_PROGRESS["platform_list_new_counts"].get(platform)
            if platform == "Threads" and new_count and target_count >= new_count:
                retry_count = target_count - new_count
                info["message"] = (
                    f"{platform} 상세 수집 대상 {target_count}건 "
                    f"(신규 {new_count}건 + 기존 미완료/재시도 {retry_count}건)"
                )
            else:
                info["message"] = f"{platform} 상세 수집 대상 {target_count}건"

        message = info["message"]
        if any(event.get("message") == message for event in SCRAP_PROGRESS["events"]):
            return

        SCRAP_PROGRESS["seq"] += 1
        now = _now_kst_iso()
        elapsed = _format_scrap_elapsed(SCRAP_PROGRESS.get("started_monotonic"))
        SCRAP_PROGRESS["updated_at"] = now
        created_event = {
            "seq": SCRAP_PROGRESS["seq"],
            "time": now,
            "level": level,
            "message": message,
        }
        if elapsed:
            created_event["elapsed"] = elapsed
        SCRAP_PROGRESS["events"].append(created_event)
        if len(SCRAP_PROGRESS["events"]) > SCRAP_PROGRESS_MAX_EVENTS:
            SCRAP_PROGRESS["events"] = SCRAP_PROGRESS["events"][-SCRAP_PROGRESS_MAX_EVENTS:]

    if created_event:
        _write_scrap_progress_log_event(created_event)


def _active_scrap_run(now_monotonic=None):
    """실행 중인 수집이 있으면 그 정보를, 없거나 stale 이면 None 을 준다.

    호출자는 반드시 SCRAP_PROGRESS_LOCK 을 잡은 상태여야 한다.
    검사와 상태 갱신 사이에 틈이 생기면 가드가 무의미해진다.
    """
    if not SCRAP_PROGRESS.get("running"):
        return None
    started = SCRAP_PROGRESS.get("started_monotonic")
    if started is None:
        return None
    elapsed = (now_monotonic if now_monotonic is not None else time.monotonic()) - started
    if elapsed > SCRAP_STALE_SECONDS:
        return None
    return {
        "run_id": SCRAP_PROGRESS.get("run_id", ""),
        "started_at": SCRAP_PROGRESS.get("started_at"),
        "elapsed_seconds": int(max(0, elapsed)),
    }


def _reset_scrap_progress(run_id, mode):
    """진행 상태를 새 실행으로 초기화한다.

    이미 실행 중이면 초기화하지 않고 그 실행 정보를 반환한다.
    검사와 갱신을 같은 lock 안에서 한다 - 사이에 틈이 생기면 가드가 무의미하다.
    """
    now = _now_kst_iso()
    with SCRAP_PROGRESS_LOCK:
        active = _active_scrap_run()
        if active is not None:
            return active
        SCRAP_PROGRESS.update(
            {
                "run_id": run_id,
                "running": True,
                "seq": 0,
                "events": [],
                "started_at": now,
                "started_monotonic": time.monotonic(),
                "updated_at": now,
                "platform_list_new_counts": {},
            }
        )

    label = "전체 재수집" if mode == "all" else "최근 업데이트"
    _append_scrap_progress(f"{label} 스크랩 시작")
    return None


def _finish_scrap_progress():
    with SCRAP_PROGRESS_LOCK:
        SCRAP_PROGRESS["running"] = False
        SCRAP_PROGRESS["updated_at"] = _now_kst_iso()


def _scrap_complete_message(mode, stats):
    if mode == "all":
        return (
            "전체 재수집 완료: "
            f"Threads {stats['threads_count']}건, "
            f"LinkedIn {stats['linkedin_count']}건, "
            f"X {stats['twitter_count']}건, "
            f"YouTube {stats['youtube_count']}건"
        )
    return (
        "스크랩 완료: "
        f"Threads {stats['threads']}건, "
        f"LinkedIn {stats['linkedin']}건, "
        f"X {stats['twitter']}건, "
        f"YouTube {stats['youtube']}건"
    )


def _is_local_request():
    remote_addr = request.remote_addr or ""
    try:
        return ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        return remote_addr in {"localhost"}


def _require_local_request():
    if not _is_local_request():
        abort(403)


def _auth_signal_path(session_id):
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))
    return os.path.join(AUTH_RUNTIME_DIR, f"{safe_id}.complete")


def _public_auth_job(job):
    process = job.get("process")
    return_code = process.poll() if process else job.get("return_code")
    if return_code is None:
        status = "running"
    elif job.get("completed_requested"):
        status = "completed" if return_code == 0 else "failed"
    else:
        status = "exited" if return_code == 0 else "failed"

    return {
        "session_id": job.get("session_id"),
        "platform": job.get("platform"),
        "status": status,
        "return_code": return_code,
        "started_at": job.get("started_at"),
        "completed_requested": bool(job.get("completed_requested")),
    }


def _prune_auth_jobs():
    stale_sessions = []
    now = time.time()
    for session_id, job in AUTH_JOBS.items():
        process = job.get("process")
        if process and process.poll() is not None:
            job["return_code"] = process.returncode
        if job.get("return_code") is not None and now - job.get("started_at", now) > 3600:
            stale_sessions.append(session_id)

    for session_id in stale_sessions:
        AUTH_JOBS.pop(session_id, None)


def _normalize_platform_filter(raw):
    value = str(raw or "").strip().lower()
    if value in {"", "all"}:
        return ""
    if value == "x":
        return "twitter"
    # web·file(볼트 자료)이 빠지면 "전체"로 취급돼, 흔한 검색어에서 상한(800)으로
    # 자른 뒤에야 뷰어가 거른다 - 자료가 조용히 빠진다. 뷰어의
    # getServerPlatformFilter() 와 같은 목록이다. 계획: _docs/20260911_01 (W2 T2-e, F25)
    if value not in {"threads", "linkedin", "twitter", "youtube", *LIBRARY_PLATFORMS}:
        return ""
    return value


def _build_posts_response_etag(base_etag, request_path):
    token = str(request_path or "").replace('"', "")
    return f'{base_etag[:-1]}:{token}"'


def _if_none_match_matches(etag):
    if not etag:
        return False
    return request.if_none_match.contains_weak(etag.strip('"'))


def _matches_platform_filter(post, platform_filter):
    if not platform_filter:
        return True

    platform = str(post.get("sns_platform") or "").strip().lower()
    if platform_filter == "twitter":
        return platform in {"twitter", "x"}
    return platform == platform_filter


def _sort_search_matches(posts, sort):
    sort_value = str(sort or "").strip().lower()

    if sort_value == "sequence":
        # 자료는 순번이 통합본 뒤에 붙으므로 sort_seq(수집 시각 사이 자리)로 센다.
        return sorted(
            posts,
            key=lambda post: post.get("sort_seq") or post.get("sequence_id") or 0,
            reverse=True,
        )

    return sorted(
        posts,
        key=lambda post: (
            str(post.get("created_at") or ""),
            str(post.get("date") or ""),
            post.get("sequence_id") or 0,
        ),
        reverse=(sort_value != "oldest"),
    )


_SEARCH_SEPARATOR_RE = re.compile(r"[-_]+")
_SEARCH_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_search_text(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = _SEARCH_SEPARATOR_RE.sub(" ", normalized)
    return _SEARCH_WHITESPACE_RE.sub(" ", normalized).strip()


def _split_search_terms(value):
    return [term for term in _normalize_search_text(value).split(" ") if term]


def _matches_search_query(searchable, query):
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return False
    searchable_text = str(searchable or "")
    if normalized_query in searchable_text:
        return True
    terms = _split_search_terms(query)
    return bool(terms) and all(term in searchable_text for term in terms)


def _parse_scrap_summary(lines):
    pattern = re.compile(r"SNS_SCRAP_SUMMARY\s*[:=]?\s*(\{.*\})\s*$")
    for line in reversed(lines):
        match = pattern.search(str(line or "").strip())
        if not match:
            continue
        try:
            summary = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if not isinstance(summary, dict):
            return None
        return summary
    return None


def _canonical_auth_platform(value):
    platform = str(value or "").strip().lower()
    if platform in {"threads", "thread"}:
        return "threads"
    if platform in {"linkedin", "linked_in"}:
        return "linkedin"
    if platform in {"x", "twitter", "x/twitter", "x_twitter"}:
        return "x"
    return ""


def _canonical_auth_required_platform(value):
    """인증 신호에서만 쓰는 정규화. 벤치마킹 슬롯도 같은 플랫폼으로 본다.

    🔴 `_canonical_auth_platform` 자체를 고치면 안 된다 — 그 함수는 `platform_results`
       정규화도 함께 쓰므로, 거기에 `bench_*` 매핑이 생기면 벤치마킹 결과와 저장글
       결과가 같은 키를 두고 서로 덮어써 한쪽이 조용히 사라진다.

    인증만 뭉쳐도 되는 이유: 벤치마킹과 저장글이 **같은 세션 파일 하나**를 본다.
    한쪽이 만료면 다른 쪽도 만료이므로 「LinkedIn 재로그인 필요」는 정확한 안내다.
    반면 수집 실패는 원인이 서로 달라 뭉치면 오인을 부른다 — 그래서 여기까지만이다.
    계획: _docs/20260908_02 (W3)
    """
    text = str(value or "").strip().lower()
    if text.startswith("bench_"):
        text = text[len("bench_"):]
    return _canonical_auth_platform(text)


def _normalize_scrap_summary(summary):
    if not isinstance(summary, dict):
        return {"auth_required": [], "platform_results": {}, "warnings": []}

    platform_results = {}
    for raw_platform, raw_result in (summary.get("platform_results") or {}).items():
        platform = _canonical_auth_platform(raw_platform)
        if not platform:
            continue
        if isinstance(raw_result, dict):
            platform_results[platform] = raw_result
        else:
            platform_results[platform] = {"status": str(raw_result)}

    # 여기부터가 인증 신호 경로다. total_scrap 은 벤치마킹을 `bench_linkedin` 같은
    # 슬롯 이름으로 보내므로, 이 목록만 벤치마킹을 알아보는 정규화를 쓴다.
    auth_required = []
    raw_auth_required = summary.get("auth_required")
    if isinstance(raw_auth_required, list):
        auth_required.extend(raw_auth_required)
    elif isinstance(raw_auth_required, dict):
        auth_required.extend(
            platform for platform, required in raw_auth_required.items() if required
        )
    elif isinstance(raw_auth_required, str):
        auth_required.append(raw_auth_required)

    for platform, result in platform_results.items():
        status = str(result.get("status") or result.get("result") or "").lower()
        phase_statuses = [
            str(phase_result.get("status") or phase_result.get("result") or "").lower()
            for phase_result in (result.get("phases") or {}).values()
            if isinstance(phase_result, dict)
        ]
        if result.get("auth_required") or "auth" in status or any(
            "auth" in phase_status for phase_status in phase_statuses
        ):
            auth_required.append(platform)
        if not status and phase_statuses:
            if any(phase_status == "auth_required" for phase_status in phase_statuses):
                result["status"] = "auth_required"
            elif any(phase_status == "failed" for phase_status in phase_statuses):
                result["status"] = "failed"
            elif all(phase_status == "ok" for phase_status in phase_statuses):
                result["status"] = "ok"

    normalized_auth_required = []
    seen = set()
    for raw_platform in auth_required:
        platform = _canonical_auth_required_platform(raw_platform)
        if platform and platform not in seen:
            normalized_auth_required.append(platform)
            seen.add(platform)

    # 🔴 도구 부재 경고는 플랫폼 정규화를 태우지 않는다. 그 정규화는 threads·
    #    linkedin·x 만 인정해 youtube 를 버리는데, 이 경고의 주인공이 바로 youtube 다.
    #    계획: _docs/20260909_01 (W5 T5-c)
    raw_warnings = summary.get("warnings")
    warnings = [item for item in raw_warnings if isinstance(item, dict)] if isinstance(raw_warnings, list) else []

    return {
        "auth_required": normalized_auth_required,
        "platform_results": platform_results,
        "warnings": warnings,
    }


def _is_auth_url(url):
    lowered = str(url or "").lower()
    return any(marker in lowered for marker in ("login", "signup", "challenge"))


def _find_x_auth_signal(x_result):
    if not isinstance(x_result, dict):
        return {}

    signal = x_result.get("auth_signal")
    if isinstance(signal, dict):
        return signal

    for phase in (x_result.get("phases") or {}).values():
        if not isinstance(phase, dict):
            continue
        signal = phase.get("auth_signal")
        if isinstance(signal, dict):
            return signal

    return {}


def _suppress_unreliable_x_auth_required(summary):
    auth_required = list(summary.get("auth_required") or [])
    if "x" not in auth_required:
        return summary

    platform_results = summary.get("platform_results") or {}
    x_result = platform_results.get("x") or {}
    signal = _find_x_auth_signal(x_result)
    if not signal:
        return summary

    reason = str(signal.get("reason") or "").lower()
    current_url = str(signal.get("current_url") or "")
    if not current_url:
        return summary
    if reason == "login_required" and _is_auth_url(current_url):
        return summary

    summary["auth_required"] = [platform for platform in auth_required if platform != "x"]
    x_result["status"] = "failed"
    x_result.pop("auth_required", None)
    x_result["auth_suppression"] = {
        "suppressed_auth_required": True,
        "reason": "current_url_not_auth",
        "current_url": current_url,
    }
    platform_results["x"] = x_result
    summary["platform_results"] = platform_results
    return summary


def _request_cache_token():
    full_path = str(request.full_path or "").rstrip("?")
    return full_path or (request.path or "")


def _should_apply_cached_json_headers(request_path):
    return (
        request.method == "GET"
        and (
            request_path == "/api/posts"
            or request_path.startswith("/api/post/")
            or request_path == "/api/search"
        )
    )


def _should_apply_gzip_json_headers(request_path):
    return _should_apply_cached_json_headers(request_path) or (
        request.method == "POST" and request_path == "/api/auto-tag/apply"
    )


def _merge_vary_header(response, value):
    response.vary.add(value)
    return response


def _get_latest_total_file():
    pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
    files = [
        path
        for path in glob.glob(pattern)
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    ]
    if not files:
        raise FileNotFoundError("Data file not found")
    files.sort(reverse=True)
    return files[0]


def _state_path(env_name, file_name):
    """뷰어 상태 파일 경로. 검증 전용 서버(scripts/_library_verify_server.mjs)가 운영 파일
    대신 사본을 보게 환경변수로 바꿔 끼울 수 있다 - 검증 페이지는 로드 때 자동 태그를 적용해
    태그 파일 전체를 저장하므로, 운영 파일을 같이 쓰면 표본 볼트 키가 섞인다.
    계획: _docs/20260911_02 (W2 T2-a)"""
    override = os.environ.get(env_name, "").strip()
    return os.path.abspath(override) if override else os.path.join(WEB_VIEWER_DIR, file_name)


def _get_user_metadata_path():
    return _state_path("SNS_USER_METADATA_PATH", "sns_user_metadata.json")


def _get_tags_path():
    return _state_path("SNS_TAGS_PATH", "sns_tags.json")


def _get_tag_catalog_path():
    return _state_path("SNS_TAG_CATALOG_PATH", "sns_tag_catalog.json")


def _get_file_state(path):
    if not os.path.exists(path):
        return {"path": path, "mtime": None, "size": None}
    stat = os.stat(path)
    return {"path": path, "mtime": stat.st_mtime_ns, "size": stat.st_size}


def _load_user_metadata():
    path = _get_user_metadata_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _get_user_note_for_post(post, user_metadata):
    post_key = post.get("post_key") or build_post_meta(post).get("post_key")
    if not post_key:
        return ""
    entry = user_metadata.get(post_key)
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("note") or "").strip()


def _load_latest_posts():
    latest_file = _get_latest_total_file()
    stat = os.stat(latest_file)
    mtime = stat.st_mtime_ns
    size = stat.st_size
    metadata_state = _get_file_state(_get_user_metadata_path())
    library_state = _get_library_state()
    # 레지스트리·연결 파일이 바뀌면 글마다 붙는 creator_id 가 달라진다.
    creator_state = (
        _get_file_state(_get_creators_path()),
        _get_file_state(_get_creator_links_path()),
    )

    if (
        _POSTS_CACHE["path"] == latest_file
        and _POSTS_CACHE["mtime"] == mtime
        and _POSTS_CACHE["size"] == size
        and _POSTS_CACHE.get("metadata_path") == metadata_state["path"]
        and _POSTS_CACHE.get("metadata_mtime") == metadata_state["mtime"]
        and _POSTS_CACHE.get("metadata_size") == metadata_state["size"]
        and _POSTS_CACHE.get("library_state") == library_state
        and _POSTS_CACHE.get("creator_state") == creator_state
        and _POSTS_CACHE["posts_full"] is not None
        and _POSTS_CACHE["posts_meta"] is not None
    ):
        return _POSTS_CACHE

    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    raw_posts = data.get("posts", [])
    # 볼트 자료를 합류시킨다. 통합본 파일에는 넣지 않는다 - 수집·병합(total_scrap)은
    # 이 기능과 무관하게 돈다. 볼트를 못 읽어도 SNS 목록은 그대로 나와야 한다.
    # 계획: _docs/20260911_01 (W2 T2-c)
    visible_library, overlap_library = [], []
    try:
        start_seq = max((int(post.get("sequence_id") or 0) for post in raw_posts), default=0) + 1
        visible_library, overlap_library = link_library_posts(
            build_library_posts(library_state[0]), raw_posts, start_seq
        )
    except Exception:
        logging.exception("Failed to load library notes")

    # 모든 글에 사람 단위 id 를 붙인다 - 이름 옆 아이콘이 제작자 카드를 열 근거다.
    # SNS 글은 레지스트리(볼트 프로필 채널 + 벤치마킹 계정 + 확정 연결) 키로 판정하고,
    # 자료 카드는 frontmatter creator 를 그대로 쓴다. 계획: _docs/20260911_01 (W4 T4-c)
    creators = []
    try:
        creators = apply_links(load_registry(_get_creators_path()), load_links(_get_creator_links_path()))
    except Exception:
        logging.exception("Failed to load creator registry")
    creator_index = build_creator_match_index(creators)
    for raw_post in raw_posts:
        raw_post["creator_id"] = match_creator_id(raw_post, creator_index)
    for note in [*visible_library, *overlap_library]:
        note["creator_id"] = note.get("library_creator") or None

    posts_full = []
    posts_meta = []
    user_metadata = _load_user_metadata()
    for raw_post in [*raw_posts, *visible_library]:
        meta = build_post_meta(raw_post)
        meta["canonical_url"] = meta.get("canonical_url") or canonicalize_url(raw_post)
        meta = {field: meta.get(field) for field in META_FIELDS}
        user_note = _get_user_note_for_post({**raw_post, **meta}, user_metadata)
        searchable_parts = [
            str(raw_post.get("full_text") or ""),
            str(raw_post.get("display_name") or ""),
            str(raw_post.get("username") or raw_post.get("user") or ""),
            user_note,
            # 자료 카드는 제목·주제·태그로도 찾혀야 한다(본문에 제목이 없는 노트가 있다).
            str(raw_post.get("library_title") or ""),
            str(raw_post.get("library_topic") or ""),
            " ".join(str(tag) for tag in (raw_post.get("library_tags") or [])),
        ]
        posts_full.append(
            {
                **raw_post,
                **meta,
                "_searchable": _normalize_search_text(" ".join(part for part in searchable_parts if part)),
                "_user_note": user_note,
            }
        )
        posts_meta.append(meta)

    _POSTS_CACHE["path"] = latest_file
    _POSTS_CACHE["mtime"] = mtime
    _POSTS_CACHE["size"] = size
    _POSTS_CACHE["metadata_path"] = metadata_state["path"]
    _POSTS_CACHE["metadata_mtime"] = metadata_state["mtime"]
    _POSTS_CACHE["metadata_size"] = metadata_state["size"]
    _POSTS_CACHE["posts_full"] = posts_full
    _POSTS_CACHE["posts_meta"] = posts_meta
    _POSTS_CACHE["library_state"] = library_state
    _POSTS_CACHE["creator_state"] = creator_state
    _POSTS_CACHE["creators"] = {creator["id"]: creator for creator in creators}
    _POSTS_CACHE["creator_index"] = creator_index
    _POSTS_CACHE["library_count"] = len(visible_library)
    _POSTS_CACHE["library_overlaps"] = {
        note["sequence_id"]: {**note, **build_post_meta(note)} for note in overlap_library
    }
    # 볼트 상태가 ETag 에 없으면 브라우저가 304 로 옛 목록을 계속 쓴다.
    _POSTS_CACHE["etag"] = (
        f'"{mtime}-{size}-{metadata_state["mtime"]}-{metadata_state["size"]}'
        f'-{library_state[1]}-{library_state[2]}'
        f'-{creator_state[0]["mtime"]}-{creator_state[1]["mtime"]}"'
    )
    # CLI(utils/query-sns.mjs)가 읽는 파생 파일. 볼트 상태가 바뀔 때만 다시 쓴다.
    # 검증 전용 서버(표본 볼트)가 운영 인덱스를 덮지 않게 경로를 바꿔 끼울 수 있다.
    index_path = os.environ.get("SNS_LIBRARY_INDEX_PATH", "").strip() or os.path.join(
        WEB_VIEWER_DIR, "sns_library_index.json"
    )
    if _LIBRARY_STATE.get("written_state") != (index_path, library_state) or not os.path.exists(index_path):
        try:
            write_index_file(index_path, visible_library, overlap_library, library_state[0])
            _LIBRARY_STATE["written_state"] = (index_path, library_state)
        except OSError:
            logging.exception("Failed to write library index")
    return _POSTS_CACHE

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    try:
        export_path = _get_tags_path()
        if not os.path.exists(export_path):
            return jsonify({})
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        logging.exception("Failed to get tags")
        return jsonify({"error": "Failed to load tags"}), 500

@app.route('/api/save-tags', methods=['POST'])
def save_tags():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        if not os.path.exists(WEB_VIEWER_DIR):
            os.makedirs(WEB_VIEWER_DIR)
        export_path = _get_tags_path()
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, sort_keys=True)
        return jsonify({"status": "success", "message": "Tags saved successfully"})
    except Exception as e:
        logging.exception("Failed to save tags")
        return jsonify({"status": "error", "message": "Failed to save tags"}), 500

@app.route('/api/get-tag-catalog', methods=['GET'])
def get_tag_catalog():
    try:
        export_path = _get_tag_catalog_path()
        if not os.path.exists(export_path):
            return jsonify({})
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return jsonify({})
        return jsonify(data)
    except Exception:
        logging.exception("Failed to get tag catalog")
        return jsonify({"error": "Failed to load tag catalog"}), 500

@app.route('/api/save-tag-catalog', methods=['POST'])
def save_tag_catalog():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        if not os.path.exists(WEB_VIEWER_DIR):
            os.makedirs(WEB_VIEWER_DIR)
        export_path = _get_tag_catalog_path()
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, sort_keys=True)
        return jsonify({"status": "success", "message": "Tag catalog saved successfully"})
    except Exception:
        logging.exception("Failed to save tag catalog")
        return jsonify({"status": "error", "message": "Failed to save tag catalog"}), 500


def _atomic_write_json(path, data):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False, sort_keys=True)
    os.replace(tmp_path, path)


@app.route("/api/get-user-metadata", methods=["GET"])
def get_user_metadata():
    try:
        export_path = _get_user_metadata_path()
        if not os.path.exists(export_path):
            return jsonify({})
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return jsonify({})
        return jsonify(data)
    except Exception:
        logging.exception("Failed to load user metadata")
        return jsonify({"error": "Failed to load user metadata"}), 500


def _load_env_once():
    """~/.env 를 읽어 필요한 키만 os.environ 에 채운다(값은 출력하지 않는다).

    `youtube_scrap.py:136 load_env()` 와 같은 규칙이다. 서버는 VBS 런처로 뜨는
    경우가 있어 셸 환경변수를 물려받지 못한다 - 그때 /api/verify-channel 이
    missing_api_key 로만 답한다.
    """
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


_load_env_once()


def _get_benchmark_accounts_path():
    """벤치마킹 계정 파일 경로.

    `SNS_BENCHMARK_ACCOUNTS_PATH` 가 있으면 그것을 쓴다. 검증 스크립트가
    운영 파일을 건드리지 않게 하는 유일한 통로다 - 종전에는 검증이 API 로
    운영 파일을 바꾼 뒤 `finally` 에서 되돌렸고, 그 되돌리기가 실패하면
    계정이 꺼진 채 굳었다. 되돌릴 것을 만들지 않는 편이 낫다.
    계획: _docs/20260906_03 (W2)
    """
    override = os.environ.get("SNS_BENCHMARK_ACCOUNTS_PATH", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(WEB_VIEWER_DIR, "benchmark_accounts.json")


BENCHMARK_STATUSES = {"active", "off", "excluded"}


@app.route("/api/get-benchmark-accounts", methods=["GET"])
def get_benchmark_accounts():
    """벤치마킹 계정 목록. 파일이 없어도 200 과 빈 목록을 준다.

    동기화 스크립트를 한 번도 안 돌린 상태에서도 뷰어가 정상 동작해야 한다.
    계획: _docs/20260906_01 (P1)
    """
    empty = {"accounts": []}
    try:
        export_path = _get_benchmark_accounts_path()
        if not os.path.exists(export_path):
            return jsonify(empty)
        with open(export_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
            return jsonify(empty)
        return jsonify(data)
    except Exception:
        logging.exception("Failed to load benchmark accounts")
        return jsonify({"error": "Failed to load benchmark accounts"}), 500


@app.route("/api/save-benchmark-accounts", methods=["POST"])
def save_benchmark_accounts():
    """화면에서 편집한 계정 목록을 파일로 저장한다.

    status 값을 서버에서 검증한다. 오타가 들어가면 뷰어의
    `보임 = is_saved OR (benchmark_accounts 중 status=="active")` 가 조용히
    거짓이 되어 글이 사라진다 - 조용한 실패라 발견이 늦다.
    """
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        accounts = data.get("accounts")
        if not isinstance(accounts, list):
            return jsonify({"status": "error", "message": "accounts must be a list"}), 400

        seen_ids = set()
        for index, account in enumerate(accounts):
            if not isinstance(account, dict):
                return jsonify({"status": "error", "message": f"accounts[{index}] must be an object"}), 400
            account_id = str(account.get("id") or "").strip()
            if not account_id:
                return jsonify({"status": "error", "message": f"accounts[{index}].id is required"}), 400
            if account_id in seen_ids:
                return jsonify({"status": "error", "message": f"duplicate account id: {account_id}"}), 400
            seen_ids.add(account_id)
            status = str(account.get("status") or "")
            if status not in BENCHMARK_STATUSES:
                return jsonify({
                    "status": "error",
                    "message": f"accounts[{index}].status must be one of {sorted(BENCHMARK_STATUSES)}",
                }), 400

        _atomic_write_json(_get_benchmark_accounts_path(), data)
        return jsonify({"status": "success", "message": "Benchmark accounts saved successfully"})
    except Exception:
        logging.exception("Failed to save benchmark accounts")
        return jsonify({"status": "error", "message": "Failed to save benchmark accounts"}), 500


CREATOR_PROFILE_DIR = os.path.join(
    os.path.expanduser("~"), "cowork", "90_자료수집", "_제작자별_상세"
)
# 옵시디언 vault 루트. `.obsidian` 이 여기 있다 - vault 등록명이 폴더명과 다를 수
# 있어 `obsidian://open?vault=` 대신 `?path=` 를 쓴다.
OBSIDIAN_VAULT_ROOT = os.path.join(os.path.expanduser("~"), "cowork")


def _creator_profile_path(account):
    """계정에 대응하는 제작자 `.md` 절대경로. 없으면 None.

    파일명·별칭으로 찾는다. 벤치마킹 계정의 `name` 은 사람 이름이고 제작자 파일은
    `이승필_사용성연구소.md` 처럼 수식이 붙는 경우가 있어 부분 일치를 쓴다 -
    `sync_benchmark_accounts.profile_channels_for()` 와 같은 규칙이다.
    """
    if not os.path.isdir(CREATOR_PROFILE_DIR):
        return None

    needles = [str(account.get("name") or "").strip()]
    needles += [str(a).strip() for a in (account.get("aliases") or [])]
    needles = [n.lower() for n in needles if n]
    if not needles:
        return None

    for entry in sorted(os.listdir(CREATOR_PROFILE_DIR)):
        if not entry.endswith(".md"):
            continue
        stem = os.path.splitext(entry)[0].lower()
        if any(needle in stem for needle in needles):
            return os.path.join(CREATOR_PROFILE_DIR, entry)
    return None


def _parse_creator_profile(path):
    """제작자 md 에서 프론트매터 채널·별칭·전문분야와 `## 프로필` 본문을 뽑는다."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        text = handle.read(20000)

    front = ""
    if text.startswith("---") and text.count("---") >= 2:
        front = text.split("---", 2)[1]

    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    channels = {}
    for platform in ("threads", "youtube", "linkedin", "x", "blog", "service", "newsletter", "instagram"):
        match = re.search(rf"^{platform}:\s*(.+)$", front, re.MULTILINE)
        if not match:
            continue
        raw = match.group(1).strip().strip('"').strip("'")
        link = link_re.search(raw)
        channels[platform] = link.group(2) if link else raw

    def _list_field(name):
        head = re.search(rf"^{name}:\s*$", front, re.MULTILINE)
        if not head:
            return []
        items = []
        for line in front[head.end():].split("\n"):
            if not line.strip():
                continue
            if not line.startswith((" ", "\t")):
                break
            item = re.match(r"^\s*-\s+(.*)$", line)
            if item:
                value = item.group(1).strip().strip('"').strip("'")
                if value:
                    items.append(value)
        return items

    body = ""
    section = re.search(r"^##\s*프로필\s*$(.*?)^##\s", text, re.MULTILINE | re.DOTALL)
    if section:
        body = section.group(1).strip()

    return {
        "channels": channels,
        "aliases": _list_field("aliases"),
        "expertise": _list_field("expertise"),
        "profile_text": body,
    }


@app.route("/api/creator-profile", methods=["GET"])
def creator_profile():
    """벤치마킹 계정 하나의 제작자 프로필. 읽기 전용이다.

    뷰어의 제작자 카드가 쓴다. 파일이 없으면 404 가 아니라 200 + `found:false` 를
    준다 - 프로필 문서가 없는 계정도 카드의 나머지(채널·글 건수)는 보여야 한다.

    🔴 vault 밖 파일을 읽지 않는다. 경로는 `account_id` 로 **간접 조회**하며
    클라이언트가 준 문자열을 경로로 쓰지 않는다. 그래도 `os.path.realpath` 로
    한 번 더 가둔다 - 제작자 파일이 심볼릭 링크인 경우를 막는다.
    계획: _docs/20260910_01 (W3 T3-a)

    `creator_id` 경로(계획 _docs/20260911_01 W4 T4-d)는 벤치마킹 계정이 아닌 제작자도
    받는다. 기존 `account_id` 경로는 그대로다.
    """
    creator_id = request.args.get("creator_id")
    if creator_id is not None:
        return _creator_profile_by_creator_id(creator_id.strip())

    account_id = (request.args.get("account_id") or "").strip()
    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    try:
        path = _get_benchmark_accounts_path()
        if not os.path.exists(path):
            return jsonify({"found": False, "reason": "no_accounts_file"})
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        accounts = data.get("accounts", []) if isinstance(data, dict) else []
        account = next(
            (a for a in accounts if isinstance(a, dict) and a.get("id") == account_id),
            None,
        )
        if not account:
            return jsonify({"found": False, "reason": "unknown_account"})

        profile_path = _creator_profile_path(account)
        if not profile_path:
            return jsonify({"found": False, "reason": "no_profile_file"})

        # 화이트리스트 밖이면 읽지 않는다.
        resolved = os.path.realpath(profile_path)
        allowed_root = os.path.realpath(CREATOR_PROFILE_DIR)
        if os.path.commonpath([resolved, allowed_root]) != allowed_root:
            logging.warning("creator profile outside vault: %s", resolved)
            return jsonify({"found": False, "reason": "outside_vault"}), 403

        parsed = _parse_creator_profile(resolved)
        relative = os.path.relpath(resolved, os.path.realpath(OBSIDIAN_VAULT_ROOT))
        return jsonify(
            {
                "found": True,
                "account_id": account_id,
                "file_name": os.path.basename(resolved),
                "vault_relative_path": relative.replace("\\", "/"),
                "obsidian_url": "obsidian://open?path="
                + urllib.parse.quote(resolved.replace("\\", "/"), safe=""),
                **parsed,
            }
        )
    except Exception:
        logging.exception("Failed to load creator profile")
        return jsonify({"error": "Failed to load creator profile"}), 500


def _creator_profile_by_creator_id(creator_id):
    """제작자 id(볼트 프로필 파일명) 하나의 프로필 + 레지스트리 정보.

    🔴 경로를 조립하지 않는다. 프로필 폴더의 **파일 목록에 정확히 있는 이름**만
    연다 - `../` 같은 값은 목록에 있을 수 없다. 모양부터 틀리면 400 이다.
    realpath 가드도 기존 account_id 경로와 같게 유지한다.
    """
    if not is_safe_creator_id(creator_id):
        return jsonify({"error": "invalid creator_id"}), 400
    try:
        cache = _load_latest_posts()
        creator = (cache.get("creators") or {}).get(creator_id) or {}
        base = {
            "creator_id": creator_id,
            "name": creator.get("name") or creator_id,
            "in_registry": bool(creator),
            "registry_channels": creator.get("channels") or {},
            "benchmark_account": creator.get("benchmark_account"),
            "linked_accounts": creator.get("linked_accounts") or [],
        }
        listing = os.listdir(CREATOR_PROFILE_DIR) if os.path.isdir(CREATOR_PROFILE_DIR) else []
        file_name = f"{creator_id}.md"
        if file_name not in listing:
            return jsonify({"found": False, "reason": "no_profile_file", **base})

        resolved = os.path.realpath(os.path.join(CREATOR_PROFILE_DIR, file_name))
        allowed_root = os.path.realpath(CREATOR_PROFILE_DIR)
        if os.path.commonpath([resolved, allowed_root]) != allowed_root:
            logging.warning("creator profile outside vault: %s", resolved)
            return jsonify({"found": False, "reason": "outside_vault"}), 403

        parsed = _parse_creator_profile(resolved)
        try:
            relative = os.path.relpath(resolved, os.path.realpath(OBSIDIAN_VAULT_ROOT))
        except ValueError:
            # 표본 볼트처럼 드라이브가 다르면 상대경로를 만들 수 없다.
            relative = os.path.basename(resolved)
        return jsonify(
            {
                "found": True,
                **base,
                "file_name": os.path.basename(resolved),
                "vault_relative_path": relative.replace("\\", "/"),
                "obsidian_url": "obsidian://open?path="
                + urllib.parse.quote(resolved.replace("\\", "/"), safe=""),
                **parsed,
            }
        )
    except Exception:
        logging.exception("Failed to load creator profile by creator_id")
        return jsonify({"error": "Failed to load creator profile"}), 500


@app.route("/api/save-creator-links", methods=["POST"])
def save_creator_links():
    """뷰어 「다른 계정 연결」로 확정한 계정 연결을 저장한다.

    이름·본문 링크로 찾은 후보는 여기 오지 않는다 - 사용자가 고른 것(`source: user`)과
    본인이 게시한 링크(`self_declared`, W5)만 확정 연결이다(F23 동명이인 실측).
    이미 다른 제작자에 속한 계정은 409 로 거절한다 - 판정 인덱스는 먼저 온 쪽이
    이기므로, 받아도 효과가 없고 사용자는 "연결했는데 왜 안 합쳐지지"가 된다.
    원자적 쓰기(임시 파일 → 교체). 계획: _docs/20260911_01 (W4 T4-b)
    """
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"status": "error", "message": "No data received"}), 400
        link_request, error = validate_link_request(payload)
        if not link_request:
            return jsonify({"status": "error", "message": error}), 400

        cache = _load_latest_posts()
        index = cache.get("creator_index") or {}
        for account in link_request["accounts"]:
            owner = index.get((account["platform"], normalize_key(account["key"])))
            if owner and owner != link_request["creator_id"]:
                return jsonify(
                    {"status": "error", "message": "이미 다른 제작자에 연결된 계정이다", "creator_id": owner}
                ), 409

        path = _get_creator_links_path()
        links, added = merge_link_request(load_links(path), link_request)
        _atomic_write_json(path, {"links": links})
        return jsonify({"status": "success", "creator_id": link_request["creator_id"], "added": added})
    except Exception:
        logging.exception("Failed to save creator links")
        return jsonify({"status": "error", "message": "Failed to save creator links"}), 500


@app.route("/api/verify-channel", methods=["GET"])
def verify_channel():
    """계정 주소가 실제로 열리는지 서버가 대신 확인한다.

    브라우저에서 직접 못 한다 - YOUTUBE_API_KEY 는 ~/.env 에 있고 프런트로
    내보내면 안 된다. 응답에는 조회 결과만 싣는다(키·원본 응답 금지).

    오타를 입력 시점에 잡는 것이 목적이다. 사후에는 수집 0건의 원인을 알 수 없다.
    계획: _docs/20260906_01 (P1, P4 / SPEC D3)
    """
    platform = (request.args.get("platform") or "").strip().lower()
    handle = (request.args.get("handle") or "").strip()

    if not handle:
        return jsonify({"ok": False, "reason": "handle is required"}), 400
    if platform != "youtube":
        # 계정 단위 확인이 되는 것은 지금 YouTube 뿐이다. 나머지는 "확인 불가"를
        # 정직하게 돌려준다 - 임의로 통과시키면 쓰레기 주소가 목록에 남는다.
        return jsonify({
            "ok": False,
            "reason": "unsupported_platform",
            "message": f"{platform or '(빈 값)'} 은 아직 자동 확인을 지원하지 않는다",
        }), 200

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "reason": "missing_api_key"}), 503

    normalized = handle if handle.startswith("@") else f"@{handle}"
    try:
        params = urllib.parse.urlencode({
            "part": "snippet,statistics",
            "forHandle": normalized,
            "key": api_key,
        })
        url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logging.exception("Failed to verify youtube channel")
        return jsonify({"ok": False, "reason": "lookup_failed"}), 502

    items = payload.get("items") or []
    if not items:
        return jsonify({"ok": False, "reason": "not_found", "handle": normalized}), 200

    item = items[0]
    snippet = item.get("snippet") or {}
    statistics = item.get("statistics") or {}
    return jsonify({
        "ok": True,
        "platform": "youtube",
        "handle": normalized,
        "channel_id": item.get("id") or "",
        "title": snippet.get("title") or "",
        "subscriber_count": statistics.get("subscriberCount"),
        "video_count": statistics.get("videoCount"),
    })


@app.route("/api/get-external-summaries", methods=["GET"])
def get_external_summaries():
    """Lilys/LiveWiki 외부 요약 링크 매핑.

    쓰기 짝(/api/save-*)이 없다. 이 파일은 사용자 상태가 아니라
    scripts/build_external_summaries.mjs 가 만드는 파생 데이터다.
    파일이 없어도 200 과 빈 items 를 준다 - 수집기를 한 번도 안 돌린 상태에서도
    뷰어가 정상 동작해야 한다.
    """
    empty = {"items": {}}
    try:
        export_path = os.path.join(WEB_VIEWER_DIR, "sns_external_summaries.json")
        if not os.path.exists(export_path):
            return jsonify(empty)
        with open(export_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
            return jsonify(empty)
        return jsonify(data)
    except Exception:
        logging.exception("Failed to load external summaries")
        return jsonify({"error": "Failed to load external summaries"}), 500


@app.route("/api/save-user-metadata", methods=["POST"])
def save_user_metadata():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        export_path = _get_user_metadata_path()
        _atomic_write_json(export_path, data)
        return jsonify({"status": "success", "message": "User metadata saved successfully"})
    except Exception:
        logging.exception("Failed to save user metadata")
        return jsonify({"status": "error", "message": "Failed to save user metadata"}), 500

@app.route('/api/latest-data', methods=['GET'])
def get_latest_data():
    try:
        latest_file = _get_latest_total_file()
        # Some files might have BOM
        with open(latest_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404
    except Exception as e:
        logging.exception("Failed to load latest data")
        return jsonify({"error": "Failed to load data"}), 500


def _read_latest_metadata():
    """최신 total_full_*.json의 metadata를 읽는다. 파일이 없으면 None."""
    payload = _read_latest_total_payload()
    return payload.get("metadata") if payload else None


def _read_latest_total_payload():
    """최신 total_full_*.json의 핵심 데이터를 읽는다. 파일이 없으면 None."""
    try:
        latest_file = _get_latest_total_file()
    except FileNotFoundError:
        return None
    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    return {
        "path": latest_file,
        "metadata": data.get("metadata") or {},
        "posts": data.get("posts") or [],
    }


def _consistency_platform(value):
    platform = str(value or "").strip().lower()
    if platform in {"threads", "thread"}:
        return "threads"
    if platform in {"linkedin", "linked_in"}:
        return "linkedin"
    if platform in {"x", "twitter", "x/twitter", "x_twitter"}:
        return "twitter"
    if platform == "youtube":
        return "youtube"
    return platform


def _consistency_post_key(post):
    platform = _consistency_platform(post.get("sns_platform"))
    post_id = str(post.get("platform_id") or post.get("code") or "").strip()
    if platform and post_id:
        return f"{platform}:id:{post_id}"

    post_url = (
        post.get("canonical_url")
        or canonicalize_url(post)
        or post.get("url")
        or post.get("post_url")
        or post.get("source_url")
        or ""
    )
    post_url = str(post_url).strip()
    if platform and post_url:
        return f"{platform}:url:{post_url}"
    return ""


def _consistency_sample(post):
    return {
        "sequence_id": post.get("sequence_id"),
        "platform_id": post.get("platform_id") or post.get("code"),
        "sns_platform": _consistency_platform(post.get("sns_platform")),
        "url": post.get("canonical_url") or canonicalize_url(post) or post.get("url"),
        "display_name": post.get("display_name") or post.get("username") or post.get("user"),
    }


def _build_consistency_probe(before_posts=None):
    """수집 후 프런트가 서버/화면 정합성을 확인할 때 사용할 기준값."""
    cache = _load_latest_posts()
    # 수집 정합성은 통합본 기준이다. 볼트 자료는 순번이 가장 커서 빼지 않으면
    # probe 가 자료 카드를 고른다.
    posts = [
        post for post in (cache.get("posts_full") or [])
        if post.get("sns_platform") not in LIBRARY_PLATFORMS
    ]
    metadata = {}

    if cache.get("path"):
        with open(cache["path"], 'r', encoding='utf-8-sig') as f:
            metadata = (json.load(f).get("metadata") or {})

    total_count = int(metadata.get("total_count") or len(posts))
    platform_counts = {
        "threads": int(metadata.get("threads_count") or 0),
        "linkedin": int(metadata.get("linkedin_count") or 0),
        "twitter": int(metadata.get("twitter_count") or 0),
        "youtube": int(metadata.get("youtube_count") or 0),
    }
    if not any(platform_counts.values()):
        for post in posts:
            platform = str(post.get("sns_platform") or "").lower()
            if platform in {"threads", "linkedin", "youtube"}:
                platform_counts[platform] += 1
            elif platform in {"twitter", "x"}:
                platform_counts["twitter"] += 1

    before_keys = {
        key
        for key in (_consistency_post_key(post) for post in (before_posts or []))
        if key
    }
    new_posts_by_platform = {"threads": [], "linkedin": [], "twitter": [], "youtube": []}
    for post in posts:
        key = _consistency_post_key(post)
        platform = _consistency_platform(post.get("sns_platform"))
        if not key or key in before_keys or platform not in new_posts_by_platform:
            continue
        new_posts_by_platform[platform].append(post)

    for platform_posts in new_posts_by_platform.values():
        platform_posts.sort(key=lambda post: post.get("sequence_id") or 0, reverse=True)

    new_counts = {
        platform: len(platform_posts)
        for platform, platform_posts in new_posts_by_platform.items()
    }
    new_samples = {
        platform: [_consistency_sample(post) for post in platform_posts[:3]]
        for platform, platform_posts in new_posts_by_platform.items()
    }

    probe_post = None
    if posts:
        probe_post = max(posts, key=lambda post: post.get("sequence_id") or 0)

    probe = None
    if probe_post:
        full_text = str(probe_post.get("full_text") or probe_post.get("full_text_preview") or "").strip()
        search_query = " ".join(full_text.split())[:80]
        probe = {
            "sequence_id": probe_post.get("sequence_id"),
            "platform_id": probe_post.get("platform_id") or probe_post.get("code"),
            "sns_platform": probe_post.get("sns_platform"),
            "url": probe_post.get("canonical_url") or probe_post.get("url"),
            "display_name": probe_post.get("display_name") or probe_post.get("username"),
            "search_query": search_query,
        }

    source_path = cache.get("path") or ""
    try:
        source_file = os.path.relpath(source_path, PROJECT_ROOT) if source_path else ""
    except ValueError:
        source_file = os.path.basename(source_path)

    return {
        "source_file": source_file,
        "updated_at": metadata.get("updated_at") or metadata.get("generated_at"),
        "total_count": total_count,
        "platform_counts": platform_counts,
        "new_counts": new_counts,
        "new_samples": new_samples,
        "probe": probe,
    }


ALLOWED_SCRAP_MODES = {'update', 'all'}

@app.route('/api/run-scrap', methods=['POST'])
def run_scrap():
    progress_started = False
    try:
        script_path = os.path.join(PROJECT_ROOT, 'total_scrap.py')
        if not os.path.exists(script_path):
            return jsonify({"status": "error", "message": "Script not found"}), 404
        data = request.json or {}
        mode = data.get('mode', 'update')
        if mode not in ALLOWED_SCRAP_MODES:
            return jsonify({"status": "error", "message": f"Invalid mode. Allowed: {', '.join(sorted(ALLOWED_SCRAP_MODES))}"}), 400
        run_id = _normalize_scrap_run_id(data.get("run_id"))
        # 중복 실행 가드. 프런트에도 가드가 있지만 탭 단위 JS 변수라
        # 두 번째 탭, 실행 중 새로고침, 직접 API 호출은 통과한다.
        # 두 벌이 돌면 같은 날짜 output JSON 과 통합본을 동시에 써서 데이터가 섞인다.
        active = _reset_scrap_progress(run_id, mode)
        if active is not None:
            return jsonify({
                "status": "error",
                "message": "이미 스크랩이 실행 중입니다.",
                "running_run_id": active["run_id"],
                "started_at": active["started_at"],
                "elapsed_seconds": active["elapsed_seconds"],
            }), 409
        progress_started = True
        before_payload = _read_latest_total_payload()
        before_meta = (before_payload or {}).get("metadata")
        before_counts = {
            'total': (before_meta or {}).get('total_count', 0),
            'threads': (before_meta or {}).get('threads_count', 0),
            'linkedin': (before_meta or {}).get('linkedin_count', 0),
            'twitter': (before_meta or {}).get('twitter_count', 0),
            'youtube': (before_meta or {}).get('youtube_count', 0),
        }
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        log_offsets = _snapshot_scrap_log_offsets()
        tailer_stop = None
        tailer_thread = None
        process = subprocess.Popen(
            [sys.executable, "-u", script_path, "--mode", mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
        tailer_stop, tailer_thread = _start_scrap_log_tailer(log_offsets)
        full_output = []
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    full_output.append(line)
                    _append_scrap_progress(_scrap_progress_message_from_line(line))
            process.wait()
        finally:
            if tailer_stop:
                tailer_stop.set()
            if tailer_thread:
                tailer_thread.join(timeout=2)
        stdout_val = "".join(full_output[-20:])
        after_meta = _read_latest_metadata()
        after_counts = {
            'total': (after_meta or {}).get('total_count', 0),
            'threads': (after_meta or {}).get('threads_count', 0),
            'linkedin': (after_meta or {}).get('linkedin_count', 0),
            'twitter': (after_meta or {}).get('twitter_count', 0),
            'youtube': (after_meta or {}).get('youtube_count', 0),
        }
        stats = {
            'total': after_counts['total'] - before_counts['total'],
            'threads': after_counts['threads'] - before_counts['threads'],
            'linkedin': after_counts['linkedin'] - before_counts['linkedin'],
            'twitter': after_counts['twitter'] - before_counts['twitter'],
            'youtube': after_counts['youtube'] - before_counts['youtube'],
            'total_count': after_counts['total'],
            'threads_count': after_counts['threads'],
            'linkedin_count': after_counts['linkedin'],
            'twitter_count': after_counts['twitter'],
            'youtube_count': after_counts['youtube'],
        }
        summary = _normalize_scrap_summary(_parse_scrap_summary(full_output))
        summary = _suppress_unreliable_x_auth_required(summary)
        consistency_probe = _build_consistency_probe((before_payload or {}).get("posts") or [])
        _append_scrap_progress(_scrap_complete_message(mode, stats))
        _finish_scrap_progress()
        return jsonify({
            "status": "success",
            "message": "Scraping finished",
            "run_id": run_id,
            "output": stdout_val,
            "stats": stats,
            "consistency_probe": consistency_probe,
            "auth_required": summary["auth_required"],
            "platform_results": summary["platform_results"],
            # 자막 도구처럼 「수집은 됐는데 일부가 조용히 빈」 경우를 결과창까지 올린다.
            # 계획: _docs/20260909_01 (W5)
            "warnings": summary.get("warnings") or [],
        })
    except Exception as e:
        if progress_started:
            _append_scrap_progress("스크랩 실패", level="error")
            _finish_scrap_progress()
        logging.exception("Failed to run scraping")
        return jsonify({"status": "error", "message": "Scraping failed"}), 500


@app.route('/api/scrap-progress', methods=['GET'])
def get_scrap_progress():
    _require_local_request()
    requested_run_id = str(request.args.get("run_id") or "").strip()
    try:
        after = int(request.args.get("after", 0) or 0)
    except (TypeError, ValueError):
        after = 0

    with SCRAP_PROGRESS_LOCK:
        current_run_id = SCRAP_PROGRESS["run_id"]
        if requested_run_id and requested_run_id != current_run_id:
            return jsonify(
                {
                    "run_id": requested_run_id,
                    "running": False,
                    "seq": 0,
                    "events": [],
                    "started_at": None,
                    "updated_at": None,
                }
            )

        events = [
            event
            for event in SCRAP_PROGRESS["events"]
            if int(event.get("seq") or 0) > after
        ]
        return jsonify(
            {
                "run_id": current_run_id,
                "running": bool(SCRAP_PROGRESS["running"]),
                "seq": SCRAP_PROGRESS["seq"],
                "events": events,
                "started_at": SCRAP_PROGRESS["started_at"],
                "updated_at": SCRAP_PROGRESS["updated_at"],
            }
        )


@app.route('/api/auth/start', methods=['POST'])
def start_auth():
    _require_local_request()
    payload = request.get_json(silent=True) or {}
    platform = str(payload.get("platform") or "").strip().lower()
    if platform not in ALLOWED_AUTH_PLATFORMS:
        return jsonify({"status": "error", "message": "Invalid platform"}), 400
    if not os.path.exists(AUTH_RENEW_SCRIPT):
        return jsonify({"status": "error", "message": "Renew script not found"}), 404

    with AUTH_JOBS_LOCK:
        _prune_auth_jobs()
        for job in AUTH_JOBS.values():
            process = job.get("process")
            if job.get("platform") == platform and process and process.poll() is None:
                return jsonify({
                    "status": "error",
                    "message": "Auth renewal already running",
                    "job": _public_auth_job(job),
                }), 409

        os.makedirs(AUTH_RUNTIME_DIR, exist_ok=True)
        session_id = secrets.token_urlsafe(12)
        signal_path = _auth_signal_path(session_id)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                AUTH_RENEW_SCRIPT,
                "--web",
                "--session-id",
                session_id,
                "--signal-dir",
                AUTH_RUNTIME_DIR,
                platform,
            ],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        job = {
            "session_id": session_id,
            "platform": platform,
            "process": process,
            "started_at": time.time(),
            "completed_requested": False,
            "signal_path": signal_path,
            "return_code": None,
        }
        AUTH_JOBS[session_id] = job

    return jsonify({"status": "started", "job": _public_auth_job(job)})


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    _require_local_request()
    session_id = str(request.args.get("session_id") or "").strip()
    platform = str(request.args.get("platform") or "").strip().lower()
    if platform and platform not in ALLOWED_AUTH_PLATFORMS:
        return jsonify({"status": "error", "message": "Invalid platform"}), 400

    with AUTH_JOBS_LOCK:
        _prune_auth_jobs()
        if session_id:
            job = AUTH_JOBS.get(session_id)
            if not job:
                return jsonify({"status": "not_found"}), 404
            return jsonify({"status": "ok", "job": _public_auth_job(job)})

        jobs = [
            _public_auth_job(job)
            for job in AUTH_JOBS.values()
            if not platform or job.get("platform") == platform
        ]

    return jsonify({"status": "ok", "jobs": jobs})


@app.route('/api/auth/complete', methods=['POST'])
def complete_auth():
    _require_local_request()
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "").strip()
    platform = str(payload.get("platform") or "").strip().lower()
    if platform and platform not in ALLOWED_AUTH_PLATFORMS:
        return jsonify({"status": "error", "message": "Invalid platform"}), 400

    with AUTH_JOBS_LOCK:
        _prune_auth_jobs()
        job = AUTH_JOBS.get(session_id) if session_id else None
        if not job and platform:
            for candidate in AUTH_JOBS.values():
                process = candidate.get("process")
                if candidate.get("platform") == platform and process and process.poll() is None:
                    job = candidate
                    break
        if not job:
            return jsonify({"status": "not_found"}), 404
        process = job.get("process")
        if not process or process.poll() is not None:
            job["return_code"] = process.returncode if process else job.get("return_code")
            return jsonify({"status": "error", "message": "Auth renewal is not running", "job": _public_auth_job(job)}), 409

        with open(job["signal_path"], "w", encoding="utf-8") as file:
            json.dump({"complete": True, "at": time.time()}, file)
        job["completed_requested"] = True

    return jsonify({"status": "complete_requested", "job": _public_auth_job(job)})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})


@app.route('/api/posts', methods=['GET'])
def get_posts():
    try:
        cache = _load_latest_posts()
        sorted_posts = _sort_search_matches(cache["posts_full"], request.args.get("sort"))
        return jsonify({"posts": [build_post_meta(post) for post in sorted_posts]})
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404
    except Exception:
        logging.exception("Failed to load posts")
        return jsonify({"error": "Failed to load posts"}), 500


@app.route('/api/post/<int:sequence_id>', methods=['GET'])
def get_post_detail(sequence_id):
    try:
        cache = _load_latest_posts()
        # 겹침 자료(원문 SNS 카드가 이미 있는 요약본)는 목록에 없고 여기서만 열린다.
        found = next(
            (post for post in cache["posts_full"] if post.get("sequence_id") == sequence_id),
            None,
        ) or (cache.get("library_overlaps") or {}).get(sequence_id)
        if found:
            return jsonify(
                {
                    key: value
                    for key, value in found.items()
                    if key not in {"_searchable", "_user_note"}
                }
            )
        return jsonify({"error": "Post not found"}), 404
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404
    except Exception:
        logging.exception("Failed to load post detail")
        return jsonify({"error": "Failed to load post"}), 500


@app.route('/api/search', methods=['GET'])
def search_posts():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "q is required"}), 400

    platform = _normalize_platform_filter(request.args.get("platform"))

    # 기본 상한 500 → 800. 벤치마킹 포함이 검색 기본이 되면서 흔한 검색어에서
    # 내 저장글이 상한 밖으로 밀렸다 - 실측(2026-09-09) "AI" 492 → 370건(-24.8%).
    # 계획이 미리 정한 기준(-5% 이하면 상향)에 걸렸다. 하드 상한 1000 은 그대로다.
    # 계획: _docs/20260909_01 (W3-4, 위험 7)
    try:
        limit = int(request.args.get("limit", 800))
    except (TypeError, ValueError):
        limit = 800
    limit = max(1, min(limit, 1000))

    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    # 벤치마킹 글을 **자르기 전에** 거른다. limit(기본 500)로 자른 뒤 클라이언트가
    # 거르면, 벤치마킹을 꺼둔 사용자에게 내 저장글이 예전보다 덜 나온다.
    # 절단은 이미 지금도 일어난다 - 실측(2026-09-06): "AI" 1,921건 · "claude" 813건.
    # 계획: _docs/20260906_01 (M2)
    include_benchmark = str(request.args.get("include_benchmark") or "").lower() in {
        "1", "true", "yes",
    }

    try:
        cache = _load_latest_posts()
        matched_posts = []
        for post in cache["posts_full"]:
            if not _matches_platform_filter(post, platform):
                continue
            if not include_benchmark and post.get("is_saved") is False:
                continue
            if _matches_search_query(post.get("_searchable"), q):
                matched_posts.append(post)

        matches = [build_post_meta(post) for post in _sort_search_matches(matched_posts, request.args.get("sort"))]

        sliced = matches[offset:offset + limit]
        return jsonify(
            {
                "posts": sliced,
                "query": q,
                "total_matched": len(matches),
                "returned": len(sliced),
                "limit": limit,
                "offset": offset,
            }
        )
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404
    except Exception:
        logging.exception("Failed to search posts")
        return jsonify({"error": "Failed to search posts"}), 500


@app.route('/api/auto-tag/apply', methods=['POST'])
def apply_auto_tags():
    payload = request.get_json(silent=True) or {}
    rules = payload.get("rules")
    if not isinstance(rules, list):
        return jsonify({"error": "rules is required"}), 400

    try:
        cache = _load_latest_posts()
        url_to_auto_tags = {}

        # 규칙 정본은 utils/auto_tag.py 다 - 자료 카드는 제목 + 앞 800자만 훑고 볼트 주제·
        # 노트 태그를 더한다. 정리 스크립트가 같은 함수를 쓴다. 계획: _docs/20260911_02 (W3 T3-b)
        for post in cache["posts_full"]:
            matched_tags = match_auto_tags(post, rules)
            if matched_tags:
                url_to_auto_tags[post["canonical_url"]] = matched_tags

        return jsonify(
            {
                "url_to_auto_tags": url_to_auto_tags,
                "matched_post_count": len(url_to_auto_tags),
                "rule_count": len(rules),
            }
        )
    except FileNotFoundError:
        return jsonify({"error": "Data file not found"}), 404
    except Exception:
        logging.exception("Failed to apply auto tags")
        return jsonify({"error": "Failed to apply auto tags"}), 500


@app.after_request
def add_json_response_headers(response):
    if not response.is_json:
        return response

    if response.status_code != 200:
        return response

    request_path = request.path or ""
    if not _should_apply_gzip_json_headers(request_path):
        return response

    if request.headers.get("Origin"):
        _merge_vary_header(response, "Origin")
    _merge_vary_header(response, "Accept-Encoding")

    if _should_apply_cached_json_headers(request_path):
        try:
            cache = _load_latest_posts()
            etag = cache.get("etag")
        except FileNotFoundError:
            return response
        except Exception:
            logging.exception("Failed to load posts cache for response headers")
            return response

        if not etag:
            return response

        response_etag = _build_posts_response_etag(etag, _request_cache_token())
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        response.headers["ETag"] = response_etag

        if _if_none_match_matches(response_etag):
            response.set_data(b"")
            response.status_code = 304
            return response

    accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "").lower()
    if accepts_gzip and len(response.get_data()) >= 512:
        response.set_data(gzip.compress(response.get_data()))
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(response.get_data()))

    return response


def _send_root_index():
    return send_from_directory(PROJECT_ROOT, 'index.html')


def _send_web_viewer_asset(path):
    rel_path = path[len('web_viewer/'):]
    requested = os.path.realpath(os.path.join(WEB_VIEWER_DIR, rel_path))
    web_viewer_real = os.path.realpath(WEB_VIEWER_DIR)

    if not requested.startswith(web_viewer_real + os.sep) and requested != web_viewer_real:
        abort(403)

    if os.path.exists(requested) and os.path.isfile(requested):
        return send_from_directory(WEB_VIEWER_DIR, rel_path)

    abort(404)


def _has_path_traversal(path):
    normalized = path.replace('\\', '/')
    return any(part == '..' for part in normalized.split('/'))


@app.route('/')
def index():
    if os.path.exists(INDEX_HTML_PATH):
        return _send_root_index()
    return "index.html not found", 404


@app.route('/<path:path>')
def static_proxy(path):
    if _has_path_traversal(path):
        abort(403)

    if path == "api" or path.startswith("api/"):
        return jsonify({"error": "API route not found"}), 404

    if path in PUBLIC_ROOT_FILES:
        return send_from_directory(PROJECT_ROOT, path)

    if path.startswith('web_viewer/'):
        return _send_web_viewer_asset(path)

    if '.' in os.path.basename(path):
        abort(404)

    if os.path.exists(INDEX_HTML_PATH):
        return _send_root_index()

    abort(404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
