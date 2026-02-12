import json
import os

FILE_PATH = 'output_twitter/python/twitter_py_simple_20260212.json'
# 중복된 텍스트의 핵심 부분만 사용
DUP_KEYWORD = "이게 현실임"

def clean_duplicates():
    if not os.path.exists(FILE_PATH):
        print(f"❌ 파일을 찾을 수 없습니다: {FILE_PATH}")
        return

    try:
        with open(FILE_PATH, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 파일 로드 실패: {e}")
        return
    
    posts = data.get('posts', [])
    fix_count = 0
    
    for p in posts:
        txt = p.get('full_text', '')
        if txt and DUP_KEYWORD in txt and len(txt) > 100:
            # 중복된 긴 텍스트 발견! 
            p['full_text'] = "[Deduplication Reset] " + txt[:50] + "..."
            p['is_detail_collected'] = False
            p['source'] = 'reset_for_fix'
            fix_count += 1
            print(f"✅ Reset ID: {p.get('platform_id')} | URL: {p.get('url')}")

    if fix_count > 0:
        with open(FILE_PATH, 'w', encoding='utf-8-sig') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\n✨ 총 {fix_count}개의 중복 항목을 초기화했습니다. 이제 twitter_scrap_single.py를 실행하면 정상 수집될 것입니다.")
    else:
        print("🔍 중복된 항목을 찾지 못했습니다.")

if __name__ == "__main__":
    clean_duplicates()
