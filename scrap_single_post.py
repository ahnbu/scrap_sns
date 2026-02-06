import asyncio
from playwright.async_api import async_playwright
import json
import time
import os
from datetime import datetime

# ==========================================
# 🧪 Test Configuration
# ==========================================
# Test Targets (Mix of single posts and split posts)
TEST_CODES = [
    "DUX8tp_EvRN", # bellman.pub (Normal)
    "DUZLMwvkojo", # specal1849 (Image)
    "DUOKKcfj4wK", # seulgi.kaang (Split Post - Key Verification Target)
    "DUTTMTDEoas", # keke_appa (Long text)
    "DUUBhjKgeKZ", # inner.builder (Normal)
    "DUUYhntk4Ey", # geumverse_ai (Normal)
]

OUTPUT_FILE = "docs/scrap_result_async_test.json"
PENDING_FILE = "pending_list.json"
AUTH_FILE = "auth/auth_threads.json"
CONCURRENCY_LIMIT = 3 # Number of parallel tabs

# 브라우저 설정
HEADLESS = False       # 브라우저 창을 보일지 여부 (차단 방지를 위해 False 권장)
WINDOW_X = 5000        # 화면 밖으로 보내서 사용자 방해 최소화 (Stealth 모드)
WINDOW_Y = 50
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 500

# ==========================================
# 🛠️ Utility Functions
# ==========================================
def format_timestamp(ts):
    if not ts: return None, None
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except:
        return None, None

def extract_json_from_html(html_content):
    """Robustly extracts specific JSON data from Threads HTML"""
    if "thread_items" not in html_content:
        return None

    ti_idx = html_content.find("thread_items")
    marker = '"result":{"data"'
    idx = html_content.rfind(marker, 0, ti_idx)
    
    if idx == -1:
        return None

    start_obj = idx + 9
    brace_count = 0
    json_str = ""
    
    # Balance braces to extract valid JSON
    for i in range(start_obj, len(html_content)):
        char = html_content[i]
        if char == '{': brace_count += 1
        elif char == '}': brace_count -= 1
        json_str += char
        if brace_count == 0 and char == '}':
            break
            
    try:
        return json.loads(json_str)
    except:
        return None

def find_master_pk_recursive(data, username):
    """Recursively search for the user pk matching the username"""
    if isinstance(data, dict):
        if data.get("username") == username:
            return data.get("pk")
        for v in data.values():
            res = find_master_pk_recursive(v, username)
            if res: return res
    elif isinstance(data, list):
        for item in data:
            res = find_master_pk_recursive(item, username)
            if res: return res
    return None

# ==========================================
# 🕷️ Core Scraping Logic (Per URL)
# ==========================================
async def process_network_post_async(node, master_pk, code):
    """Extracts post data from a node, applying strict author filtering"""
    if not node: return []

    local_collected = []
    
    # 1. Normalize Post List (Single vs Thread)
    posts_to_process = []
    thread_items = node.get("thread_items", [])
    
    if thread_items:
        posts_to_process = [item.get("post", {}) for item in thread_items]
    else:
        post = node.get("post") or node 
        posts_to_process = [post]

    if not posts_to_process: return []

    # 2. Identify Root Validity
    root_post = posts_to_process[0]
    root_code = root_post.get("code")
    root_user_pk = root_post.get("user", {}).get("pk")
    
    if not root_code: return []

    # 3. Iterate & Filter
    for i, post in enumerate(posts_to_process):
        p_code = post.get("code")
        if not p_code: continue

        # Filter: Author Match (Global & Local)
        current_user_pk = post.get("user", {}).get("pk")
        
        # Must match the URL's owner (Master PK)
        if master_pk and current_user_pk != master_pk:
            continue
            
        # Must match the Root Post's owner (Thread Consistency)
        if current_user_pk != root_user_pk:
            continue

        # Filter: Reply Target Match
        if i > 0:
            text_post_app_info = post.get("text_post_app_info", {})
            reply_to_author_id = text_post_app_info.get("reply_to_author", {}).get("id")
            if reply_to_author_id and reply_to_author_id != root_user_pk:
                continue

        # Extract Media
        images = []
        # (Simplified media extraction for verification - adds first image if any)
        if post.get("image_versions2", {}).get("candidates"):
            images.append(post["image_versions2"]["candidates"][0]["url"])

        # Extract Metadata
        user = post.get("user", {})
        caption = post.get("caption", {})
        created_at, time_text = format_timestamp(post.get("taken_at"))

        post_info = {
            "code": p_code,
            "root_code": root_code,
            "username": user.get("username"),
            "full_text": caption.get("text") if caption else "",
            "created_at": created_at,
            "images_count": len(images),
            "post_url": f"https://www.threads.net/t/{p_code}"
        }
        
        if post_info['full_text'] or images:
            local_collected.append(post_info)

    return local_collected

class Progress:
    total = 0
    current = 0
    lock = asyncio.Lock()

    @classmethod
    async def increment(cls):
        async with cls.lock:
            cls.current += 1
            return cls.current, cls.total

async def worker(context, semaphore, code, collected_data, results_lock):
    """Async worker for a single URL"""
    url = f"https://www.threads.net/t/{code}" # Redirects to clean URL usually
    
    async with semaphore:
        curr, total = await Progress.increment()
        percent = (curr / total) * 100 if total > 0 else 0
        page = await context.new_page()
        try:
            print(f"⏳ [{curr}/{total}] ({percent:.1f}%) [Start] {code}...")
            # Navigate
            await page.goto(url)
            await page.wait_for_timeout(3000) # Initial load
            
            # Scroll to trigger any lazy loading (for threads)
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(2000)
            
            # Extract HTML
            html_content = await page.content()
            data = extract_json_from_html(html_content)
            
            if not data:
                print(f"❌ [Fail] {code} - No data found in HTML")
                return

            # Determine Target User from HTML Data
            # (We don't strictly parsing the URL username here, but we could. 
            #  Instead, we try to find the author of the main post in the data)
            
            # Navigate to the relevant data section
            inner_data = None
            if "data" in data and "data" in data["data"]:
                inner_data = data["data"]["data"]
            
            if not inner_data:
                print(f"❌ [Fail] {code} - Invalid JSON structure")
                return

            extracted_items = []
            
            # Strategy: Find Content -> Process
            if "edges" in inner_data:
                # Iterate edges to find the one matching our requested code
                # Or just process all edges found (usually relevant to the page)
                edges = inner_data.get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    # Dynamic Master PK detection
                    # Ideally we want the username from the URL, but here we take the root user of the node
                    # A better way: Extract username from page URL if possible, or assume node owner
                    
                    # For safety, let's extract username from the URL the page is currently on
                    current_url = page.url
                    # https://www.threads.net/@username/post/CODE
                    try:
                        target_username = current_url.split("/@")[1].split("/")[0]
                        master_pk = find_master_pk_recursive(data, target_username)
                    except:
                        master_pk = None # Fallback (less strict)

                    items = await process_network_post_async(node, master_pk, code)
                    extracted_items.extend(items)

            elif "containing_thread" in inner_data:
                node = inner_data["containing_thread"]
                try:
                    target_username = page.url.split("/@")[1].split("/")[0]
                    master_pk = find_master_pk_recursive(data, target_username)
                except:
                    master_pk = None
                
                items = await process_network_post_async(node, master_pk, code)
                extracted_items.extend(items)
            
            if extracted_items:
                # 🔄 Force-group logic: 
                # All items found on this target page (and passing filtered) should belong to this target's group
                for item in extracted_items:
                    item['root_code'] = code

                print(f"✅ [Done] {code} - Captured {len(extracted_items)} items")
                async with results_lock:
                    collected_data.extend(extracted_items)
            else:
                print(f"⚠️ [Empty] {code} - Found data but no valid items extracted")

        except Exception as e:
            print(f"🔥 [Error] {code}: {e}")
        finally:
            await page.close()

def merge_thread_items(thread_items):
    """
    여러 개의 포스트(본문+답글)를 하나의 게시글 레코드로 병합합니다.
    - full_text: ' --- ' 구분자로 연결
    - images: 모든 이미지 URL 통합 및 중복 제거
    """
    if not thread_items: return None
    
    # 시간순 정렬 (이미 되어있겠지만 확인 차원)
    sorted_items = sorted(thread_items, key=lambda x: x.get('created_at', ''))
    
    root = sorted_items[0]
    merged_text_parts = []
    all_images = []
    
    for i, item in enumerate(sorted_items):
        text = item.get('full_text', '').strip()
        if text:
            # 첫 글이 아니면 구분자 추가
            if i > 0:
                merged_text_parts.append("\n\n---\n\n")
            merged_text_parts.append(text)
        
        # 이미지 통합
        all_images.extend(item.get('images', []))
    
    # 중복 제거 및 리스트 유지
    unique_images = []
    for img in all_images:
        if img not in unique_images:
            unique_images.append(img)
            
    # 병합된 레코드 생성 (ID와 기본 정보는 Root 기준)
    merged_post = root.copy()
    merged_post['full_text'] = "".join(merged_text_parts)
    merged_post['images'] = unique_images
    # 병합됨을 나타내는 플래그 (선택 사항)
    merged_post['is_merged_thread'] = True
    merged_post['original_item_count'] = len(sorted_items)
    
    return merged_post

def promote_to_full_history(grouped_data):
    """
    상세 수집된 데이터를 메인 threads_py_full_*.json 파일에 반영합니다.
    - 기존 얕은 데이터를 병합된 상세 데이터로 치환 (Replace & Expand)
    """
    base_dir = "output_threads/python"
    
    # 1. 최신 Full 파일 찾기
    import glob
    from datetime import datetime
    files = glob.glob(f"{base_dir}/threads_py_full_*.json")
    if not files:
        print("⚠️ [Promotion] 메인 Full 파일을 찾을 수 없습니다. 통합을 건너뜁니다.")
        return
    
    files.sort(key=lambda x: os.path.basename(x), reverse=True)
    latest_full_path = files[0]
    print(f"📂 [Promotion] 메인 DB 로드 중: {os.path.basename(latest_full_path)}")
    
    try:
        with open(latest_full_path, 'r', encoding='utf-8') as f:
            full_content = json.load(f)
    except Exception as e:
        print(f"❌ [Promotion] 파일 읽기 실패: {e}")
        return

    posts = full_content.get('posts', [])
    metadata = full_content.get('metadata', {})
    
    # 2. 치환 작업
    updated_count = 0
    new_posts = []
    
    # 매칭을 위한 맵 생성 (root_code -> merged_post)
    merge_map = {}
    for rc, items in grouped_data.items():
        merged = merge_thread_items(items)
        if merged:
            merge_map[rc] = merged

    for p in posts:
        code = p.get('code')
        if code in merge_map:
            # 치환! (기존 데이터의 sequence_id 등 핵심 메타 정보 유지)
            merged_data = merge_map[code]
            # ID와 수집시간 등은 기존 Full 데이터의 것을 유지하는 것이 뷰어 정렬에 유리함
            merged_data['sequence_id'] = p.get('sequence_id', merged_data.get('sequence_id'))
            merged_data['crawled_at'] = p.get('crawled_at', merged_data.get('crawled_at'))
            
            new_posts.append(merged_data)
            updated_count += 1
            print(f"🔄 [Promotion] 치환 완료: {code} ({merged_data['original_item_count']}개 결합됨)")
        else:
            new_posts.append(p)

    if updated_count == 0:
        print("✨ [Promotion] 업데이트할 게시글이 없습니다. (이미 최신이거나 대상 없음)")
        return

    # 3. 데이터 저장
    full_content['posts'] = new_posts
    
    # 메타데이터 업데이트 (Detailed Stats Calculation)
    total_posts = len(new_posts)
    merged_items = [p for p in new_posts if p.get('is_merged_thread') is True]
    multi_items = [p for p in merged_items if p.get('original_item_count', 0) > 1]
    single_items = [p for p in merged_items if p.get('original_item_count', 0) == 1]
    failed_items = [p for p in new_posts if not p.get('is_merged_thread')]
    
    # Max Sequence ID 재계산
    current_max_seq = max([p.get('sequence_id', 0) for p in new_posts]) if new_posts else 0

    full_content['metadata'].update({
        'integrated_at': datetime.now().isoformat(),
        'total_count': total_posts,
        'max_sequence_id': current_max_seq,
        'stats': {
            'merged': len(merged_items),
            'multi_thread': len(multi_items),
            'single_thread': len(single_items),
            'failed_or_pending': len(failed_items)
        }
    })
    
    # 원본 보존을 위해 새 파일로 저장하거나 덮어쓰기 (여기서는 덮어쓰기 권장/사용자 선택)
    # 안전을 위해 같은 파일에 덮어씁니다.
    with open(latest_full_path, 'w', encoding='utf-8') as f:
        json.dump(full_content, f, ensure_ascii=False, indent=4)
        
    print(f"✅ [Promotion] 총 {updated_count}개의 게시글이 타래글로 고도화되었습니다.")
    print(f"💾 파일 저장 완료: {latest_full_path}")

def import_from_simple_database():
    """Simple DB(목록)의 신규 데이터를 Full DB(상세)로 가져옵니다."""
    import glob
    
    # 1. 최신의 Simple Full 파일 찾기
    simple_files = glob.glob(os.path.join("output_threads/python", "threads_py_simple_full_*.json"))
    if not simple_files:
        print("⚠️ [Import] Simple 데이터가 없습니다.")
        return None
    simple_files.sort(reverse=True)
    with open(simple_files[0], 'r', encoding='utf-8') as f:
        simple_data = json.load(f)
    
    # 2. 최신의 Full 파일 찾기 (없으면 새로 생성 준비)
    full_dir = "output_threads/python"
    full_files = glob.glob(os.path.join(full_dir, "threads_py_full_*.json"))
    full_files.sort(reverse=True)
    
    latest_full_path = full_files[0] if full_files else os.path.join(full_dir, f"threads_py_full_{datetime.now().strftime('%Y%m%d')}.json")
    
    full_content = {"metadata": {"version": "1.0", "posts_count": 0}, "posts": []}
    if os.path.exists(latest_full_path):
        with open(latest_full_path, 'r', encoding='utf-8') as f:
            full_content = json.load(f)
            
    # 3. 데이터 병합 (Upsert)
    full_posts = full_content.get('posts', [])
    existing_full_codes = {p['code'] for p in full_posts}
    max_seq = max((p.get('sequence_id', 0) for p in full_posts), default=0)
    
    new_count = 0
    # Simple 데이터 중 없는 항목만 추가
    # 최신이 배열 앞에 오도록 Simple 데이터를 정렬(기존 순서 유지)한 후 역순으로 Sequence ID 부여
    new_items_to_add = []
    for p in simple_data.get('posts', []):
        if p['code'] not in existing_full_codes:
            new_item = p.copy()
            new_item['is_merged_thread'] = False
            new_items_to_add.append(new_item)
            new_count += 1
            
    if new_count > 0:
        # 신규 항목들에 대해 Sequence ID 부여 (역순: 최신이 큰 번호)
        for i, item in enumerate(new_items_to_add):
            item['sequence_id'] = max_seq + new_count - i
            full_posts.insert(0, item)
            
        full_content['posts'] = full_posts
        full_content['metadata']['total_count'] = len(full_posts)
        full_content['metadata']['updated_at'] = datetime.now().isoformat()
        
        with open(latest_full_path, 'w', encoding='utf-8') as f:
            json.dump(full_content, f, ensure_ascii=False, indent=4)
        print(f"✅ [Import] Simple에서 {new_count}개의 신규 데이터를 Full DB로 가져왔습니다. (Max Seq: {max_seq + new_count})")
    
    return latest_full_path

async def run():
    start_time = time.time()
    collected_data = []
    results_lock = asyncio.Lock()
    
    # 0. Simple -> Full 동기화
    latest_full_path = import_from_simple_database()
    
    async with async_playwright() as p:
        # 브라우저 실행 설정
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                f"--window-position={WINDOW_X},{WINDOW_Y}",
                f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"
            ]
        )
        
        # 인증 상태 로드 (auth_threads.json)
        storage_state = AUTH_FILE if os.path.exists(AUTH_FILE) else None
        context = await browser.new_context(
            viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT},
            storage_state=storage_state
        )

        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        
        # 1. 수집 대상 식별 (pending_list + 미수집 Full 항목)
        targets = []
        if os.path.exists(PENDING_FILE):
             with open(PENDING_FILE, 'r', encoding='utf-8') as f:
                 pending_data = json.load(f)
                 targets = [item['code'] for item in pending_data]
                 print(f"📂 [Queue] {len(targets)} targets loaded from {PENDING_FILE}")

        # 🔍 이미 상세 수집(Merged)된 항목은 제외하는 필터링 및 미수집 항목 추가
        final_targets = []
        try:
            if latest_full_path and os.path.exists(latest_full_path):
                with open(latest_full_path, 'r', encoding='utf-8') as f:
                    f_data = json.load(f)
                    
                    # Full DB에서 미수집된(False) 항목들도 수집 대상에 포함 (pending_list가 없을 대비)
                    unmerged_codes = [p['code'] for p in f_data.get('posts', []) if not p.get('is_merged_thread')]
                    
                    # 중복 없이 합치기
                    all_potential_targets = list(dict.fromkeys(targets + unmerged_codes))
                    
                    # 최종 필터링 (다시 한번 확인)
                    merged_codes = {p['code'] for p in f_data.get('posts', []) if p.get('is_merged_thread')}
                    final_targets = [t for t in all_potential_targets if t not in merged_codes]
                    
                    skip_count = len(all_potential_targets) - len(final_targets)
                    if skip_count > 0:
                        print(f"⏩ [Skip] 이미 상세 수집된 {skip_count}개의 게시물은 건너뜁니다.")
            else:
                final_targets = targets
        except Exception as e:
            print(f"⚠️ [Error] 대상 필터링 중 오류: {e}")
            final_targets = targets

        # 1차 시도 실행
        Progress.total = len(final_targets)
        Progress.current = 0
        tasks = [worker(context, semaphore, code, collected_data, results_lock) for code in final_targets]
        await asyncio.gather(*tasks)
        
        # 실패 건 식별 및 2차 시도 (Retry)
        scraped_codes = {item['root_code'] for item in collected_data}
        retry_targets = [c for c in final_targets if c not in scraped_codes]
        
        if retry_targets:
            print(f"\n⚠️ {len(retry_targets)}건 수집 실패. 2차 시도(재시도)를 시작합니다...")
            Progress.total = len(retry_targets)
            Progress.current = 0
            retry_tasks = [worker(context, semaphore, code, collected_data, results_lock) for code in retry_targets]
            await asyncio.gather(*retry_tasks)
        
        await browser.close()

    # Group results by root_code
    grouped_map = {}
    for item in collected_data:
        rc = item.get('root_code')
        if not rc: continue
        if rc not in grouped_map:
            grouped_map[rc] = []
        grouped_map[rc].append(item)
    
    # 1. 테스트용 결과물 저장 (Flat items)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # 이전에는 grouped 형태로 저장했으나, 
        # 이제 promotion이 메인이므로 여기는 백업/로그 성격으로 유지
        json.dump(collected_data, f, ensure_ascii=False, indent=4)

    # 2. 메인 DB 통합 (Promotion)
    print("\n🚀 메인 데이터베이스 통합(Promotion)을 시작합니다...")
    promote_to_full_history(grouped_map)

    # 3. 전체 데이터베이스 및 웹 뷰어 동기화 (Sync to Total & Web Viewer)
    print("\n🔄 전체 데이터베이스 및 웹 뷰어 동기화를 시작합니다...")
    sync_to_total_database()

    # 4. 최종 요약 출력
    print_final_summary()

    # 보고 작업
    duration = time.time() - start_time
    print(f"\n🏁 Finished in {duration:.2f} seconds")

def print_final_summary():
    """최종 수집 결과 요약을 출력합니다."""
    import glob
    base_dir = "output_threads/python"
    files = glob.glob(f"{base_dir}/threads_py_full_*.json")
    if not files:
        return
    files.sort(key=lambda x: os.path.basename(x), reverse=True)
    latest_full_path = files[0]
    
    try:
        with open(latest_full_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        posts = data.get('posts', [])
        total = len(posts)
        merged = [p for p in posts if p.get('is_merged_thread') == True]
        multi = [p for p in merged if p.get('original_item_count', 0) > 1]
        single = [p for p in merged if p.get('original_item_count', 0) == 1]
        failed = [p for p in posts if not p.get('is_merged_thread')]
        
        print("\n" + "="*40)
        print("📊 최종 수집 결과 요약")
        print(f"Total Threads Posts: {total}")
        print(f"Merged: {len(merged)} (Multi: {len(multi)}, Single: {len(single)})")
        print(f"Failed/Pending: {len(failed)}")
        print("="*40 + "\n")
    except Exception as e:
        print(f"⚠️ 요약 출력 중 에러 발생: {e}")

def sync_to_total_database():
    """Threads 전용 DB의 변경사항을 전체 통합 DB와 data.js에 반영합니다."""
    import glob
    
    # 1. 최신의 threads_py_full_*.json 로드
    threads_dir = "output_threads/python"
    threads_files = glob.glob(os.path.join(threads_dir, "threads_py_full_*.json"))
    if not threads_files:
        print("⚠️ [Sync] Threads Full 파일을 찾을 수 없습니다.")
        return
    threads_files.sort(reverse=True)
    with open(threads_files[0], 'r', encoding='utf-8') as f:
        threads_data = json.load(f)
    
    threads_posts_map = {p['code']: p for p in threads_data.get('posts', [])}
    
    # 2. 최신의 total_full_*.json 로드
    total_dir = "output_total"
    total_files = glob.glob(os.path.join(total_dir, "total_full_*.json"))
    if not total_files:
        print("⚠️ [Sync] 전체 통합 Full 파일을 찾을 수 없습니다.")
        return
    total_files.sort(reverse=True)
    latest_total_path = total_files[0]
    
    with open(latest_total_path, 'r', encoding='utf-8') as f:
        total_data = json.load(f)
    
    # 3. 데이터 업데이트 (Threads 플랫폼 항목만)
    updated_count = 0
    new_posts = []
    for p in total_data.get('posts', []):
        if p.get('sns_platform') == 'threads' or 'threads.net' in p.get('source_url', ''):
            code = p.get('code')
            if code in threads_posts_map:
                # 상세 정보가 업데이트된 항목으로 치환
                updated_post = threads_posts_map[code].copy()
                updated_post['sns_platform'] = 'threads' # 플랫폼 식별자 유지
                new_posts.append(updated_post)
                updated_count += 1
            else:
                new_posts.append(p)
        else:
            new_posts.append(p)
            
    if updated_count == 0:
        print("✨ [Sync] 업데이트할 전체 통합 데이터가 없습니다.")
        return

    total_data['posts'] = new_posts
    total_data['metadata']['integrated_at'] = datetime.now().isoformat()
    
    # 4. total_full_*.json 저장
    with open(latest_total_path, 'w', encoding='utf-8') as f:
        json.dump(total_data, f, ensure_ascii=False, indent=4)
    print(f"✅ [Sync] 전체 통합 DB 업데이트 완료: {latest_total_path} ({updated_count}개 갱신)")

    # 5. web_viewer/data.js 갱신
    try:
        data_js_path = os.path.join('web_viewer', 'data.js')
        js_content = "const snsFeedData = " + json.dumps(total_data, ensure_ascii=False, indent=2) + ";"
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        print(f"🌐 [Sync] web_viewer/data.js 갱신 완료")
    except Exception as e:
        print(f"⚠️ [Sync] data.js 갱신 실패: {e}")
    
    # ✅ 작업 완료 후 pending_list 비우기
    if os.path.exists(PENDING_FILE):
        os.remove(PENDING_FILE)
        print(f"🗑️ [Sync] 처리 완료된 {PENDING_FILE}을 삭제했습니다.")

if __name__ == "__main__":
    asyncio.run(run())
