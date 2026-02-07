import json
import os
import glob
from datetime import datetime

def merge_linkedin_data():
    main_file = r"output_linkedin_user/gb-jeong/python/linkedin_python_full_20260207.json"
    temp_dir = r"output_linkedin_user/temp"
    output_file = r"output_linkedin_user/gb-jeong/python/linkedin_python_full_20260207_total.json"
    
    all_files = []
    if os.path.exists(main_file):
        all_files.append(main_file)
    
    temp_files = glob.glob(os.path.join(temp_dir, "*.json"))
    all_files.extend(temp_files)
    
    if not all_files:
        print("Target files not found.")
        return

    merged_data_dict = {}
    stats = []
    total_raw_count = 0

    print("Starting merge...")
    
    for file_path in all_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            posts = []
            if isinstance(data, dict):
                posts = data.get("posts", [])
            elif isinstance(data, list):
                posts = data
            
            file_count = len(posts)
            total_raw_count += file_count
            
            new_added = 0
            for post in posts:
                code = post.get("code")
                if code:
                    if code not in merged_data_dict:
                        new_added += 1
                    merged_data_dict[code] = post
            
            stats.append({
                "file": os.path.basename(file_path),
                "count": file_count,
                "new_added": new_added
            })
            print(f"Loaded {os.path.basename(file_path)}: {file_count} items")
            
        except Exception as e:
            print(f"Error processing {os.path.basename(file_path)}: {e}")

    final_posts = list(merged_data_dict.values())
    final_posts.sort(key=lambda x: x.get("code", ""), reverse=True)
    
    for i, post in enumerate(reversed(final_posts)):
        post["sequence_id"] = i + 1
    
    result = {
        "metadata": {
            "version": "1.0_total",
            "merged_at": datetime.now().isoformat(),
            "total_count": len(final_posts),
            "source_files_count": len(all_files),
            "raw_total_count": total_raw_count,
            "duplicate_removed": total_raw_count - len(final_posts)
        },
        "posts": final_posts
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print("Merge Summary")
    print("-" * 50)
    for s in stats:
        print(f"{s['file']:40} | Count: {s['count']:4} | New: {s['new_added']:4}")
    print("-" * 50)
    print(f"Total Raw Count: {total_raw_count}")
    print(f"Duplicates Removed: {total_raw_count - len(final_posts)}")
    print(f"Final Merged Count: {len(final_posts)}")
    print(f"Saved to: {output_file}")
    print("="*50 + "\n")

if __name__ == "__main__":
    merge_linkedin_data()