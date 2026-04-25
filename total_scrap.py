from utils.common import load_json, save_json, clean_text, reorder_post, format_timestamp, parse_relative_time
import subprocess
import time
import os
import sys
import glob
import json
import argparse
import signal
import hashlib
import requests
from datetime import datetime
import io
from utils.json_to_md import convert_json_to_md
from utils.auth_status import AUTH_REQUIRED_EXIT_CODE

# Windows 터미널 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
OUTPUT_THREADS_DIR = os.path.join(PROJECT_ROOT, "output_threads", "python")
OUTPUT_LINKEDIN_DIR = os.path.join(PROJECT_ROOT, "output_linkedin", "python")
OUTPUT_TWITTER_DIR = os.path.join(PROJECT_ROOT, "output_twitter", "python")
OUTPUT_TOTAL_DIR = os.path.join(PROJECT_ROOT, "output_total")
WEB_IMAGE_DIR = os.path.join(PROJECT_ROOT, "web_viewer", "images")
WEB_IMAGE_PREFIX = "web_viewer/images"

# 전역 프로세스 및 로그 파일 리스트 (시그널 핸들러에서 사용)
running_processes = []
opened_log_files = [] # (platform, file_handle)

PLATFORM_KEYS = {
    "Threads": "threads",
    "LinkedIn": "linkedin",
    "X/Twitter": "x",
}

def signal_handler(sig, frame):
    # 중복 호출 방지
    if getattr(signal_handler, '_called', False):
        return
    signal_handler._called = True

    print("\n\n🛑 사용자에 의해 중단되었습니다 (Ctrl+C). 모든 백그라운드 프로세스를 종료합니다...")
    
    # 프로세스 종료
    for platform, p in running_processes:
        try:
            # 윈도우에서 자식 프로세스 트리를 종료하기 위한 명령 (비동기 실행)
            subprocess.Popen(f"taskkill /F /T /PID {p.pid}", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        except Exception:
            pass
            
    # 로그 파일 마감
    for plat, f in opened_log_files:
        try:
            if not f.closed:
                f.write(f"\n\n================================================\n")
                f.write(f"🛑 {plat} 사용자에 의해 강제 중단됨: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"================================================\n")
                f.flush()
                f.close()
        except Exception: pass

    print("🏁 프로세스 종료 명령 완료. 즉시 종료합니다.")
    os._exit(0)

# 시그널 핸들러 등록
signal.signal(signal.SIGINT, signal_handler)

# CLI 인자 파싱
def find_latest_full_file(directory, pattern):
    files = glob.glob(os.path.join(directory, pattern))
    if not files: return None
    files.sort(reverse=True)
    return files[0]


def get_media_extension(img_url):
    lower_url = str(img_url).lower()
    if '.png' in lower_url:
        return '.png'
    if '.webp' in lower_url:
        return '.webp'
    return '.jpg'


def get_local_image_paths(img_url):
    file_hash = hashlib.md5(str(img_url).encode('utf-8')).hexdigest()
    filename = f"{file_hash}{get_media_extension(img_url)}"
    return os.path.join(WEB_IMAGE_DIR, filename), f"{WEB_IMAGE_PREFIX}/{filename}"


def web_image_exists(web_path):
    if not web_path:
        return False
    normalized = str(web_path).replace('/', os.sep)
    return os.path.exists(os.path.join(PROJECT_ROOT, normalized))


def collect_preserved_local_images():
    preserved = {}
    pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
    for total_path in sorted(glob.glob(pattern), reverse=True):
        if not os.path.basename(total_path).startswith("total_full_"):
            continue
        data = load_json(total_path, {})
        posts = data.get('posts', []) if isinstance(data, dict) else []
        for post in posts:
            media_list = post.get('media') or []
            local_images = post.get('local_images') or []
            for index, img_url in enumerate(media_list):
                if index >= len(local_images):
                    continue
                web_path = local_images[index]
                if img_url and web_image_exists(web_path) and img_url not in preserved:
                    preserved[img_url] = web_path
    return preserved


def validate_local_image_links(posts):
    missing = []
    for post in posts:
        local_images = set(post.get('local_images') or [])
        for img_url in post.get('media', []) or []:
            if '.mp4' in str(img_url).lower():
                continue
            fs_path, web_path = get_local_image_paths(img_url)
            if os.path.exists(fs_path) and web_path not in local_images:
                missing.append({
                    "code": post.get('code') or post.get('platform_id') or post.get('url'),
                    "image": web_path,
                })
                if len(missing) >= 5:
                    break
        if len(missing) >= 5:
            break

    if missing:
        examples = ", ".join(f"{item['code']}->{item['image']}" for item in missing)
        raise RuntimeError(
            "local_images validation failed: existing local files are not linked. "
            f"examples: {examples}"
        )


def get_failure_count(failure_info):
    if not isinstance(failure_info, dict):
        return 0

    value = failure_info.get("fail_count")
    if value is None:
        value = failure_info.get("count", 0)

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _phase_display_name(phase_name):
    if phase_name == "producer":
        return "Producer"
    if phase_name == "consumer":
        return "Consumer"
    return str(phase_name or "").title()


def _safe_platform_name(platform):
    return str(platform).lower().replace('/', '_')


def _status_from_returncode(returncode):
    if returncode == 0:
        return "ok"
    if returncode == AUTH_REQUIRED_EXIT_CODE:
        return "auth_required"
    return "failed"


def _ensure_platform_result(platform_results, platform, log_path):
    platform_key = PLATFORM_KEYS.get(platform, str(platform).lower())
    result = platform_results.setdefault(
        platform_key,
        {
            "status": "pending",
            "returncode": None,
            "log": log_path,
            "phases": {},
        },
    )
    result.setdefault("phases", {})
    if log_path:
        result["log"] = log_path
    return platform_key, result


def _write_phase_log_header(file_handle, platform, phase_name, cmd):
    phase_label = _phase_display_name(phase_name)
    file_handle.write("================================================\n")
    file_handle.write(
        f"🚀 {platform} {phase_label} 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    file_handle.write(f"💻 명령어: {cmd}\n")
    file_handle.write("================================================\n\n")
    file_handle.flush()


def _finalize_platform_results(platform_results):
    for result in platform_results.values():
        phases = result.get("phases") or {}
        statuses = [str(phase.get("status") or "").lower() for phase in phases.values()]
        if any(status == "auth_required" for status in statuses):
            result["status"] = "auth_required"
            result["returncode"] = AUTH_REQUIRED_EXIT_CODE
        elif any(status == "failed" for status in statuses):
            result["status"] = "failed"
            first_failed = next(
                (
                    phase.get("returncode")
                    for phase in phases.values()
                    if str(phase.get("status") or "").lower() == "failed"
                ),
                1,
            )
            result["returncode"] = first_failed
        elif statuses and all(status == "ok" for status in statuses):
            result["status"] = "ok"
            result["returncode"] = 0
        elif statuses:
            result["status"] = statuses[-1]
            result["returncode"] = next(
                (
                    phase.get("returncode")
                    for phase in reversed(list(phases.values()))
                    if phase.get("returncode") is not None
                ),
                None,
            )

def should_run_consumer(platform):
    """상세 수집기(Consumer)를 실행할 필요가 있는지 체크"""
    if platform == "Threads":
        latest = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_simple_*.json")
    elif platform == "X/Twitter":
        latest = find_latest_full_file(OUTPUT_TWITTER_DIR, "twitter_py_simple_*.json")
    else:
        return True # 기본적으로는 실행
        
    if not latest: return True
    
    data = load_json(latest)
    posts = data.get('posts', [])
    
    # 💡 수집 완료되지 않은 항목이 있는지 확인
    uncollected = [p for p in posts if not p.get('is_detail_collected')]
    
    # 실패 이력 체크
    failure_file = "scrap_failures_threads.json" if platform == "Threads" else "scrap_failures_twitter.json"
    failures = {}
    if os.path.exists(failure_file):
        with open(failure_file, 'r', encoding='utf-8-sig') as f:
            try: failures = json.load(f)
            except Exception: pass
            
    final_targets = [
        p
        for p in uncollected
        if get_failure_count(
            failures.get(str(p.get('platform_id') or p.get('id') or p.get('code')))
        ) < 3
    ]
    
    return len(final_targets) > 0

def run_scrapers_in_parallel(mode='update'):
    print(f"🚀 플랫폼별 스크래퍼 병렬 실행 시작 (2-wave 모드)... (모드: {mode})")
    platform_results = {}
    running_processes.clear()
    opened_log_files.clear()

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    create_no_window = 0x08000000
    phase_commands = [
        (
            "producer",
            {
                "Threads": f"python -u thread_scrap.py --mode {mode}",
                "X/Twitter": f"python -u twitter_scrap.py --mode {mode}",
                "LinkedIn": f"python -u linkedin_scrap.py --mode {mode}",
            },
        ),
        (
            "consumer",
            {
                "Threads": "python -u thread_scrap_single.py",
                "X/Twitter": "python -u twitter_scrap_single.py",
            },
        ),
    ]

    log_handles = {}

    try:
        for phase_name, commands in phase_commands:
            phase_label = _phase_display_name(phase_name)
            print(f"\n🚀 {phase_label} wave 시작...")
            running_processes.clear()

            for platform, cmd in commands.items():
                safe_name = _safe_platform_name(platform)
                log_path = os.path.join(log_dir, f"{safe_name}.log")
                file_handle = log_handles.get(platform)
                if file_handle is None:
                    file_handle = open(log_path, "a", encoding="utf-8")
                    log_handles[platform] = file_handle
                    opened_log_files.append((platform, file_handle))

                _write_phase_log_header(file_handle, platform, phase_name, cmd)
                print(f"   [+] {platform} {phase_label} 실행 중 (로그: {log_path})...")

                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["SNS_ORCHESTRATED_RUN"] = "1"

                p = subprocess.Popen(
                    f"cmd /c {cmd}",
                    creationflags=create_no_window,
                    stdout=file_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=PROJECT_ROOT
                )
                running_processes.append((platform, p))
                _, result = _ensure_platform_result(platform_results, platform, log_path)
                result["phases"][phase_name] = {
                    "status": "running",
                    "returncode": None,
                }

            print(f"\n⏳ {phase_label} wave 완료 대기 중... ({len(running_processes)}개 프로세스)")

            while any(p.poll() is None for _, p in running_processes):
                time.sleep(1)

            for platform, p in running_processes:
                safe_name = _safe_platform_name(platform)
                _, result = _ensure_platform_result(
                    platform_results,
                    platform,
                    os.path.join(log_dir, f"{safe_name}.log"),
                )
                phase_result = result["phases"].setdefault(phase_name, {})
                phase_result["returncode"] = p.returncode
                phase_result["status"] = _status_from_returncode(p.returncode)

                if p.returncode == 0:
                    print(f"   ✅ {platform} {phase_label} 완료.")
                elif p.returncode == AUTH_REQUIRED_EXIT_CODE:
                    print(f"   🔐 {platform} {phase_label} 인증 필요. 최신 보유 데이터로 계속 진행합니다.")
                else:
                    print(f"   ❌ {platform} {phase_label} 종료 (반환 코드: {p.returncode}). logs/{safe_name}.log 확인 필요.")

        _finalize_platform_results(platform_results)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

    finally:
        running_processes.clear()
        for plat, file_handle in opened_log_files:
            try:
                if not file_handle.closed:
                    file_handle.write("\n\n================================================\n")
                    file_handle.write(
                        f"🏁 {plat} 스크래핑 종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                    file_handle.write("================================================\n")
                    file_handle.close()
            except Exception:
                pass
        opened_log_files.clear()

    print("\n모든 플랫폼 스크래핑이 종료되었습니다.")
    return platform_results


def merge_results():
    print("\n📦 결과 병합 및 데이터 정규화 시작...")
    
    latest_threads = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_full_*.json")
    latest_linkedin = find_latest_full_file(OUTPUT_LINKEDIN_DIR, "linkedin_py_full_*.json")
    latest_twitter = find_latest_full_file(OUTPUT_TWITTER_DIR, "twitter_py_full_*.json")
    
    if not latest_threads and not latest_linkedin and not latest_twitter:
        print("❌ 병합 가능한 Full 파일을 찾을 수 없습니다.")
        return None, 0, 0, 0

    if latest_threads:
        print(f"   - Threads: {os.path.basename(latest_threads)}")
    else:
        print("   - Threads: 최신 Full 파일 없음")
    if latest_linkedin:
        print(f"   - LinkedIn: {os.path.basename(latest_linkedin)}")
    else:
        print("   - LinkedIn: 최신 Full 파일 없음")
    if latest_twitter:
        print(f"   - X/Twitter: {os.path.basename(latest_twitter)}")
    else:
        print("   - X/Twitter: 최신 Full 파일 없음")

    threads_data = load_json(latest_threads) if latest_threads else {}
    linkedin_data = load_json(latest_linkedin) if latest_linkedin else {}
    twitter_data = load_json(latest_twitter) if latest_twitter else {}
    
    threads_posts = threads_data.get('posts', []) if isinstance(threads_data, dict) else threads_data
    linkedin_posts = linkedin_data.get('posts', []) if isinstance(linkedin_data, dict) else linkedin_data
    twitter_posts = twitter_data.get('posts', []) if isinstance(twitter_data, dict) else twitter_data

    # 플랫폼 정규화 및 수집 순서 보존
    for p in threads_posts: 
        p['sns_platform'] = 'threads'
        p['platform_sequence_id'] = p.get('sequence_id', 0)
    for p in linkedin_posts: 
        p['sns_platform'] = 'linkedin'
        p['platform_sequence_id'] = p.get('sequence_id', 0)
    for p in twitter_posts: 
        p['sns_platform'] = 'x'
        p['platform_sequence_id'] = p.get('sequence_id', 0)

    # 중복 제거 (ID 기준)
    seen_ids = set()
    unique_posts = []
    all_posts = threads_posts + linkedin_posts + twitter_posts
    
    for p in all_posts:
        pid = str(p.get('platform_id') or p.get('id') or p.get('code') or p.get('url'))
        if pid not in seen_ids:
            unique_posts.append(p)
            seen_ids.add(pid)

    return unique_posts, len(threads_posts), len(linkedin_posts), len(twitter_posts)

def save_total(new_posts, threads_count, linkedin_count, twitter_count):
    today = datetime.now().strftime('%Y%m%d')
    total_filename = os.path.join(OUTPUT_TOTAL_DIR, f"total_full_{today}.json")
    validate_local_image_links(new_posts)
    
    # 💡 [개선] '저장순' 정렬 구현 (최초 수집 시점 1순위, 플랫폼 내 순서 2순위)
    def sort_key(post):
        # 1. 최초 수집 시점 (ISO 포맷 문자열 비교)
        # crawled_at이 없는 레거시 데이터는 timestamp/created_at으로 대체
        c_at = post.get('crawled_at') or post.get('created_at') or post.get('timestamp') or post.get('date') or '0000-00-00'
        # 2. 플랫폼 내부 저장 순서
        psid = post.get('platform_sequence_id', 0)
        return (c_at, psid)
        
    new_posts.sort(key=sort_key)
    
    # 전역 ID 재부여 및 순서 정렬
    final_ordered_posts = []
    for i, p in enumerate(new_posts):
        p['sequence_id'] = i + 1
        final_ordered_posts.append(reorder_post(p))

    os.makedirs(OUTPUT_TOTAL_DIR, exist_ok=True)
    
    total_data = {
        "metadata": {
            "updated_at": datetime.now().isoformat(),
            "max_sequence_id": len(final_ordered_posts),
            "total_count": len(final_ordered_posts),
            "threads_count": threads_count,
            "linkedin_count": linkedin_count,
            "twitter_count": twitter_count,
            "execution_mode": "parallel_multi_window"
        },
        "posts": final_ordered_posts
    }
    
    with open(total_filename, 'w', encoding='utf-8-sig') as f:
        json.dump(total_data, f, ensure_ascii=False, indent=4)
    print(f"\n🏁 Total Full 저장 완료: {total_filename} (총 {len(new_posts)}개)")
    
    # MD 변환
    convert_json_to_md(total_filename)

def download_images(posts):
    print("\n🖼️ 미수집 이미지 로컬 다운로드 시작...")
    os.makedirs(WEB_IMAGE_DIR, exist_ok=True)
    
    count = 0
    linked_existing = 0
    preserved = collect_preserved_local_images()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for post in posts:
        remote_media = post.get('media', [])
        if not remote_media: continue
            
        local_images = []
        seen_local_images = set()
        for existing_path in post.get('local_images') or []:
            if web_image_exists(existing_path) and existing_path not in seen_local_images:
                local_images.append(existing_path)
                seen_local_images.add(existing_path)

        for img_url in remote_media:
            if '.mp4' in img_url.lower(): continue
            try:
                preserved_path = preserved.get(img_url)
                if preserved_path and web_image_exists(preserved_path):
                    if preserved_path not in seen_local_images:
                        local_images.append(preserved_path)
                        seen_local_images.add(preserved_path)
                        linked_existing += 1
                    continue

                fs_path, web_path = get_local_image_paths(img_url)
                
                if not os.path.exists(fs_path):
                    curr_headers = headers.copy()
                    if 'licdn.com' in img_url: curr_headers = {"User-Agent": headers["User-Agent"]}
                    response = requests.get(img_url, headers=curr_headers, timeout=10)
                    if response.status_code == 200:
                        with open(fs_path, 'wb') as f:
                            f.write(response.content)
                        count += 1
                
                if os.path.exists(fs_path) and web_path not in seen_local_images:
                    local_images.append(web_path)
                    seen_local_images.add(web_path)
            except Exception: pass
        if local_images: post['local_images'] = local_images

    print(f"   ✅ 이미지 다운로드 완료: 신규 {count}개 저장, 기존 {linked_existing}개 연결됨.")


def run(mode='update'):
    platform_results = {}
    try:
        # 1. 병렬 실행 (새 창)
        platform_results = run_scrapers_in_parallel(mode=mode)

        # 2. 결과 병합
        merged_results_data = merge_results()

        if merged_results_data[0]:
            posts, threads_count, linkedin_count, twitter_count = merged_results_data
            # 3. 이미지 다운로드
            download_images(posts)
            # 4. 최종 저장 및 정규화
            save_total(posts, threads_count, linkedin_count, twitter_count)
    finally:
        auth_required = [
            platform
            for platform, result in platform_results.items()
            if result.get("status") == "auth_required"
        ]
        summary = {
            "platform_results": platform_results,
            "auth_required": auth_required,
        }
        print(f"SNS_SCRAP_SUMMARY {json.dumps(summary, ensure_ascii=False)}", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='통합 SNS 스크래퍼 (멀티 윈도우 병렬 모드)')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    args = parser.parse_args()
    run(mode=args.mode)
