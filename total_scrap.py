import subprocess
import time
import os
import sys
import glob
import json
from datetime import datetime
import io

# Windows 터미널 인코딩 문제 해결을 위한 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OUTPUT_THREADS_DIR = "output_threads/python"
OUTPUT_LINKEDIN_DIR = "output_linkedin/python"
OUTPUT_TOTAL_DIR = "output_total"

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

def run_scrapers():
    print("🚀 병렬 스크래퍼 실행 시작...")
    
    # 실행 명령어 정의
    scrapers = [
        ["python", "threads_scrap.py"],
        ["python", "linkedin_scrap.py"]
    ]
    
    processes = []
    for cmd in scrapers:
        print(f"   ▶️ 실행 중: {' '.join(cmd)}")
        p = subprocess.Popen(cmd)
        processes.append(p)
        
    print(f"⏳ {len(processes)}개의 스크래퍼가 완료되기를 기다리는 중...")
    for p in processes:
        p.wait()
    print("✅ 모든 스크래퍼 실행 완료.")

def merge_results():
    print("\n🔄 결과 병합 중...")
    
    latest_threads = find_latest_full_file(OUTPUT_THREADS_DIR, "threads_py_full_*.json")
    latest_linkedin = find_latest_full_file(OUTPUT_LINKEDIN_DIR, "linkedin_python_full_*.json")
    
    if not latest_threads or not latest_linkedin:
        print("⚠️ Full 파일을 찾을 수 없어 병합할 수 없습니다.")
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
        print(f"   📉 이전 Total 파일 로드: {os.path.basename(prev_total_file)}")
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
    print(f"💾 Total Full 저장 완료: {total_filename} (총 {len(new_posts)}개, Threads: {threads_count}, LinkedIn: {linkedin_count})")
    
    if new_items:
        update_dir = os.path.join(OUTPUT_TOTAL_DIR, "update")
        os.makedirs(update_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        update_filename = os.path.join(update_dir, f"total_update_{timestamp}.json")
        
        with open(update_filename, 'w', encoding='utf-8') as f:
            json.dump(new_items, f, ensure_ascii=False, indent=4)
        print(f"✨ 업데이트 저장 완료: {update_filename} (신규 {len(new_items)}개)")
    else:
        print("   이번 실행에서 새로운 업데이트가 없습니다.")

    # 4. 웹 뷰어용 data.js 자동 갱신 (CORS 문제 해결 및 로컬 실행 지원)
    data_js_path = os.path.join("web_viewer", "data.js")
    try:
        # JSON 데이터 로드 (위의 total_data를 재사용하면 좋지만, 함수 구조상 다시 구성)
        js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"
        
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        print(f"   🌐 web_viewer/data.js 자동 갱신 완료")
    except Exception as e:
        print(f"   ⚠️ data.js 갱신 실패: {e}")

def run():
    run_scrapers()
    merged_results_data = merge_results()
    if merged_results_data[0]:
        save_total(merged_results_data[0], merged_results_data[1], merged_results_data[2])

if __name__ == "__main__":
    run()
