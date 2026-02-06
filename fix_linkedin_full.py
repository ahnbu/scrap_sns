import json
import os
from datetime import datetime

# 최신 update 파일 읽기
update_file = "output_linkedin/python/update/linkedin_python_update_20260206_183836.json"
with open(update_file, 'r', encoding='utf-8') as f:
    posts = json.load(f)

print(f"✅ Update 파일 로드 완료: {len(posts)}개")
print(f"   개행 문자 포함 확인: {any(chr(10) in p.get('full_text', '') for p in posts)}")

# Full 파일 생성
full_file = "output_linkedin/python/linkedin_python_full_20260206.json"
full_data = {
    "metadata": {
        "version": "1.0",
        "crawled_at": datetime.now().isoformat(),
        "total_count": len(posts),
        "max_sequence_id": max(p.get("sequence_id", 0) for p in posts),
        "first_code": posts[0]["code"] if posts else None,
        "last_code": posts[-1]["code"] if posts else None,
        "crawl_mode": "all",
        "legacy_data_count": 0,
        "verified_data_count": len(posts),
        "merge_history": [{
            "merged_at": datetime.now().isoformat(),
            "new_items_count": len(posts),
            "duplicates_removed": 0,
            "source_file": "linkedin_python_update_20260206_183836.json",
            "crawl_mode": "manual_fix"
        }]
    },
    "posts": posts
}

with open(full_file, 'w', encoding='utf-8') as f:
    json.dump(full_data, f, ensure_ascii=False, indent=2)

print(f"💾 Full 파일 갱신 완료: {full_file}")
print(f"   개행 문자 포함 확인: {any(chr(10) in p.get('full_text', '') for p in full_data['posts'])}")
