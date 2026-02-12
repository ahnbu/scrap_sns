import json
import os
from collections import OrderedDict

def reorder_post(post):
    standard_order = [
        "sequence_id", "platform_id", "sns_platform", "username", "display_name",
        "full_text", "media", "url", "created_at", "date", "crawled_at",
        "source", "local_images"
    ]
    
    if "sns_platform" not in post:
        post["sns_platform"] = "linkedin"
    
    if "username" not in post:
        user_link = post.get("user_link", "")
        if "linkedin.com/in/" in user_link:
            post["username"] = user_link.split("/in/")[-1].split("?")[0]
        else:
            post["username"] = "unknown"

    if "date" not in post:
        created_at = post.get("created_at", "")
        if created_at and len(created_at) >= 10:
            post["date"] = created_at[:10]
        else:
            post["date"] = "unknown"

    if "media" not in post:
        post["media"] = []
        
    if "local_images" not in post:
        post["local_images"] = []

    new_post = OrderedDict()
    for field in standard_order:
        new_post[field] = post.get(field)
    
    for key in post:
        if key not in standard_order:
            new_post[key] = post[key]
            
    return new_post

def migrate_file(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    if "posts" in data:
        data["posts"] = [reorder_post(p) for p in data["posts"]]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("Successfully migrated.")
    else:
        print("No 'posts' key found.")

if __name__ == "__main__":
    migrate_file(r"D:\vibe-coding\scrap_sns\output_linkedin\python\linkedin_py_full_20260212.json")
