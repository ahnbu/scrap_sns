import json
from datetime import datetime
from urllib.parse import urlparse
from utils.common import format_timestamp

def extract_json_from_html(html_content):
    """Robustly extracts specific JSON data from Threads HTML"""
    if "thread_items" not in html_content: return None
    ti_idx = html_content.find("thread_items")
    
    # Threads has various markers depending on the version
    marker = '"result":{"data"'
    idx = html_content.rfind(marker, 0, ti_idx)
    if idx == -1: return None
    
    # Find the start of the JSON object (the first '{' after the marker)
    start_obj = html_content.find('{', idx + len(marker) - 5) # Look around "data" area
    if start_obj == -1: return None
    
    brace_count = 0
    json_str = ""
    for i in range(start_obj, len(html_content)):
        char = html_content[i]
        if char == '{': brace_count += 1
        elif char == '}': brace_count -= 1
        json_str += char
        if brace_count == 0 and char == '}': break
    
    try: 
        # result is a dictionary that contains "data" or similar
        return json.loads(json_str)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return None

def find_master_pk_recursive(data, username):
    """Recursively search the user pk matching URL username."""
    if not username:
        return None
    if isinstance(data, dict):
        if data.get("username") == username:
            return data.get("pk")
        for v in data.values():
            res = find_master_pk_recursive(v, username)
            if res:
                return res
    elif isinstance(data, list):
        for item in data:
            res = find_master_pk_recursive(item, username)
            if res:
                return res
    return None

def extract_posts_from_node(node, target_code, master_pk):
    """Extract posts from a node with author consistency filters."""
    if not isinstance(node, dict):
        return []

    thread_items = node.get("thread_items", [])
    if thread_items:
        posts_to_process = [item.get("post", {}) for item in thread_items]
    else:
        post = node.get("post") or node
        posts_to_process = [post]

    if not posts_to_process:
        return []

    root_post = posts_to_process[0]
    root_user_pk = root_post.get("user", {}).get("pk")
    if not root_post.get("code"):
        return []

    extracted = []
    for i, post in enumerate(posts_to_process):
        if not isinstance(post, dict):
            continue
        code = post.get("code")
        if not code:
            continue

        current_user_pk = post.get("user", {}).get("pk")
        if master_pk and current_user_pk != master_pk:
            continue
        if root_user_pk and current_user_pk != root_user_pk:
            continue

        if i > 0:
            text_post_app_info = post.get("text_post_app_info", {})
            reply_to_author_id = text_post_app_info.get("reply_to_author", {}).get("id")
            if reply_to_author_id and root_user_pk and reply_to_author_id != root_user_pk:
                continue

        user = post.get("user", {})
        username = user.get("username")
        created_at, created_date = format_timestamp(post.get("taken_at"))
        extracted.append({
            "platform_id": code,
            "code": code,
            "root_code": target_code,
            "username": username,
            "display_name": user.get("full_name") or username,
            "full_text": post.get("caption", {}).get("text", ""),
            "media": [c.get("url") for c in post.get("image_versions2", {}).get("candidates", [])[:1] if c.get("url")],
            "url": f"https://www.threads.net/@{username}/post/{code}" if username else "",
            "created_at": created_at,
            "date": created_date,
            "sns_platform": "threads",
            "source": "consumer_detail",
            "pk": post.get("pk"),
            "taken_at": post.get("taken_at"),
        })
    return extracted

def extract_items_multi_path(data, target_code, username):
    """
    Fallback extraction path for Threads payload:
    1) data.data.data.thread_items (Direct API)
    2) data.result.data.data.thread_items (Embedded in HTML)
    """
    if not isinstance(data, dict):
        return []

    # Try various root paths
    inner_data = None
    if "result" in data:
        inner_data = data.get("result", {}).get("data", {}).get("data")
    elif "data" in data:
        # Could be data.data.data or just data.data
        d = data.get("data", {})
        if "data" in d:
            inner_data = d.get("data")
        else:
            inner_data = d

    if not isinstance(inner_data, dict):
        # Last resort: use data itself if it contains thread_items
        if "thread_items" in data:
            inner_data = data
        else:
            return []

    master_pk = find_master_pk_recursive(data, username)
    extracted = []

    thread_items = inner_data.get("thread_items")
    if isinstance(thread_items, list) and thread_items:
        extracted.extend(extract_posts_from_node(inner_data, target_code, master_pk))

    edges = inner_data.get("edges")
    if isinstance(edges, list):
        for edge in edges:
            extracted.extend(extract_posts_from_node(edge.get("node", {}), target_code, master_pk))

    containing_thread = inner_data.get("containing_thread")
    if isinstance(containing_thread, dict):
        extracted.extend(extract_posts_from_node(containing_thread, target_code, master_pk))

    dedup = {}
    for item in extracted:
        dedup[item.get("code")] = item
    return [v for v in dedup.values() if v.get("code")]
