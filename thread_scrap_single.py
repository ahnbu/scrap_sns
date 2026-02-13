import asyncio
from playwright.async_api import async_playwright
import json
import time
import os
import glob
from datetime import datetime
from urllib.parse import urlparse

# ==========================================
# ⚙️ Configuration
# ==========================================
OUTPUT_DIR = "output_threads/python"
SIMPLE_FILE_PATTERN = "threads_py_simple_*.json"
FULL_FILE_PATTERN = "threads_py_full_{date}.json"
FAILURES_FILE = "scrap_failures_threads.json"
AUTH_FILE = "auth/auth_threads.json"
CONCURRENCY_LIMIT = 3 # Number of parallel tabs

# 브라우저 설정
HEADLESS = False       # 브라우저 창을 보일지 여부
WINDOW_X = 5000        # 화면 밖으로 보내서 사용자 방해 최소화
WINDOW_Y = 50
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 500

# ==========================================
# 🛠️ Utility Functions
# ==========================================
def load_failures():
    if os.path.exists(FAILURES_FILE):
        with open(FAILURES_FILE, 'r', encoding='utf-8-sig') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_failures(failures):
    with open(FAILURES_FILE, 'w', encoding='utf-8') as f:
        json.dump(failures, f, ensure_ascii=False, indent=4)

def format_timestamp(ts):
    if not ts: return None, None
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except: return None, None

def get_post_code(post):
    """Legacy-safe code resolver for simple/full datasets."""
    code = post.get('code') or post.get('root_code') or post.get('platform_id')
    if code:
        return code

    url = post.get('url') or ""
    if url:
        try:
            path = urlparse(url).path.rstrip("/")
            # threads URL pattern: /@username/post/{code}
            if "/post/" in path:
                return path.split("/post/")[-1]
        except:
            pass
    return None

def extract_json_from_html(html_content):
    """Robustly extracts specific JSON data from Threads HTML"""
    if "thread_items" not in html_content: return None
    ti_idx = html_content.find("thread_items")
    marker = '"result":{"data"'
    idx = html_content.rfind(marker, 0, ti_idx)
    if idx == -1: return None
    start_obj = idx + 9
    brace_count = 0
    json_str = ""
    for i in range(start_obj, len(html_content)):
        char = html_content[i]
        if char == '{': brace_count += 1
        elif char == '}': brace_count -= 1
        json_str += char
        if brace_count == 0 and char == '}': break
    try: return json.loads(json_str)
    except: return None

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

        created_at, _ = format_timestamp(post.get("taken_at"))
        extracted.append({
            "code": code,
            "root_code": target_code,
            "user": post.get("user", {}).get("username"),
            "full_text": post.get("caption", {}).get("text", ""),
            "media": [c.get("url") for c in post.get("image_versions2", {}).get("candidates", [])[:1] if c.get("url")],
            "timestamp": created_at,
            "sns_platform": "threads"
        })
    return extracted

def extract_items_multi_path(data, target_code, username):
    """
    Fallback extraction path for Threads payload:
    1) data.data.thread_items
    2) data.data.edges[].node
    3) data.data.containing_thread
    """
    inner_data = data.get("data", {}).get("data")
    if not isinstance(inner_data, dict):
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

def merge_thread_items(thread_items):
    """Merges multiple posts from the same thread into one single post data object."""
    if not thread_items: return None
    sorted_items = sorted(thread_items, key=lambda x: x.get('taken_at', 0))
    root = sorted_items[0]
    merged_text = "\n\n---\n\n".join([item.get('full_text', '') for item in sorted_items if item.get('full_text')])
    all_media = []
    seen_media = set()
    for item in sorted_items:
        for m in item.get('media', []):
            if m not in seen_media:
                all_media.append(m)
                seen_media.add(m)
    
    merged_post = root.copy()
    merged_post['full_text'] = merged_text
    merged_post['media'] = all_media
    merged_post['is_merged_thread'] = True
    merged_post['original_item_count'] = len(sorted_items)
    return merged_post

def promote_to_full_history(grouped_data):
    """수집된 타래 데이터를 최신 Full DB 파일로 병합 및 승격시킵니다."""
    if not grouped_data: return
    
    today = datetime.now().strftime('%Y%m%d')
    latest_full_path = os.path.join(OUTPUT_DIR, FULL_FILE_PATTERN.format(date=today))
    
    if not os.path.exists(latest_full_path):
        latest_full_path = import_from_simple_database()
        
    if not latest_full_path or not os.path.exists(latest_full_path):
        print("❌ [Promotion] 메인 Full 파일을 찾을 수 없습니다.")
        return
    
    with open(latest_full_path, 'r', encoding='utf-8-sig') as f:
        full_content = json.load(f)

    posts = full_content.get('posts', [])
    merge_map = {}
    for rc, items in grouped_data.items():
        merged = merge_thread_items(items)
        if merged: merge_map[rc] = merged

    updated_count = 0
    new_posts = []
    max_sequence_id = full_content.get('metadata', {}).get('max_sequence_id', 0)

    for p in posts:
        code = p.get('code')
        if code in merge_map:
            merged_data = merge_map[code]
            # 💡 기존 메타데이터(sequence_id, crawled_at) 보존
            merged_data['sequence_id'] = p.get('sequence_id')
            merged_data['crawled_at'] = p.get('crawled_at')
            new_posts.append(merged_data)
            updated_count += 1
            
            sid = merged_data.get('sequence_id', 0)
            if sid > max_sequence_id: max_sequence_id = sid
        else:
            new_posts.append(p)

    if updated_count > 0:
        full_content['posts'] = new_posts
        full_content['metadata'].update({
            'updated_at': datetime.now().isoformat(),
            'total_count': len(new_posts),
            'max_sequence_id': max_sequence_id
        })
        with open(latest_full_path, 'w', encoding='utf-8-sig') as f:
            json.dump(full_content, f, ensure_ascii=False, indent=4)
        print(f"✅ [Promotion] {updated_count}개 타래 승격 완료: {os.path.basename(latest_full_path)} (max_sequence_id: {max_sequence_id})")

def import_from_simple_database():
    """Simple DB(목록)의 신규 데이터를 Full DB(상세)로 가져옵니다."""
    simple_files = glob.glob(os.path.join(OUTPUT_DIR, SIMPLE_FILE_PATTERN))
    if not simple_files: return None
    simple_files.sort(reverse=True)
    with open(simple_files[0], 'r', encoding='utf-8-sig') as f:
        simple_data = json.load(f)
    
    today = datetime.now().strftime('%Y%m%d')
    today_full_path = os.path.join(OUTPUT_DIR, FULL_FILE_PATTERN.format(date=today))
    
    full_files = glob.glob(os.path.join(OUTPUT_DIR, "threads_py_full_*.json"))
    full_files.sort(reverse=True)
    
    full_content = {"metadata": {"version": "1.0", "total_count": 0, "max_sequence_id": 0}, "posts": []}
    if os.path.exists(today_full_path):
        with open(today_full_path, 'r', encoding='utf-8-sig') as f:
            full_content = json.load(f)
    elif full_files:
        with open(full_files[0], 'r', encoding='utf-8-sig') as f:
            full_content = json.load(f)
            
    full_posts = full_content.get('posts', [])
    existing_codes = {c for p in full_posts if (c := get_post_code(p))}
    
    # Simple 파일에서 데이터 로드 시 메타데이터 포함 확인
    simple_posts = simple_data.get('posts', [])
    max_sequence_id = simple_data.get('metadata', {}).get('max_sequence_id', 0)
    
    if not max_sequence_id and simple_posts:
        max_sequence_id = max((p.get('sequence_id', 0) for p in simple_posts), default=0)

    new_items = []
    for p in simple_posts:
        code = get_post_code(p)
        if not code:
            continue
        if code not in existing_codes:
            new_item = p.copy()
            new_item['code'] = code
            new_item['is_merged_thread'] = False
            new_items.append(new_item)
            
    if new_items:
        # 💡 [개선] 이미 simple 파일에서 sequence_id가 부여되어 있으므로, 
        # 새로 계산하지 않고 그대로 가져오되 max_sequence_id만 갱신
        for item in new_items:
            full_posts.insert(0, item)
            sid = item.get('sequence_id', 0)
            if sid > max_sequence_id: max_sequence_id = sid
            
        full_content['posts'] = full_posts
        full_content['metadata']['total_count'] = len(full_posts)
        full_content['metadata']['max_sequence_id'] = max_sequence_id
        
        with open(today_full_path, 'w', encoding='utf-8-sig') as f:
            json.dump(full_content, f, ensure_ascii=False, indent=4)
        print(f"✅ [Import] {len(new_items)}개 목록 가져옴: {os.path.basename(today_full_path)} (max_sequence_id: {max_sequence_id})")
    
    return today_full_path

def sync_detail_collected_flags(simple_path, full_path):
    """Synchronize is_detail_collected flags from simple DB to full DB."""
    if not simple_path or not full_path:
        return 0
    if not os.path.exists(simple_path) or not os.path.exists(full_path):
        return 0

    with open(simple_path, 'r', encoding='utf-8-sig') as f:
        simple_data = json.load(f)
    with open(full_path, 'r', encoding='utf-8-sig') as f:
        full_data = json.load(f)

    simple_posts = simple_data.get('posts', [])
    full_posts = full_data.get('posts', [])

    simple_done_codes = set()
    simple_changed = 0
    for p in simple_posts:
        code = get_post_code(p)
        if not code:
            continue
        if not p.get('code'):
            p['code'] = code
            simple_changed += 1
        if p.get('is_detail_collected') is True:
            simple_done_codes.add(code)

    full_changed = 0
    for p in full_posts:
        code = get_post_code(p)
        if not code:
            continue
        if code in simple_done_codes and p.get('is_detail_collected') is not True:
            p['is_detail_collected'] = True
            full_changed += 1

    if simple_changed > 0:
        with open(simple_path, 'w', encoding='utf-8-sig') as f:
            json.dump(simple_data, f, ensure_ascii=False, indent=4)

    if full_changed > 0:
        full_data['posts'] = full_posts
        full_data.setdefault('metadata', {})
        full_data['metadata']['updated_at'] = datetime.now().isoformat()
        with open(full_path, 'w', encoding='utf-8-sig') as f:
            json.dump(full_data, f, ensure_ascii=False, indent=4)

    return full_changed

class Progress:
    total = 0
    current = 0

async def worker(context, semaphore, code, username, results, lock):
    async with semaphore:
        url = f"https://www.threads.net/@{username}/post/{code}"
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            html = await page.content()
            data = extract_json_from_html(html)
            if data:
                items = extract_items_multi_path(data, code, username)
                async with lock:
                    for item in items:
                        results.append(item)
                if items:
                    Progress.current += 1
                    percent = int((Progress.current / Progress.total) * 100)
                    print(f"   ✅ 수집 완료: [{code}] ({Progress.current}/{Progress.total}, {percent}%)")
                else:
                    print(f"   ⚠️ 수집 실패(추출 0건): [{code}]")
            else:
                print(f"   ⚠️ 수집 실패(JSON 없음): [{code}]")
        except: print(f"   ❌ 수집 실패: [{code}]")
        finally: await page.close()

async def run():
    start_time = time.time()
    collected_data = []
    results_lock = asyncio.Lock()
    
    latest_full_path = import_from_simple_database()
    failures = load_failures()
    simple_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, SIMPLE_FILE_PATTERN)), reverse=True)
    latest_simple = simple_files[0] if simple_files else None

    synced = sync_detail_collected_flags(latest_simple, latest_full_path)
    if synced > 0:
        print(f"[Sync] 상세 수집 상태 {synced}개를 full DB에 동기화했습니다.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=[f"--window-position={WINDOW_X},{WINDOW_Y}"])
        storage_state = AUTH_FILE if os.path.exists(AUTH_FILE) else None
        context = await browser.new_context(viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}, storage_state=storage_state)
        
        target_codes = []
        skipped_done = 0
        skipped_invalid = 0
        skipped_fail_limit = 0
        if latest_full_path and os.path.exists(latest_full_path):
            with open(latest_full_path, 'r', encoding='utf-8-sig') as f:
                full_data = json.load(f)
                for p in full_data.get('posts', []):
                    code = get_post_code(p)
                    if not code:
                        skipped_invalid += 1
                        continue
                    if p.get('is_merged_thread'):
                        continue
                    if p.get('is_detail_collected') is True:
                        skipped_done += 1
                        continue
                    if failures.get(code, {}).get('fail_count', 0) >= 3:
                        skipped_fail_limit += 1
                        continue
                    target_codes.append({'code': code, 'username': p.get('user') or p.get('username')})

        print(
            f"[Target] 수집대상 {len(target_codes)}개 | "
            f"기수집 스킵 {skipped_done}개 | 코드없음 스킵 {skipped_invalid}개 | "
            f"실패한도 스킵 {skipped_fail_limit}개"
        )
        
        if target_codes:
            Progress.total = len(target_codes)
            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
            tasks = [worker(context, semaphore, t['code'], t['username'], collected_data, results_lock) for t in target_codes]
            await asyncio.gather(*tasks)
        else:
            print("✨ 수집할 새로운 타래가 없습니다.")
        await browser.close()

    scraped_codes = {item['root_code'] for item in collected_data}
    for code in scraped_codes:
        if code in failures: del failures[code]
    for t in target_codes:
        if t['code'] not in scraped_codes:
            f = failures.get(t['code'], {"fail_count": 0})
            f['fail_count'] += 1
            failures[t['code']] = f
    save_failures(failures)

    grouped = {}
    for item in collected_data:
        rc = item['root_code']
        if rc not in grouped: grouped[rc] = []
        grouped[rc].append(item)
    
    promote_to_full_history(grouped)
    
    # Simple 파일 상태 업데이트
    if latest_simple and os.path.exists(latest_simple):
        with open(latest_simple, 'r', encoding='utf-8-sig') as f:
            simple_data = json.load(f)
        simple_marked = 0
        for p in simple_data.get('posts', []):
            code = get_post_code(p)
            if code in scraped_codes and p.get('is_detail_collected') is not True:
                p['is_detail_collected'] = True
                simple_marked += 1
            if code and not p.get('code'):
                p['code'] = code
        with open(latest_simple, 'w', encoding='utf-8-sig') as f:
            json.dump(simple_data, f, ensure_ascii=False, indent=4)
        if simple_marked > 0:
            print(f"[Update] simple DB 상세수집 완료 {simple_marked}개 반영")
        synced_after = sync_detail_collected_flags(latest_simple, latest_full_path)
        if synced_after > 0:
            print(f"[Sync] 실행 후 full DB 상세수집 상태 {synced_after}개 반영")

    duration = time.time() - start_time
    print(f"\n🏁 Finished in {duration:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(run())
