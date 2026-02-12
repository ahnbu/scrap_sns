import json
import os

# 수정할 파일 목록
files = [
    r"d:\vibe-coding\scrap_sns\output_twitter\python\twitter_py_full_20260212.json",
    r"d:\vibe-coding\scrap_sns\output_twitter\python\twitter_py_simple_full_20260212.json"
]

for filepath in files:
    if not os.path.exists(filepath):
        print(f"⏩ 파일 없음: {filepath}")
        continue
    
    print(f"📂 처리 중: {os.path.basename(filepath)}")
    
    # UTF-8로 읽기
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    # source 필드 업데이트
    updated_count = 0
    for post in data.get('posts', []):
        if post.get('source') == 'full_twitter_scan':
            post['source'] = 'full_tweet_scan'
            updated_count += 1
    
    # UTF-8로 쓰기 (ensure_ascii=False 필수)
    with open(filepath, 'w', encoding='utf-8-sig') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"   ✅ {updated_count}개 항목 업데이트 완료")

print("\n✨ 모든 파일 업데이트 완료!")
