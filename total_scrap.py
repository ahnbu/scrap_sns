import subprocess
import time
import os
import sys
import glob
import json
import argparse
from datetime import datetime
import io

# Windows 터미널 인코딩 문제 해결을 위한 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OUTPUT_THREADS_DIR = "output_threads/python"
OUTPUT_LINKEDIN_DIR = "output_linkedin/python"
OUTPUT_TOTAL_DIR = "output_total"

# CLI 인자 파싱
parser = argparse.ArgumentParser(description='통합 SNS 스크래퍼')
parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드 (all: 전체, update: 증분)')
args = parser.parse_args()

def load_json(path):
    if not path or not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {}

def find_latest_full_file(directory, pattern):
    files = glob.glob(os.path.join(directory, pattern))
    if not files: return None
    # 파일명으로 정렬 (YYYYMMDD가 파일명에 포함되어 있다고 가정)
    files.sort(reverse=True)
    return files[0]

def run_scrapers(mode='update'):
    print(f"병렬 스크래퍼 실행 시작... (모드: {mode})")
    
    # 1단계: Producer 실행 (URL 목록 확보)
    print(f"   [Pass 1] Producer 실행: threads_scrap.py --mode {mode}")
    subprocess.run(["python", "threads_scrap.py", "--mode", mode])

    # 2단계: Consumer 실행 (상세 수집 및 자동 통합)
    # scrap_single_post.py는 내부적으로 promote 및 sync_to_total까지 수행함
    print("   [Pass 2] Consumer 실행: scrap_single_post.py")
    subprocess.run(["python", "scrap_single_post.py"])

    # 3단계: 기타 스크래퍼 병렬 실행 (LinkedIn 등)
    scrapers = [
        ["python", "linkedin_scrap.py", "--mode", mode]
    ]
    
    processes = []
    for cmd in scrapers:
        print(f"   실행 중: {' '.join(cmd)}")
        p = subprocess.Popen(cmd)
        processes.append(p)
        
    print(f"{len(processes)}개의 스크래퍼가 완료되기를 기다리는 중...")
    for p in processes:
        p.wait()
    print("모든 스크래퍼 실행 완료.")


def merge_results():
    print("\n결과 병합 중...")
    
    latest_threads = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_full_*.json")
    latest_linkedin = find_latest_full_file(OUTPUT_LINKEDIN_DIR, "linkedin_python_full_*.json")
    
    if not latest_threads or not latest_linkedin:
        print("Full 파일을 찾을 수 없어 병합할 수 없습니다.")
        return None, 0, 0

    print(f"   Threads 파일: {os.path.basename(latest_threads)}")
    print(f"   LinkedIn 파일: {os.path.basename(latest_linkedin)}")

    threads_data = load_json(latest_threads)
    linkedin_data = load_json(latest_linkedin)
    
    threads_posts = threads_data.get('posts', []) if isinstance(threads_data, dict) else threads_data
    linkedin_posts = linkedin_data.get('posts', []) if isinstance(linkedin_data, dict) else linkedin_data

    # 플랫폼 구분 필드(sns_platform) 추가
    for p in threads_posts:
        p['sns_platform'] = 'threads'
    for p in linkedin_posts:
        p['sns_platform'] = 'linkedin'

    all_posts = threads_posts + linkedin_posts
    return all_posts, len(threads_posts), len(linkedin_posts)

def save_total(new_posts, threads_count, linkedin_count):
    today = datetime.now().strftime('%Y%m%d')
    total_filename = os.path.join(OUTPUT_TOTAL_DIR, f"total_full_{today}.json")
    
    prev_total_file = find_latest_full_file(OUTPUT_TOTAL_DIR, "total_full_*.json")
    
    prev_codes = set()
    if prev_total_file:
        print(f"   이전 Total 파일 로드: {os.path.basename(prev_total_file)}")
        prev_data = load_json(prev_total_file)
        prev_posts_list = prev_data.get('posts', []) if isinstance(prev_data, dict) else prev_data
        for p in prev_posts_list:
            if 'code' in p:
                prev_codes.add(str(p['code']))
    
    new_items = []
    for p in new_posts:
        if str(p.get('code')) not in prev_codes:
            new_items.append(p)
            
    os.makedirs(OUTPUT_TOTAL_DIR, exist_ok=True)
    
    total_data = {
        "metadata": {
            "updated_at": datetime.now().isoformat(),
            "total_count": len(new_posts),
            "threads_count": threads_count,
            "linkedin_count": linkedin_count,
            "new_items_count": len(new_items)
        },
        "posts": new_posts
    }
    
    with open(total_filename, 'w', encoding='utf-8') as f:
        json.dump(total_data, f, ensure_ascii=False, indent=4)
    print(f"Total Full 저장 완료: {total_filename} (총 {len(new_posts)}개, Threads: {threads_count}, LinkedIn: {linkedin_count})")
    
    if new_items:
        update_dir = os.path.join(OUTPUT_TOTAL_DIR, "update")
        os.makedirs(update_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        update_filename = os.path.join(update_dir, f"total_update_{timestamp}.json")
        
        with open(update_filename, 'w', encoding='utf-8') as f:
            json.dump(new_items, f, ensure_ascii=False, indent=4)
        print(f"업데이트 저장 완료: {update_filename} (신규 {len(new_items)}개)")
    else:
        print("   이번 실행에서 새로운 업데이트가 없습니다.")

    try:
        data_js_path = os.path.join('web_viewer', 'data.js')
        # JSON 데이터 로드 (위의 total_data를 재사용하면 좋지만, 함수 구조상 다시 구성)
        js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"
        
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        print(f"   🌐 web_viewer/data.js 자동 갱신 완료")
    except Exception as e:
        print(f"   data.js 갱신 실패: {e}")

import requests
import hashlib

def download_images(posts):
    print("\n이미지 로컬 다운로드 시작...")
    
    # 이미지 저장 경로 (웹 뷰어 기준 relative path 사용을 위해 web_viewer 내부로 지정)
    # 실제 파일 시스템 경로: web_viewer/images (스크립트 실행 위치 기준)
    # 웹 접근 경로: images/filename.jpg
    fs_img_dir = os.path.join("web_viewer", "images")
    os.makedirs(fs_img_dir, exist_ok=True)
    
    count = 0
    total_images = sum(len(p.get('images', [])) for p in posts)
    
    # 헤더 설정 (403 방지)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.threads.net/"
    }

    processed = 0
    
    for post in posts:
        remote_images = post.get('images', [])
        if not remote_images: 
            continue
            
        local_images = []
        
        for img_url in remote_images:
            processed += 1
            # 비디오 제외 (mp4 등)
            if '.mp4' in img_url.lower():
                continue
                
            try:
                # 1. 고유 파일명 생성 (MD5)
                # URL에서 확장자 추출 시도, 없으면 jpg 가정
                ext = '.jpg'
                if '.png' in img_url.lower(): ext = '.png'
                elif '.webp' in img_url.lower(): ext = '.webp'
                elif '.jpeg' in img_url.lower(): ext = '.jpeg'
                
                # facebook/meta CDN URL은 만료시간 등 파라미터가 바뀌므로, URL 전체보다는 식별자 부분만 해싱하면 좋으나,
                # 간단하게 URL 전체 해싱 (중복 다운로드 좀 있어도 안전함)
                file_hash = hashlib.md5(img_url.encode('utf-8')).hexdigest()
                filename = f"{file_hash}{ext}"
                
                fs_path = os.path.join(fs_img_dir, filename)
                web_path = f"web_viewer/images/{filename}"
                
                # 2. 파일 존재 여부 확인
                if not os.path.exists(fs_path):
                    # 3. 다운로드
                    # print(f"   ⬇️ 다운로드: {filename} ({processed}/{total_images})", end="\r")
                    
                    # LinkedIn 이미지는 Referer 없이 요청해야 잘 될 때도 있음
                    curr_headers = headers.copy()
                    if 'licdn.com' in img_url:
                        curr_headers = {"User-Agent": headers["User-Agent"]}
                        
                    response = requests.get(img_url, headers=curr_headers, timeout=10)
                    if response.status_code == 200:
                        with open(fs_path, 'wb') as f:
                            f.write(response.content)
                        count += 1
                    else:
                        # 실패하면 원본 URL 사용 (local_images에 추가 X -> 프론트가 fallback)
                        # print(f"   ⚠️ 다운로드 실패({response.status_code}): {img_url}")
                        pass
                
                # 성공했거나 이미 있으면 로컬 경로 추가 (파일이 실제 있을 때만)
                if os.path.exists(fs_path):
                    local_images.append(web_path)
                    
            except Exception as e:
                # print(f"   ⚠️ 에러: {e}")
                pass
                
        # 포스트에 로컬 이미지 리스트 추가 (저장할 JSON에 포함됨)
        if local_images:
            post['local_images'] = local_images

    print(f"이미지 다운로드 완료: 신규 {count}개 저장됨.")


def run():
    # 1. 스크래퍼 순차 실행 (Producer -> Consumer -> Others)
    run_scrapers(mode=args.mode)

    # 2. 결과 병합 (스크래퍼가 업데이트한 최신 파일들을 다시 로드)
    print("\n최신 수집 데이터 기반 최종 병합을 시작합니다...")
    merged_results_data = merge_results()
    
    if merged_results_data[0]:
        posts, threads_count, linkedin_count = merged_results_data
        
        # 3. 이미지 다운로드 수행 (posts 객체를 직접 수정 - local_images 추가)
        download_images(posts)
        
        # 4. 최종 Total 파일 및 data.js 저장
        save_total(posts, threads_count, linkedin_count)

if __name__ == "__main__":
    run()
