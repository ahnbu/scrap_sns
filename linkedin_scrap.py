from utils.common import clean_text, load_json, save_json
from utils.auth_status import exit_auth_required
from dataclasses import dataclass
import json
import sys
import os
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime
from utils.json_to_md import convert_json_to_md
from utils.linkedin_parser import extract_urn_id
from scripts.linkedin_opencli_shadow_parse import parse_shadow_raw

# --- 설정 ---
TARGET_URL = "https://www.linkedin.com/my-items/saved-posts/"
DATA_DIR = "output_linkedin/python"
UPDATE_DIR = os.path.join(DATA_DIR, "update")
OPENCLI_RUNTIME_DIR = os.path.join("output_linkedin", "opencli_runtime")
OPENCLI_PRODUCTION_SESSION = "linkedin_saved_production"
CHROME_PATHS = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
]

# CLI 인자 파싱
CRAWL_MODE = "update only"  # 기본값 (__main__ 블록에서 CLI 인자로 덮어씀)
CRAWL_START_TIME = datetime.now()
CONSECUTIVE_EXISTING_LIMIT = 20

# --- 헬퍼 함수 ---


# 로컬 clean_text 제거 (utils.common 사용)

@dataclass(frozen=True)
class ChromeWindowInfo:
    hwnd: int
    title: str
    process_id: int


class LinkedInAuthRequiredError(RuntimeError):
    def __init__(self, reason, current_url=None):
        super().__init__(reason)
        self.reason = reason
        self.current_url = current_url

def configure_text_output(stream=None):
    target = stream or sys.stdout
    encoding = (getattr(target, "encoding", "") or "").lower()
    reconfigure = getattr(target, "reconfigure", None)
    if encoding and encoding != "utf-8" and callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def get_opencli_command():
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = (
            Path(appdata)
            / "npm"
            / "node_modules"
            / "@jackwener"
            / "opencli"
            / "dist"
            / "src"
            / "main.js"
        )
        if candidate.exists():
            return ["node", str(candidate)]
    return ["opencli"]


def parse_json_stdout(stdout):
    text = (stdout or "").lstrip("\ufeff").strip()
    if not text:
        raise RuntimeError("OpenCLI command returned empty stdout")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenCLI command returned non-JSON stdout: {text[:200]}") from exc


def run_opencli_whoami():
    command = get_opencli_command() + [
        "linkedin",
        "whoami",
        "--site-session",
        "persistent",
        "-f",
        "json",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI LinkedIn session is not logged in: {message}")

    payload = parse_json_stdout(result.stdout)
    if not payload.get("logged_in"):
        raise RuntimeError("OpenCLI LinkedIn session is not logged in")
    return payload


def resolve_chrome_executable():
    for chrome_path in CHROME_PATHS:
        if Path(chrome_path).exists():
            return chrome_path
    return None


def _process_image_name(process_id):
    if os.name != "nt":
        return ""

    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def snapshot_visible_chrome_windows():
    if os.name != "nt":
        return []

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    windows = []

    def enum_window(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        image_name = _process_image_name(int(process_id.value))
        if os.path.basename(image_name).lower() == "chrome.exe":
            windows.append(ChromeWindowInfo(hwnd=int(hwnd), title=buffer.value, process_id=int(process_id.value)))
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_window)
    user32.EnumWindows(enum_proc, 0)
    return windows


def launch_chrome_new_window(chrome_path):
    subprocess.Popen(
        [chrome_path, "--new-window", TARGET_URL],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def record_chrome_window_candidates(reason, candidates):
    payload = {
        "reason": reason,
        "candidates": [
            {"hwnd": candidate.hwnd, "title": candidate.title, "process_id": candidate.process_id}
            for candidate in candidates
        ],
    }
    print(f"OpenCLI Chrome HWND candidates: {json.dumps(payload, ensure_ascii=False)}")


def open_owned_chrome_window(poll_attempts=20, poll_interval=0.5):
    chrome_path = resolve_chrome_executable()
    if not chrome_path:
        raise RuntimeError("Chrome executable not found")

    baseline = {window.hwnd for window in snapshot_visible_chrome_windows()}
    launch_chrome_new_window(chrome_path)

    latest_candidates = []
    for _ in range(poll_attempts):
        latest_candidates = [
            window
            for window in snapshot_visible_chrome_windows()
            if window.hwnd not in baseline
        ]
        if len(latest_candidates) == 1:
            return latest_candidates[0].hwnd
        if len(latest_candidates) > 1:
            record_chrome_window_candidates("ambiguous_candidates", latest_candidates)
            raise RuntimeError(f"{len(latest_candidates)} new visible Chrome windows after launch")
        if poll_interval:
            time.sleep(poll_interval)

    record_chrome_window_candidates("no_candidates", latest_candidates)
    raise RuntimeError("0 new visible Chrome windows after launch")


def focus_chrome_window(hwnd):
    if os.name != "nt":
        return False

    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    return bool(user32.SetForegroundWindow(int(hwnd)))


def close_owned_chrome_window(hwnd):
    if os.name != "nt":
        return False

    import ctypes

    WM_CLOSE = 0x0010
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    return bool(user32.PostMessageW(int(hwnd), WM_CLOSE, 0, 0))


def should_stop_opencli_daemon():
    return os.environ.get("SCRAP_SNS_KEEP_OPENCLI_DAEMON") != "1"


def is_opencli_daemon_running():
    command = get_opencli_command() + ["daemon", "status"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return False
    if result.returncode != 0:
        return False
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "daemon: running" in output


def run_opencli_browser_session_command(action, session=OPENCLI_PRODUCTION_SESSION):
    command = get_opencli_command() + ["browser", session, action]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        print(f"OpenCLI browser {action} 실패: {message}")
        return False
    print(f"OpenCLI browser {action} 완료")
    return True


def is_linkedin_saved_posts_url(url):
    return "linkedin.com/my-items/saved-posts" in str(url or "")


def bind_opencli_browser_session(session=OPENCLI_PRODUCTION_SESSION, max_attempts=3, retry_interval=1.0):
    last_url = ""
    for attempt in range(max_attempts):
        command = get_opencli_command() + ["browser", session, "bind"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            print(f"OpenCLI browser bind 실패: {message}")
            raise RuntimeError("OpenCLI browser bind failed")

        payload = parse_json_stdout(result.stdout)
        last_url = str(payload.get("url") or "")
        if is_linkedin_saved_posts_url(last_url):
            print("OpenCLI browser bind 완료")
            return payload

        print(f"OpenCLI browser bind URL 불일치: {last_url}")
        if attempt + 1 < max_attempts:
            time.sleep(retry_interval)

    raise RuntimeError(f"OpenCLI browser bind attached to unexpected URL: {last_url}")


def prepare_owned_chrome_window_for_bind(hwnd, settle_delay=1.0):
    if not focus_chrome_window(hwnd):
        return False
    if settle_delay:
        time.sleep(settle_delay)
    return True


def cleanup_opencli_browser_session(session=OPENCLI_PRODUCTION_SESSION):
    run_opencli_browser_session_command("unbind", session=session)
    run_opencli_browser_session_command("close", session=session)


def stop_opencli_daemon():
    command = get_opencli_command() + ["daemon", "stop"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        print(f"OpenCLI daemon 종료 실패: {message}")
        return False
    print("OpenCLI daemon 종료 완료")
    return True


def run_opencli_browser_eval(script, session=OPENCLI_PRODUCTION_SESSION):
    command = get_opencli_command() + ["browser", session, "eval", script]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI browser eval failed: {message}")
    return parse_json_stdout(result.stdout)


def run_opencli_browser_state(session=OPENCLI_PRODUCTION_SESSION):
    command = get_opencli_command() + ["browser", session, "state"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI browser state failed: {message}")
    return result.stdout or ""


def validate_bound_opencli_session(session=OPENCLI_PRODUCTION_SESSION):
    script = """(() => ({
  href: location.href,
  title: document.title,
  text: (document.body && document.body.innerText || "").slice(0, 5000)
}))()"""
    page = run_opencli_browser_eval(script, session=session)
    state = run_opencli_browser_state(session=session)
    href = str(page.get("href") or "")
    title = str(page.get("title") or "")
    text = str(page.get("text") or "")
    combined = f"{href}\n{title}\n{text}\n{state}"
    lowered = combined.lower()

    if "checkpoint" in lowered or "login" in lowered or "authwall" in lowered:
        raise LinkedInAuthRequiredError("login_required", href)
    if "linkedin.com/my-items/saved-posts" not in href:
        raise RuntimeError(f"LinkedIn saved posts URL was not confirmed: {href}")
    if "저장한 게시물" not in combined and "Saved" not in combined:
        raise RuntimeError("LinkedIn saved posts page was not confirmed")

    return {"site": "linkedin", "logged_in": True, "public_id": page.get("public_id")}


def write_existing_ids_file(raw_dir, existing_codes):
    existing_ids = sorted(str(code) for code in existing_codes if code)
    os.makedirs(raw_dir, exist_ok=True)
    ids_path = os.path.join(raw_dir, "existing_ids.json")
    save_json(ids_path, existing_ids)
    return ids_path


def run_opencli_collector(crawl_start_time, existing_codes=None, session=OPENCLI_PRODUCTION_SESSION):
    stamp = crawl_start_time.strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(OPENCLI_RUNTIME_DIR, "raw", stamp)
    command = [
        "node",
        "scripts/linkedin_opencli_shadow_collect.mjs",
        "--session",
        session,
        "--url",
        TARGET_URL,
        "--out",
        raw_dir,
        "--use-bound-session",
    ]
    if CRAWL_MODE == "update only":
        ids_path = write_existing_ids_file(raw_dir, existing_codes or set())
        command.extend([
            "--existing-ids-file",
            ids_path,
            "--stop-after-existing-streak",
            str(CONSECUTIVE_EXISTING_LIMIT),
        ])
    else:
        command.append("--until-exhausted")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"OpenCLI LinkedIn collection failed: {message}")

    summary = parse_json_stdout(result.stdout)
    if int(summary.get("pages_collected") or 0) <= 0:
        raise RuntimeError("OpenCLI collection returned no raw pages")
    if int(summary.get("total_unique_activity_ids") or 0) <= 0:
        raise RuntimeError("OpenCLI collection returned no activity IDs")
    return raw_dir, summary


def validate_opencli_payload(payload):
    metadata = payload.get("metadata") or {}
    if int(metadata.get("parsed_post_count") or 0) <= 0:
        raise RuntimeError("OpenCLI parsed post count is zero")
    if int(metadata.get("duplicate_platform_id_count") or 0) > 0:
        raise RuntimeError("OpenCLI duplicate platform_id detected")
    if int(metadata.get("parser_failed_count") or 0) > 0:
        raise RuntimeError("OpenCLI parser failed for one or more posts")
    if int(metadata.get("entity_without_save_state_count") or 0) > 0:
        raise RuntimeError("OpenCLI SaveState verification failed")
    if int(metadata.get("entity_without_cluster_reference_count") or 0) > 0:
        raise RuntimeError("OpenCLI cluster reference verification failed")


def collect_opencli_posts(crawl_start_time, existing_codes=None):
    owned_hwnd = None
    opencli_session_touched = False
    daemon_was_running = None
    try:
        owned_hwnd = open_owned_chrome_window()
        if not prepare_owned_chrome_window_for_bind(owned_hwnd):
            raise RuntimeError(f"OpenCLI Chrome focus failed for HWND {owned_hwnd}")
        daemon_was_running = is_opencli_daemon_running()
        opencli_session_touched = True
        bind_opencli_browser_session()
        bound_session_state = validate_bound_opencli_session()
        print(f"✅ OpenCLI LinkedIn 저장글 창 확인: {bound_session_state.get('site', 'linkedin')}")

        raw_dir, collection_summary = run_opencli_collector(crawl_start_time, existing_codes=existing_codes)
        print(
            "📥 OpenCLI raw 수집 완료: "
            f"{collection_summary.get('pages_collected')} pages, "
            f"{collection_summary.get('total_unique_activity_ids')} unique IDs"
        )

        payload = parse_shadow_raw(raw_dir, crawl_start_time, require_save_state=True)
        validate_opencli_payload(payload)
        metadata = payload["metadata"]
        print(
            "✅ OpenCLI parse 검증 통과: "
            f"parsed={metadata.get('parsed_post_count')}, "
            f"duplicates={metadata.get('duplicate_platform_id_count')}, "
            f"parser_failed={metadata.get('parser_failed_count')}"
        )
        metadata["opencli_collection"] = collection_summary
        metadata["opencli_whoami"] = {
            "site": bound_session_state.get("site"),
            "logged_in": bound_session_state.get("logged_in"),
            "public_id": bound_session_state.get("public_id"),
        }
        return payload["posts"], metadata
    finally:
        if opencli_session_touched:
            try:
                cleanup_opencli_browser_session()
            except RuntimeError as exc:
                print(f"OpenCLI browser cleanup 실패: {exc}")
        if opencli_session_touched and should_stop_opencli_daemon() and daemon_was_running is False:
            try:
                stop_opencli_daemon()
            except RuntimeError as exc:
                print(f"OpenCLI daemon cleanup 실패: {exc}")
        if owned_hwnd is not None:
            try:
                close_owned_chrome_window(owned_hwnd)
            except RuntimeError as exc:
                print(f"Chrome window cleanup 실패: {exc}")


def get_post_identity(post):
    return post.get("platform_id") or post.get("code")


def merge_linkedin_full_posts(old_posts, scraped_posts, crawl_mode):
    old_by_id = {}
    old_order = []
    for post in old_posts:
        pid = get_post_identity(post)
        if not pid or pid in old_by_id:
            continue
        old_by_id[pid] = post
        old_order.append(pid)

    final_by_id = dict(old_by_id)
    observed_existing_ids = []
    new_items = []

    for post in scraped_posts:
        pid = get_post_identity(post)
        if not pid:
            continue

        existing = old_by_id.get(pid)
        if existing:
            merged = {**existing, **post}
            if existing.get("sequence_id") is not None:
                merged["sequence_id"] = existing.get("sequence_id")
            if existing.get("crawled_at"):
                merged["crawled_at"] = existing.get("crawled_at")
            if existing.get("local_images") and not post.get("local_images"):
                merged["local_images"] = existing.get("local_images")
            final_by_id[pid] = merged
            observed_existing_ids.append(pid)
        else:
            final_by_id[pid] = post
            new_items.append(post)

    observed_existing = set(observed_existing_ids)
    unobserved_existing_ids = [pid for pid in old_order if pid not in observed_existing]

    final_posts = list(final_by_id.values())
    final_posts.sort(key=lambda item: item.get("sequence_id", 0), reverse=True)

    unobserved_policy = (
        "preserved_not_deletion_candidate"
        if crawl_mode == "update only"
        else "preserved_pending_full_sync_review"
    )
    merge_report = {
        "crawl_mode": crawl_mode,
        "observed_existing_count": len(observed_existing),
        "unobserved_existing_count": len(unobserved_existing_ids),
        "unobserved_existing_ids": unobserved_existing_ids[:20],
        "unobserved_existing_policy": unobserved_policy,
    }

    return final_posts, new_items, merge_report

class LinkedinScraper:
    def __init__(self):
        self.posts = [] # collected data
        self.new_posts_count = 0
        self.stopped_early = False
        self.collected_codes = set()
        
        # 기존 데이터 로드 (증분 업데이트용)
        self.existing_codes = set()
        self.existing_posts_map = {}
        self.max_sequence_id = 0
        self.consecutive_existing_count = 0
        
        # 전체 파일 경로 (가장 최근 날짜 파일 찾기)
        self.full_file_path = self.get_latest_full_file()
            
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj

            for p in full_posts:
                pid = p.get("platform_id") or p.get("code")
                if pid:
                    self.existing_codes.add(pid)
                    self.existing_posts_map[pid] = p
            
            if isinstance(full_data_obj, dict):
                self.max_sequence_id = full_data_obj.get("metadata", {}).get("max_sequence_id", 0)
            
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨. 현재 max_sequence_id: {self.max_sequence_id}")
            if CRAWL_MODE == "update only":
                print(
                    f"🔄 UPDATE ONLY 모드: 기존 {len(self.existing_codes)}건과 대조, "
                    f"기수집 {CONSECUTIVE_EXISTING_LIMIT}건 연속 확인 시 수집을 중단합니다."
                )

    def get_latest_full_file(self):
        if not os.path.exists(DATA_DIR):
            return None
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("linkedin_py_full_") and f.endswith(".json")]
        if not files:
            return None
        # 날짜순 정렬 (파일명에 YYYYMMDD가 포함되어 있으므로 문자열 정렬 가능)
        files.sort(reverse=True)
        return os.path.join(DATA_DIR, files[0])

    def run(self):
        start_time_dt = datetime.now()
        print("🚀 링크드인 스크래퍼 시작 (OpenCLI 기본 모드)")

        self.posts, self.opencli_metadata = collect_opencli_posts(CRAWL_START_TIME, existing_codes=self.existing_codes)
        self.save_results()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        print("\n" + "="*40)
        print(f"시작시간 : {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"종료시간 : {end_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요시간: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print("="*40)

    def save_results(self):
        if not self.posts:
            print("ℹ️ 수집된 새로운 데이터가 없습니다.")
            return

        date_str = CRAWL_START_TIME.strftime("%Y%m%d")
        full_file, final_posts, new_items = self.update_full_version(date_str)

        # 신규 수집된 것들만 업데이트 파일에 저장
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"linkedin_python_update_{timestamp}.json")
        final_indexed_posts = []
        for idx, post in enumerate(new_items):
            final_indexed_posts.append({"index": idx + 1, **post})

        if final_indexed_posts:
            save_json(update_file, final_indexed_posts)
            print(f"💾 업데이트 데이터 저장 완료: {update_file} ({len(final_indexed_posts)}개)")
        else:
            print("ℹ️ 신규 LinkedIn 저장글은 없습니다.")

        print(f"✅ LinkedIn full 저장 기준: {full_file} (총 {len(final_posts)}개)")

    def update_full_version(self, date_str):
        print("🔄 전체 데이터 병합 중...")
        
        # 기존 전체 데이터 로드
        old_posts = []
        existing_merge_history = []
        source_filename = None

        if self.full_file_path:
            source_filename = os.path.basename(self.full_file_path)
            old_data_obj = load_json(self.full_file_path)
            if isinstance(old_data_obj, dict):
                old_posts = old_data_obj.get("posts", [])
                existing_merge_history = old_data_obj.get("metadata", {}).get("merge_history", [])
            else:
                old_posts = old_data_obj

        final_posts, new_items, merge_report = merge_linkedin_full_posts(
            old_posts,
            self.posts,
            CRAWL_MODE,
        )
        duplicate_count = len(self.posts) - len(new_items)

        new_items.sort(key=lambda item: item.get("crawled_at", ""))
        for post in new_items:
            if not post.get("sequence_id"):
                self.max_sequence_id += 1
                post["sequence_id"] = self.max_sequence_id

        # sequence_id 기준으로 내림차순 정렬 (최신순)
        final_posts.sort(key=lambda x: x.get("sequence_id", 0), reverse=True)

        # merge_history 업데이트
        merge_history = list(existing_merge_history)
        if new_items:
            merge_history.append({
                "merged_at": datetime.now().isoformat(),
                "new_items_count": len(new_items),
                "duplicates_removed": duplicate_count,
                "source_file": source_filename,
                "crawl_mode": CRAWL_MODE,
                "observed_existing_count": merge_report["observed_existing_count"],
                "unobserved_existing_count": merge_report["unobserved_existing_count"],
                "unobserved_existing_ids": merge_report["unobserved_existing_ids"],
                "unobserved_existing_policy": merge_report["unobserved_existing_policy"],
            })

        full_file = os.path.join(DATA_DIR, f"linkedin_py_full_{date_str}.json")
        
        # 메타데이터 구조 (JS 버전 참고)
        legacy_count = len([p for p in final_posts if "crawled_at" not in p])
        verified_count = len(final_posts) - legacy_count
        opencli_metadata = getattr(self, "opencli_metadata", {}) or {}
        opencli_collection = opencli_metadata.get("opencli_collection") or {}
        opencli_whoami = opencli_metadata.get("opencli_whoami") or {}

        full_data = {
            "metadata": {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "first_code": (final_posts[0].get("platform_id") or final_posts[0].get("code")) if final_posts else None,
                "last_code": (final_posts[-1].get("platform_id") or final_posts[-1].get("code")) if final_posts else None,
                "crawl_mode": CRAWL_MODE,
                "legacy_data_count": legacy_count,
                "verified_data_count": verified_count,
                "collector": "opencli",
                "opencli_logged_in": opencli_whoami.get("logged_in"),
                "opencli_site": opencli_whoami.get("site"),
                "opencli_public_id": opencli_whoami.get("public_id"),
                "opencli_raw_pages": opencli_collection.get("pages_collected"),
                "opencli_unique_activity_ids": opencli_collection.get("total_unique_activity_ids"),
                "opencli_parsed_post_count": opencli_metadata.get("parsed_post_count"),
                "opencli_duplicate_platform_id_count": opencli_metadata.get("duplicate_platform_id_count"),
                "opencli_parser_failed_count": opencli_metadata.get("parser_failed_count"),
                "opencli_entity_without_save_state_count": opencli_metadata.get("entity_without_save_state_count"),
                "opencli_entity_without_cluster_reference_count": opencli_metadata.get("entity_without_cluster_reference_count"),
                "all_mode_observed_existing_count": merge_report["observed_existing_count"],
                "all_mode_unobserved_existing_count": merge_report["unobserved_existing_count"],
                "unobserved_existing_policy": merge_report["unobserved_existing_policy"],
                "opencli_end_reason": opencli_collection.get("end_reason"),
                "opencli_existing_streak_stop_limit": opencli_collection.get("existing_streak_stop_limit"),
                "opencli_existing_streak_at_end": opencli_collection.get("existing_streak_at_end"),
                "opencli_existing_ids_loaded": opencli_collection.get("existing_ids_loaded"),
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 파일 저장 완료: {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)
        return full_file, final_posts, new_items

def main(argv=None):
    configure_text_output(sys.stdout)
    configure_text_output(sys.stderr)
    parser = argparse.ArgumentParser(description='LinkedIn 스크래퍼')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    args = parser.parse_args(argv)
    global CRAWL_MODE
    CRAWL_MODE = "update only" if args.mode == "update" else "all"
    scraper = LinkedinScraper()
    try:
        scraper.run()
    except LinkedInAuthRequiredError as exc:
        exit_auth_required(
            "linkedin",
            reason=exc.reason,
            current_url=exc.current_url,
        )


if __name__ == "__main__":
    main()
