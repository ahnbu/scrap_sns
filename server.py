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
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS
from utils.post_meta import META_FIELDS, build_post_meta, canonicalize_url

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
SCRAP_PROGRESS = {
    "run_id": "",
    "running": False,
    "seq": 0,
    "events": [],
    "started_at": None,
    "updated_at": None,
}
SCRAP_PROGRESS_LOCK = threading.Lock()
_POSTS_CACHE = {
    "path": None,
    "mtime": None,
    "size": None,
    "posts_full": None,
    "posts_meta": None,
    "etag": None,
}


def _now_kst_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


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
    if "이미지 다운로드 완료" in text:
        return "이미지 다운로드 완료"
    if "Total Full 저장 완료" in text:
        return "통합 파일 저장 완료"

    running_match = re.search(
        r"\[\+\]\s*(Threads|LinkedIn|X/Twitter)\s+(Producer|Consumer)\s+실행 중",
        text,
    )
    if running_match:
        platform = _scrap_progress_platform_label(running_match.group(1))
        phase = _scrap_progress_phase_label(running_match.group(2))
        return f"{platform} {phase} 수집 시작"

    done_match = re.search(
        r"✅\s*(Threads|LinkedIn|X/Twitter)\s+(Producer|Consumer)\s+완료",
        text,
    )
    if done_match:
        platform = _scrap_progress_platform_label(done_match.group(1))
        phase = _scrap_progress_phase_label(done_match.group(2))
        return f"{platform} {phase} 수집 완료"

    auth_match = re.search(
        r"🔐\s*(Threads|LinkedIn|X/Twitter)\s+(Producer|Consumer)\s+인증 필요",
        text,
    )
    if auth_match:
        platform = _scrap_progress_platform_label(auth_match.group(1))
        phase = _scrap_progress_phase_label(auth_match.group(2))
        return f"{platform} {phase} 인증 필요"

    failed_match = re.search(
        r"❌\s*(Threads|LinkedIn|X/Twitter)\s+(Producer|Consumer)\s+종료",
        text,
    )
    if failed_match:
        platform = _scrap_progress_platform_label(failed_match.group(1))
        phase = _scrap_progress_phase_label(failed_match.group(2))
        return f"{platform} {phase} 수집 실패"

    return None


def _append_scrap_progress(message, level="info"):
    if not message:
        return

    with SCRAP_PROGRESS_LOCK:
        SCRAP_PROGRESS["seq"] += 1
        now = _now_kst_iso()
        SCRAP_PROGRESS["updated_at"] = now
        SCRAP_PROGRESS["events"].append(
            {
                "seq": SCRAP_PROGRESS["seq"],
                "time": now,
                "level": level,
                "message": str(message),
            }
        )
        if len(SCRAP_PROGRESS["events"]) > SCRAP_PROGRESS_MAX_EVENTS:
            SCRAP_PROGRESS["events"] = SCRAP_PROGRESS["events"][-SCRAP_PROGRESS_MAX_EVENTS:]


def _reset_scrap_progress(run_id, mode):
    now = _now_kst_iso()
    with SCRAP_PROGRESS_LOCK:
        SCRAP_PROGRESS.update(
            {
                "run_id": run_id,
                "running": True,
                "seq": 0,
                "events": [],
                "started_at": now,
                "updated_at": now,
            }
        )

    label = "전체 재수집" if mode == "all" else "최근 업데이트"
    _append_scrap_progress(f"{label} 스크랩 시작")


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
            f"X {stats['twitter_count']}건"
        )
    return (
        "스크랩 완료: "
        f"Threads {stats['threads']}건, "
        f"LinkedIn {stats['linkedin']}건, "
        f"X {stats['twitter']}건"
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
    if value not in {"threads", "linkedin", "twitter"}:
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
        return sorted(posts, key=lambda post: post.get("sequence_id") or 0, reverse=True)

    return sorted(
        posts,
        key=lambda post: (
            str(post.get("created_at") or ""),
            str(post.get("date") or ""),
            post.get("sequence_id") or 0,
        ),
        reverse=(sort_value != "oldest"),
    )


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


def _normalize_scrap_summary(summary):
    if not isinstance(summary, dict):
        return {"auth_required": [], "platform_results": {}}

    platform_results = {}
    for raw_platform, raw_result in (summary.get("platform_results") or {}).items():
        platform = _canonical_auth_platform(raw_platform)
        if not platform:
            continue
        if isinstance(raw_result, dict):
            platform_results[platform] = raw_result
        else:
            platform_results[platform] = {"status": str(raw_result)}

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
        platform = _canonical_auth_platform(raw_platform)
        if platform and platform not in seen:
            normalized_auth_required.append(platform)
            seen.add(platform)

    return {
        "auth_required": normalized_auth_required,
        "platform_results": platform_results,
    }


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


def _load_latest_posts():
    latest_file = _get_latest_total_file()
    stat = os.stat(latest_file)
    mtime = stat.st_mtime_ns
    size = stat.st_size

    if (
        _POSTS_CACHE["path"] == latest_file
        and _POSTS_CACHE["mtime"] == mtime
        and _POSTS_CACHE["size"] == size
        and _POSTS_CACHE["posts_full"] is not None
        and _POSTS_CACHE["posts_meta"] is not None
    ):
        return _POSTS_CACHE

    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    posts_full = []
    posts_meta = []
    for raw_post in data.get("posts", []):
        meta = build_post_meta(raw_post)
        meta["canonical_url"] = meta.get("canonical_url") or canonicalize_url(raw_post)
        meta = {field: meta.get(field) for field in META_FIELDS}
        searchable_parts = [
            str(raw_post.get("full_text") or ""),
            str(raw_post.get("display_name") or ""),
            str(raw_post.get("username") or raw_post.get("user") or ""),
        ]
        posts_full.append(
            {
                **raw_post,
                **meta,
                "_searchable": " ".join(part for part in searchable_parts if part).lower(),
            }
        )
        posts_meta.append(meta)

    _POSTS_CACHE.update(
        {
            "path": latest_file,
            "mtime": mtime,
            "size": size,
            "posts_full": posts_full,
            "posts_meta": posts_meta,
            "etag": f'"{mtime}-{size}"',
        }
    )
    return _POSTS_CACHE

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    try:
        export_path = os.path.join(WEB_VIEWER_DIR, "sns_tags.json")
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
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        if not os.path.exists(WEB_VIEWER_DIR):
            os.makedirs(WEB_VIEWER_DIR)
        export_path = os.path.join(WEB_VIEWER_DIR, "sns_tags.json")
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return jsonify({"status": "success", "message": "Tags saved successfully"})
    except Exception as e:
        logging.exception("Failed to save tags")
        return jsonify({"status": "error", "message": "Failed to save tags"}), 500

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
    posts = cache.get("posts_full") or []
    metadata = {}

    if cache.get("path"):
        with open(cache["path"], 'r', encoding='utf-8-sig') as f:
            metadata = (json.load(f).get("metadata") or {})

    total_count = int(metadata.get("total_count") or len(posts))
    platform_counts = {
        "threads": int(metadata.get("threads_count") or 0),
        "linkedin": int(metadata.get("linkedin_count") or 0),
        "twitter": int(metadata.get("twitter_count") or 0),
    }
    if not any(platform_counts.values()):
        for post in posts:
            platform = str(post.get("sns_platform") or "").lower()
            if platform in {"threads", "linkedin"}:
                platform_counts[platform] += 1
            elif platform in {"twitter", "x"}:
                platform_counts["twitter"] += 1

    before_keys = {
        key
        for key in (_consistency_post_key(post) for post in (before_posts or []))
        if key
    }
    new_posts_by_platform = {"threads": [], "linkedin": [], "twitter": []}
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
        _reset_scrap_progress(run_id, mode)
        progress_started = True
        before_payload = _read_latest_total_payload()
        before_meta = (before_payload or {}).get("metadata")
        before_counts = {
            'total': (before_meta or {}).get('total_count', 0),
            'threads': (before_meta or {}).get('threads_count', 0),
            'linkedin': (before_meta or {}).get('linkedin_count', 0),
            'twitter': (before_meta or {}).get('twitter_count', 0),
        }
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            [sys.executable, "-u", script_path, "--mode", mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
        full_output = []
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                full_output.append(line)
                _append_scrap_progress(_scrap_progress_message_from_line(line))
        process.wait()
        stdout_val = "".join(full_output[-20:])
        after_meta = _read_latest_metadata()
        after_counts = {
            'total': (after_meta or {}).get('total_count', 0),
            'threads': (after_meta or {}).get('threads_count', 0),
            'linkedin': (after_meta or {}).get('linkedin_count', 0),
            'twitter': (after_meta or {}).get('twitter_count', 0),
        }
        stats = {
            'total': after_counts['total'] - before_counts['total'],
            'threads': after_counts['threads'] - before_counts['threads'],
            'linkedin': after_counts['linkedin'] - before_counts['linkedin'],
            'twitter': after_counts['twitter'] - before_counts['twitter'],
            'total_count': after_counts['total'],
            'threads_count': after_counts['threads'],
            'linkedin_count': after_counts['linkedin'],
            'twitter_count': after_counts['twitter'],
        }
        summary = _normalize_scrap_summary(_parse_scrap_summary(full_output))
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
        for post in cache["posts_full"]:
            if post.get("sequence_id") == sequence_id:
                return jsonify(
                    {
                        key: value
                        for key, value in post.items()
                        if key != "_searchable"
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

    try:
        limit = int(request.args.get("limit", 500))
    except (TypeError, ValueError):
        limit = 500
    limit = max(1, min(limit, 1000))

    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    try:
        cache = _load_latest_posts()
        query = q.lower()
        matched_posts = []
        for post in cache["posts_full"]:
            if not _matches_platform_filter(post, platform):
                continue
            if query in str(post.get("_searchable") or ""):
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

        for post in cache["posts_full"]:
            matched_tags = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue

                keyword = str(rule.get("keyword") or "").strip().lower()
                tag = str(rule.get("tag") or "").strip()
                match_field = str(rule.get("match_field") or "all").strip().lower()
                if not keyword or not tag:
                    continue

                haystack_parts = [str(post.get("full_text") or "")]
                if match_field == "all":
                    haystack_parts.extend(
                        [
                            str(post.get("display_name") or ""),
                            str(post.get("username") or post.get("user") or ""),
                        ]
                    )
                haystack = " ".join(part for part in haystack_parts if part).lower()

                if keyword in haystack and tag not in matched_tags:
                    matched_tags.append(tag)

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
