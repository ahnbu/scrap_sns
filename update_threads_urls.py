import json
import glob
import os

# 대상 파일 패턴들
TARGET_PATTERNS = [
    "output_threads/python/threads_py_simple_full_*.json",
    "output_threads/python/threads_py_full_*.json",
    "output_total/total_full_*.json",
    "web_viewer/data.js"
]

def update_urls(file_path):
    print(f"Processing: {file_path}")
    if not os.path.exists(file_path):
        print(f"  -> File not found: {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        data = None
        is_js = file_path.endswith('.js')
        js_prefix = "const snsFeedData = "
        
        # 1. 포맷에 따라 파싱
        if is_js:
            if content.startswith(js_prefix):
                json_str = content[len(js_prefix):].strip()
                # 끝에 세미콜론이 있을 수 있음 (rstrip으로 안전하게 제거)
                if json_str.endswith(";"):
                    json_str = json_str.rstrip(";")
                data = json.loads(json_str)
            else:
                print(f"Skipping {file_path}: JS prefix mismatch")
                return
        else:
            data = json.loads(content)
        
        # 2. 데이터 순회 및 수정
        modified_count = 0
        posts = []

        is_dict_wrapper = False
        # 'posts' 키가 있는 경우 (data.js나 total_full 등)
        if isinstance(data, dict) and "posts" in data:
            posts = data["posts"]
            is_dict_wrapper = True
        # 리스트인 경우
        elif isinstance(data, list):
            posts = data
        else:
            print(f"Skipping {file_path}: Unknown structure")
            return

        for post in posts:
            code = post.get('code')
            username = post.get('username')
            sns_platform = post.get('sns_platform')
            
            # code와 username이 있고, post_url 필드가 존재하는 경우에만
            # sns_platform이 'threads'인지 확인 (없으면 일단 진행하되, url 형태 보고 판단 가능하지만 여기선 강제)
            # 안전하게 기존 url이 threads.net 인지도 확인하면 더 좋음
            
            if code and username and 'post_url' in post:
                # 이미 변경된 포맷인지 확인
                current_url = post.get('post_url')
                new_url = f"https://www.threads.com/@{username}/post/{code}"
                
                # 기존 URL이 threads.net을 포함하거나, 새 URL과 다른 경우 업데이트
                # 단, 다른 플랫폼(instagram 등)은 건드리지 않도록 주의. 
                # 여기서는 파일명과 문맥상 threads 데이터라고 가정하지만, data.js에는 섞여 있을 수 있음.
                
                is_threads = False
                if sns_platform == 'threads':
                    is_threads = True
                elif 'threads.net' in current_url:
                    is_threads = True
                
                if is_threads and current_url != new_url:
                    post['post_url'] = new_url
                    modified_count += 1
        
        # 3. 변경 사항 저장
        if modified_count > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                if is_js:
                    json_dump = json.dumps(data, ensure_ascii=False, indent=2)
                    f.write(f"{js_prefix}{json_dump};") # 세미콜론 복구
                else:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"  -> Updated {modified_count} URLs")
        else:
            print(f"  -> No changes needed")

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Base Dir: {base_dir}")
    
    for pattern in TARGET_PATTERNS:
        full_pattern = os.path.join(base_dir, pattern)
        # glob 패턴에 슬래시/백슬래시 문제가 있을 수 있으므로 표준화
        full_pattern = full_pattern.replace("/", os.sep)
        
        # 파일이 직접 지정된 경우 (data.js)와 와일드카드인 경우를 모두 처리
        if '*' in full_pattern:
            files = glob.glob(full_pattern)
        else:
            files = [full_pattern] if os.path.exists(full_pattern) else []
            
        print(f"Pattern: {full_pattern} -> Found {len(files)} files")
        
        for file_path in files:
            update_urls(file_path)

if __name__ == "__main__":
    main()
