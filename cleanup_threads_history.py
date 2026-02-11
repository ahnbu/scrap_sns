import json
import os
import glob

def cleanup_file(file_path):
    print(f"Checking {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        is_dict = isinstance(data, dict)
        posts = data.get('posts', []) if is_dict else data
        
        if not posts:
            return
            
        seen_codes = set()
        unique_posts = []
        duplicate_count = 0
        
        for p in posts:
            code = str(p.get('code'))
            if code not in seen_codes:
                unique_posts.append(p)
                seen_codes.add(code)
            else:
                duplicate_count += 1
        
        if duplicate_count > 0:
            print(f"  -> Found {duplicate_count} duplicates. Cleaning up...")
            if is_dict:
                data['posts'] = unique_posts
                if 'metadata' in data:
                    data['metadata']['total_count'] = len(unique_posts)
                    data['metadata']['historical_cleanup'] = True
            else:
                data = unique_posts
                
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"  -> Successfully cleaned {file_path}")
        else:
            print(f"  -> No duplicates found.")
            
    except Exception as e:
        print(f"  -> Error processing {file_path}: {e}")

if __name__ == "__main__":
    threads_dir = "output_threads/python"
    json_files = glob.glob(os.path.join(threads_dir, "threads_py_*.json"))
    
    for f_path in json_files:
        cleanup_file(f_path)
    
    print("Cleanup process completed.")