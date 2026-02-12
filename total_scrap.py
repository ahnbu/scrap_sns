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

# Windows 터미널 인코딩 문제 해결을 위한 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OUTPUT_THREADS_DIR = "output_threads/python"
OUTPUT_LINKEDIN_DIR = "output_linkedin/python"
OUTPUT_TWITTER_DIR = "output_twitter/python"
OUTPUT_TOTAL_DIR = "output_total"

# CLI 인자 파싱
parser = argparse.ArgumentParser(description='통합 SNS 스크래퍼')
parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드 (all: 전체, update: 증분)')
args = parser.parse_args()

def load_json(path):
    if not path or not os.path.exists(path): return {}
    # utf-8-sig로 읽어 BOM 문제 방지
    with open(path, 'r', encoding='utf-8-sig') as f:
        try:
            return json.load(f)
        except Exception as e:
            print(f"   [Error] Failed to load JSON from {path}: {e}")
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
    print(f"   [Pass 1] Producer 실행: thread_scrap.py --mode {mode}")
    subprocess.run(["python", "thread_scrap.py", "--mode", mode])

    # 2단계: Consumer 실행 (상세 수집 및 자동 통합)
    print("   [Pass 2] Consumer 실행: thread_scrap_single.py")
    subprocess.run(["python", "thread_scrap_single.py"])

    # 3단계: 기타 스크래퍼 순차/병렬 실행
    # LinkedIn은 병렬로 실행
    linkedin_p = subprocess.Popen(["python", "linkedin_scrap.py", "--mode", mode])
    
    # X(Twitter)는 Producer-Consumer 파이프라인으로 순차 실행
    print(f"   [X/Twitter] 1단계: twitter_scrap.py (목록 확보)")
    subprocess.run(["python", "twitter_scrap.py", "--mode", mode])
    
    print(f"   [X/Twitter] 2단계: twitter_scrap_single.py (상세 타래 수집)")
    subprocess.run(["python", "twitter_scrap_single.py"])
    
    # LinkedIn 완료 대기
    print("LinkedIn 스크래퍼 완료 대기 중...")
    linkedin_p.wait()
    print("모든 스크래퍼 실행 완료.")


def merge_results():
    print("\n결과 병합 중...")
    
    latest_threads = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_full_*.json")
    latest_linkedin = find_latest_full_file(OUTPUT_LINKEDIN_DIR, "linkedin_python_full_*.json")
    latest_twitter = find_latest_full_file(OUTPUT_TWITTER_DIR, "twitter_py_full_*.json")
    
    if not latest_threads or not latest_linkedin:
        print("필수 Full 파일을 찾을 수 없어 병합할 수 없습니다.")
        return None, 0, 0, 0

    print(f"   Threads 파일: {os.path.basename(latest_threads)}")
    print(f"   LinkedIn 파일: {os.path.basename(latest_linkedin)}")
    if latest_twitter:
        print(f"   Twitter 파일: {os.path.basename(latest_twitter)}")

    threads_data = load_json(latest_threads)
    linkedin_data = load_json(latest_linkedin)
    twitter_data = load_json(latest_twitter) if latest_twitter else {}
    
    # 표준화된 posts 키에서 데이터 추출
    threads_posts = threads_data.get('posts', []) if isinstance(threads_data, dict) else threads_data
    linkedin_posts = linkedin_data.get('posts', []) if isinstance(linkedin_data, dict) else linkedin_data
    twitter_posts = twitter_data.get('posts', []) if isinstance(twitter_data, dict) else twitter_data

    # 플랫폼 고정 및 필드 정리
    for p in threads_posts: p['sns_platform'] = 'threads'
    for p in linkedin_posts: p['sns_platform'] = 'linkedin'
    for p in twitter_posts: p['sns_platform'] = 'x' # twitter -> x로 브랜드 통합

    # 중복 제거 (identifier 기준)
    seen_ids = set()
    unique_posts = []
    
    # 모든 플랫폼 데이터 통합
    all_posts = threads_posts + linkedin_posts + twitter_posts
    
    for p in all_posts:
        # 표준 id 필드 또는 url을 식별자로 사용
        identifier = str(p.get('id') or p.get('code') or p.get('url'))
        if identifier not in seen_ids:
            unique_posts.append(p)
            seen_ids.add(identifier)

    return unique_posts, len(threads_posts), len(linkedin_posts), len(twitter_posts)

def save_total(new_posts, threads_count, linkedin_count, twitter_count):
    today = datetime.now().strftime('%Y%m%d')
    total_filename = os.path.join(OUTPUT_TOTAL_DIR, f"total_full_{today}.json")
    
    # [정규화 로직] 전체 게시물을 날짜순으로 정렬하고 ID를 다시 부여합니다.
    def sort_key(post):
        return post.get('timestamp') or post.get('date') or post.get('created_at') or '0000-00-00'

    # 1. 날짜 오름차순 정렬 (과거 -> 현재)
    new_posts.sort(key=sort_key)
    
    # 2. Sequence ID 재할당 (전수 재조사)
    max_id = 0
    for i, p in enumerate(new_posts):
        max_id = i + 1
        p['sequence_id'] = max_id

    os.makedirs(OUTPUT_TOTAL_DIR, exist_ok=True)
    
    total_data = {
        "metadata": {
            "updated_at": datetime.now().isoformat(),
            "max_sequence_id": max_id,
            "total_count": len(new_posts),
            "threads_count": threads_count,
            "linkedin_count": linkedin_count,
            "twitter_count": twitter_count,
            "normalization": "full_reorder_by_date_v2"
        },
        "posts": new_posts
    }
    
    with open(total_filename, 'w', encoding='utf-8-sig') as f:
        json.dump(total_data, f, ensure_ascii=False, indent=4)
    print(f"Total Full 저장 완료: {total_filename} (총 {len(new_posts)}개, 전역 재정렬 완료)")
    
    # Markdown 자동 변환
    convert_json_to_md(total_filename)
    
    # 웹 뷰어 데이터 갱신
    try:
        data_js_path = os.path.join('web_viewer', 'data.js')
        js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"
        with open(data_js_path, 'w', encoding='utf-8-sig') as f:
            f.write(js_content)
        print(f"   🌐 web_viewer/data.js 자동 갱신 완료")
    except Exception as e:
        print(f"   data.js 갱신 실패: {e}")

import requests
import hashlib

def download_images(posts):
    print("\n이미지 로컬 다운로드 시작...")
    fs_img_dir = os.path.join("web_viewer", "images")
    os.makedirs(fs_img_dir, exist_ok=True)
    
    count = 0
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for post in posts:
        # 표준 media 필드 사용
        remote_media = post.get('media', []) or post.get('images', [])
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

    print(f"이미지 다운로드 완료: 신규 {count}개 저장됨.")


def run():
    # 1. 스크래퍼 순차 실행
    run_scrapers(mode=args.mode)

    # 2. 결과 병합
    print("\n최신 수집 데이터 기반 최종 병합을 시작합니다...")
    merged_results_data = merge_results()
    
    if merged_results_data[0]:
        posts, threads_count, linkedin_count, twitter_count = merged_results_data
        
        # 3. 이미지 다운로드
        download_images(posts)
        
        # 4. 최종 저장 및 정규화
        save_total(posts, threads_count, linkedin_count, twitter_count)

if __name__ == "__main__":
    run()
