import subprocess
import time
import os
import sys
import glob
import json
import argparse
from datetime import datetime
import io
from utils.json_to_md import convert_json_to_md

# Windows 터미널 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OUTPUT_THREADS_DIR = "output_threads/python"
OUTPUT_LINKEDIN_DIR = "output_linkedin/python"
OUTPUT_TWITTER_DIR = "output_twitter/python"
OUTPUT_TOTAL_DIR = "output_total"

# CLI 인자 파싱
parser = argparse.ArgumentParser(description='통합 SNS 스크래퍼 (멀티 윈도우 병렬 모드)')
parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
args = parser.parse_args()

def load_json(path):
    if not path or not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8-sig') as f:
        try: return json.load(f)
        except: return {}

def reorder_post(post):
    STANDARD_FIELD_ORDER = [
        "sequence_id", "platform_id", "sns_platform", "username", "display_name",
        "full_text", "media", "url", "created_at", "date", "crawled_at", "source", "local_images"
    ]
    ordered_post = {}
    for field in STANDARD_FIELD_ORDER:
        if field in post: ordered_post[field] = post[field]
    for key, value in post.items():
        if key not in ordered_post: ordered_post[key] = value
    return ordered_post

def find_latest_full_file(directory, pattern):
    files = glob.glob(os.path.join(directory, pattern))
    if not files: return None
    files.sort(reverse=True)
    return files[0]

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
        with open(failure_file, 'r', encoding='utf-8') as f:
            try: failures = json.load(f)
            except: pass
            
    final_targets = [p for p in uncollected if failures.get(str(p.get('platform_id') or p.get('id') or p.get('code')), {}).get('count', 0) < 3]
    
    return len(final_targets) > 0

def run_scrapers_in_parallel(mode='update'):
    print(f"🚀 플랫폼별 스크래퍼 병렬 실행 시작 (새 창에서 실행)... (모드: {mode})")
    
    CREATE_NEW_CONSOLE = 0x00000010
    
    # 💡 실행 여부 사전 판단
    run_threads_consumer = should_run_consumer("Threads")
    run_twitter_consumer = should_run_consumer("X/Twitter")
    
    commands = {
        "Threads": f"python thread_scrap.py --mode {mode}" + (" && python thread_scrap_single.py" if run_threads_consumer else ""),
        "X/Twitter": f"python twitter_scrap.py --mode {mode}" + (" && python twitter_scrap_single.py" if run_twitter_consumer else ""),
        "LinkedIn": f"python linkedin_scrap.py --mode {mode}"
    }
    
    processes = []
    for platform, cmd in commands.items():
        if platform == "Threads" and not run_threads_consumer:
            print(f"   [-] {platform}: 상세 수집할 항목 없음 (Producer만 실행)")
        if platform == "X/Twitter" and not run_twitter_consumer:
            print(f"   [-] {platform}: 상세 수집할 항목 없음 (Producer만 실행)")
            
        print(f"   [+] {platform} 스크래퍼 윈도우 생성 중...")
        p = subprocess.Popen(
            f"cmd /c title {platform} Scraper && {cmd}", 
            creationflags=CREATE_NEW_CONSOLE
        )
        processes.append((platform, p))
        
    print(f"\n⏳ 총 {len(processes)}개의 프로세스가 완료되기를 기다리는 중...")
    print("   (각 창에서 수집이 완료되면 자동으로 닫힙니다.)")
    
    # 모든 프로세스가 완료될 때까지 대기
    for platform, p in processes:
        p.wait()
        print(f"   ✅ {platform} 수집 완료.")

    print("\n모든 플랫폼 스크래핑이 종료되었습니다.")


def merge_results():
    print("\n📦 결과 병합 및 데이터 정규화 시작...")
    
    latest_threads = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_full_*.json")
    latest_linkedin = find_latest_full_file(OUTPUT_LINKEDIN_DIR, "linkedin_py_full_*.json")
    latest_twitter = find_latest_full_file(OUTPUT_TWITTER_DIR, "twitter_py_full_*.json")
    
    if not latest_threads or not latest_linkedin:
        print("❌ 필수 Full 파일을 찾을 수 없어 병합할 수 없습니다.")
        return None, 0, 0, 0

    print(f"   - Threads: {os.path.basename(latest_threads)}")
    print(f"   - LinkedIn: {os.path.basename(latest_linkedin)}")
    if latest_twitter:
        print(f"   - X/Twitter: {os.path.basename(latest_twitter)}")

    threads_data = load_json(latest_threads)
    linkedin_data = load_json(latest_linkedin)
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
    
    # MD 변환 및 JS 갱신
    convert_json_to_md(total_filename)
    try:
        data_js_path = os.path.join('web_viewer', 'data.js')
        js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"
        with open(data_js_path, 'w', encoding='utf-8-sig') as f:
            f.write(js_content)
        print(f"   🌐 web_viewer/data.js 갱신 완료")
    except Exception as e:
        print(f"   data.js 갱신 실패: {e}")

import requests
import hashlib

def download_images(posts):
    print("\n🖼️ 미수집 이미지 로컬 다운로드 시작...")
    fs_img_dir = os.path.join("web_viewer", "images")
    os.makedirs(fs_img_dir, exist_ok=True)
    
    count = 0
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for post in posts:
        remote_media = post.get('media', [])
        if not remote_media: continue
            
        local_images = []
        for img_url in remote_media:
            if '.mp4' in img_url.lower(): continue
            try:
                ext = '.jpg'
                if '.png' in img_url.lower(): ext = '.png'
                elif '.webp' in img_url.lower(): ext = '.webp'
                
                file_hash = hashlib.md5(img_url.encode('utf-8')).hexdigest()
                filename = f"{file_hash}{ext}"
                fs_path = os.path.join(fs_img_dir, filename)
                web_path = f"web_viewer/images/{filename}"
                
                if not os.path.exists(fs_path):
                    curr_headers = headers.copy()
                    if 'licdn.com' in img_url: curr_headers = {"User-Agent": headers["User-Agent"]}
                    response = requests.get(img_url, headers=curr_headers, timeout=10)
                    if response.status_code == 200:
                        with open(fs_path, 'wb') as f:
                            f.write(response.content)
                        count += 1
                
                if os.path.exists(fs_path):
                    local_images.append(web_path)
            except: pass
        if local_images: post['local_images'] = local_images

    print(f"   ✅ 이미지 다운로드 완료: 신규 {count}개 저장됨.")


def run():
    # 1. 병렬 실행 (새 창)
    run_scrapers_in_parallel(mode=args.mode)

    # 2. 결과 병합
    merged_results_data = merge_results()
    
    if merged_results_data[0]:
        posts, threads_count, linkedin_count, twitter_count = merged_results_data
        # 3. 이미지 다운로드
        download_images(posts)
        # 4. 최종 저장 및 정규화
        save_total(posts, threads_count, linkedin_count, twitter_count)

if __name__ == "__main__":
    run()
