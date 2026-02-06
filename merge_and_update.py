import json
import os
import glob
from datetime import datetime

# 1. 최신 파일 자동 탐색
def find_latest(pattern):
    files = glob.glob(pattern)
    return max(files) if files else None

threads_file = find_latest("output_threads/python/threads_py_full_*.json")
linkedin_file = "output_linkedin/python/linkedin_python_full_20260206.json"

if not threads_file:
    print("❌ Threads 파일을 찾을 수 없습니다!")
    exit(1)

print(f"📂 Threads: {os.path.basename(threads_file)}")
print(f"📂 LinkedIn: {os.path.basename(linkedin_file)}")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

threads_data = load_json(threads_file)
linkedin_data = load_json(linkedin_file)

threads_posts = threads_data.get('posts', []) if isinstance(threads_data, dict) else threads_data
linkedin_posts = linkedin_data.get('posts', []) if isinstance(linkedin_data, dict) else linkedin_data

# 2. 플랫폼 구분 필드 추가
for p in threads_posts:
    p['sns_platform'] = 'threads'
for p in linkedin_posts:
    p['sns_platform'] = 'linkedin'

all_posts = threads_posts + linkedin_posts

print(f"✅ Threads: {len(threads_posts)}개")
print(f"✅ LinkedIn: {len(linkedin_posts)}개")
print(f"✅ Total: {len(all_posts)}개")
print(f"✅ LinkedIn 개행 확인: {any(chr(10) in p.get('full_text', '') for p in linkedin_posts if p.get('sns_platform') == 'linkedin')}")

# 3. Total 파일 생성
os.makedirs("output_total", exist_ok=True)
total_file = "output_total/total_full_20260206.json"

total_data = {
    "metadata": {
        "updated_at": datetime.now().isoformat(),
        "total_count": len(all_posts),
        "threads_count": len(threads_posts),
        "linkedin_count": len(linkedin_posts),
        "new_items_count": len(all_posts)
    },
    "posts": all_posts
}

with open(total_file, 'w', encoding='utf-8') as f:
    json.dump(total_data, f, ensure_ascii=False, indent=4)

print(f"💾 Total 파일 저장 완료: {total_file}")

# 4. data.js 생성
data_js_path = "web_viewer/data.js"
js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"

with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)

print(f"🌐 web_viewer/data.js 갱신 완료")
print(f"✅ 최종 개행 확인: {any(chr(10) in p.get('full_text', '') for p in all_posts if p.get('sns_platform') == 'linkedin')}")
