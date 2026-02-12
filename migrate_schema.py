import json
import os
import glob

# 표준 필드 순서 정의
STANDARD_FIELD_ORDER = [
    "sequence_id",
    "platform_id",
    "sns_platform",
    "username",
    "display_name",
    "full_text",
    "media",
    "url",
    "created_at",
    "date",
    "crawled_at",
    "source",
    "local_images"
]

def reorder_post(post):
    ordered_post = {}
    for field in STANDARD_FIELD_ORDER:
        if field in post:
            ordered_post[field] = post[field]
    
    for key, value in post.items():
        if key not in ordered_post:
            ordered_post[key] = value
            
    return ordered_post

def migrate_post(post, platform, index=None):
    # 1. 고유 ID 통합: platform_id
    if 'platform_id' not in post:
        val = post.get('id') or post.get('code')
        if val: post['platform_id'] = val
    
    # 2. 사용자 핸들 통합: username
    if 'username' not in post:
        val = post.get('user') or post.get('username')
        if val: post['username'] = val

    # 3. 사용자 이름 보정 (LinkedIn 특수 상황 대응)
    if platform == 'linkedin':
        if 'display_name' not in post and 'username' in post:
            post['display_name'] = post['username']
            if 'user' in post: post['username'] = post['user']

    # 4. 미디어 통합: media
    if 'media' not in post:
        val = post.get('images') or post.get('media')
        if val: post['media'] = val
    
    # 5. 날짜/시간 통합: created_at
    if 'created_at' not in post:
        val = post.get('timestamp') or post.get('created_at')
        if val: post['created_at'] = val

    # 6. URL 통합: url
    if 'url' not in post:
        val = post.get('post_url') or post.get('url') or post.get('source_url')
        if val: post['url'] = val

    # 7. sequence_id 보정 (누락된 경우 인덱스 기반으로 생성)
    if 'sequence_id' not in post or post['sequence_id'] is None:
        if index is not None:
            post['sequence_id'] = index

    # 8. 레거시 필드 강제 삭제 (Clean up)
    legacy_fields = ['id', 'code', 'user', 'images', 'post_url', 'timestamp', 'source_url']
    for field in legacy_fields:
        if field in post:
            if field == 'user' and 'username' in post: post.pop(field)
            elif field == 'images' and 'media' in post: post.pop(field)
            elif field == 'post_url' and 'url' in post: post.pop(field)
            elif field == 'timestamp' and 'created_at' in post: post.pop(field)
            elif field == 'code' and 'platform_id' in post: post.pop(field)
            elif field == 'id' and 'platform_id' in post: post.pop(field)
            elif field == 'source_url' and 'url' in post: post.pop(field)

    return reorder_post(post)

def migrate_file(filepath):
    print(f"🧹 Advanced Cleaning & ID Backfill: {filepath}")
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        try:
            data = json.load(f)
        except:
            print(f"   ❌ Failed to load {filepath}")
            return

    posts = []
    is_meta_struct = False
    if isinstance(data, dict) and 'posts' in data:
        posts = data['posts']
        is_meta_struct = True
    elif isinstance(data, list):
        posts = data
    
    platform = 'unknown'
    if 'twitter' in filepath.lower() or '/x/' in filepath.lower(): platform = 'x'
    elif 'threads' in filepath.lower(): platform = 'threads'
    elif 'linkedin' in filepath.lower(): platform = 'linkedin'

    # sequence_id가 없는 파일(Simple)의 경우, 역순 정렬된 상태를 가정하고 
    # 전체 개수부터 1까지 거꾸로 ID 부여
    total_count = len(posts)
    new_posts = []
    for i, post in enumerate(posts):
        # index: 최신글이 큰 번호를 가지도록 (total_count - i)
        current_platform = post.get('sns_platform', platform).lower()
        new_posts.append(migrate_post(post, current_platform, index=(total_count - i)))

    if is_meta_struct:
        data['posts'] = new_posts
        # 메타데이터의 max_sequence_id도 보정
        if 'metadata' in data:
            data['metadata']['max_sequence_id'] = max([p.get('sequence_id', 0) for p in new_posts], default=0)
    else:
        data = new_posts

    with open(filepath, 'w', encoding='utf-8-sig') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"   ✅ Fixed.")

def main():
    target_dirs = [
        "output_twitter/python/*.json",
        "output_twitter/python/update/*.json",
        "output_threads/python/*.json",
        "output_threads/python/update/*.json",
        "output_linkedin/python/*.json",
        "output_linkedin/python/update/*.json",
        "output_total/*.json"
    ]
    
    for pattern in target_dirs:
        files = glob.glob(pattern)
        for f in files:
            migrate_file(f)
            
    # data.js 특수 처리 (JSON 마이그레이션 결과 반영 후 실행 권장)
    print(f"🧹 Please run 'total_scrap.py' logic or manual sync to update data.js with ID-filled data.")

if __name__ == "__main__":
    main()
