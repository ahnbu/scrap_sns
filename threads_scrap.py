"""
Threads 저장 게시글 수집기 v9 (크롤링 범위 설정 기능 추가)
- TARGET_LIMIT 변수로 수집 개수 제한 가능
- 제한 개수에 도달하면 즉시 수집 종료 및 저장
- CRAWL_MODE 설정:
  * "all": 처음부터 끝까지 전체 수집
  * "update only": 최신 full 버전의 최상단 code까지만 수집 (증분 업데이트)
- Full 버전 자동 병합 및 관리
"""

from playwright.sync_api import sync_playwright
import json
import time
import re
import os
import glob
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.local')

# 브라우저 UI 설정
WINDOW_X = 5000           # 화면 가로 위치 (모니터 왼쪽 기준 px)
WINDOW_Y = 0           # 화면 세로 위치 (모니터 위쪽 기준 px)
WINDOW_WIDTH = 900     # 브라우저 너비
WINDOW_HEIGHT = 500    # 브라우저 높이

# ===========================
# ⚙️ 설정 (여기만 수정하세요)
# ===========================
OUTPUT_DIR = "output_threads/python"
# 수집 완료 후 저장될 파일명 (임시 - 증분 업데이트 파일)
OUTPUT_FILE = f"{OUTPUT_DIR}/update/threads_py_simple_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
AUTH_FILE = "auth/auth_threads.json"
THREADS_ID = os.getenv("THREADS_ID")
THREADS_PW = os.getenv("THREADS_PW")

# ✨ 테스트용 제한 개수 (0으로 설정하면 제한 없이 끝까지 수집)
TARGET_LIMIT = 0  # 테스트용으로 5개만 수집

# 🔄 크롤링 범위 설정 (CLI 인자로 받음)
# - "all": 처음부터 끝까지 전체 수집
# - "update": 최신 full 버전의 최상단 code까지만 수집 (신규 게시물만)
parser = argparse.ArgumentParser(description='Threads 스크래퍼')
parser.add_argument('--mode', choices=['all', 'update'], default='all', help='크롤링 모드 (all: 전체, update: 증분)')
args = parser.parse_args()
CRAWL_MODE = "update only" if args.mode == "update" else "all"

# ===========================

def clean_text(full_text, username):
    lines = full_text.split('\n')
    cleaned_lines = []
    
    if lines and lines[0].strip() == username:
        lines.pop(0)

    date_patterns = [
        r'^\d+시간$', r'^\d+분$', r'^\d+일$', 
        r'^\d{4}-\d{2}-\d{2}$', r'^\d+주$', 
        r'^AI Threads$', r'^수정됨$'
    ]
    
    is_body_started = False
    for line in lines:
        line = line.strip()
        if not line: continue
            
        is_metadata = False
        for pattern in date_patterns:
            if re.match(pattern, line):
                is_metadata = True
                break
        
        if not is_body_started and is_metadata: continue
        if not is_metadata: is_body_started = True
            
        if is_body_started:
            if re.match(r'^\d+$', line) or re.match(r'^\d+/\d+$', line): continue
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()

def format_timestamp(ts):
    """Unix timestamp를 YYYY-MM-DD HH:MM:SS 형식과 YYYY-MM-DD 형식으로 변환"""
    if not ts: return None, None
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except:
        return None, None

def parse_relative_time(relative_str, base_time):
    """
    "1주", "3일", "5시간" 등 상대적 시간을 절대 시간 문자열로 변환
    """
    if not relative_str: return None, None
    
    # 이미 절대 날짜인 경우 (예: 2024-01-01)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', relative_str):
        return f"{relative_str} 00:00:00", relative_str

    match = re.search(r'(\d+)\s*(분|시간|일|주|개월|년)', relative_str)
    if not match: return None, None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == "분": delta = timedelta(minutes=value)
    elif unit == "시간": delta = timedelta(hours=value)
    elif unit == "일": delta = timedelta(days=value)
    elif unit == "주": delta = timedelta(weeks=value)
    elif unit == "개월": delta = timedelta(days=value * 30)
    elif unit == "년": delta = timedelta(days=value * 365)
    else: return None, None
    
    target_time = base_time - delta
    return target_time.strftime('%Y-%m-%d %H:%M:%S'), target_time.strftime('%Y-%m-%d')

def find_latest_simple_file():
    """output 폴더에서 최신 threads_py_simple_full_*.json 파일 찾기"""
    pattern = f"{OUTPUT_DIR}/threads_py_simple_full_*.json"
    files = glob.glob(pattern)
    
    if not files:
        return None
    
    # 파일명에서 날짜 추출 후 정렬
    file_info = []
    for file in files:
        match = re.search(r'_simple_full_(\d{8})', file)
        if match:
            date_str = match.group(1)
            mtime = os.path.getmtime(file)
            file_info.append((file, date_str, mtime))
    
    # 날짜 최신순, 그 다음 수정시간 최신순 정렬
    file_info.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    return file_info[0][0] if file_info else None

def update_simple_version(new_data, stop_code, crawl_start_time):
    """
    기존 Simple Full 파일을 읽어와서 신규 데이터와 병합한 후,
    오늘 날짜로 새로운 Simple Full 파일 생성 (메타데이터 포함)
    """
    today = datetime.now().strftime('%Y%m%d')
    today_simple = f"{OUTPUT_DIR}/threads_py_simple_full_{today}.json"
    
    # 1. 오늘 날짜 Simple Full 파일이 이미 있는지 확인
    if os.path.exists(today_simple):
        print(f"\n⚠️ 오늘 날짜의 Simple Full 파일이 이미 존재합니다: {today_simple}")
        print(f"   기존 파일을 최신 버전으로 사용하여 병합합니다.")
        latest_simple = today_simple
    else:
        latest_simple = find_latest_simple_file()
    
    # 2. 기존 Simple 파일 읽기
    existing_posts = []
    existing_merge_history = []
    source_filename = None
    
    if latest_simple:
        print(f"📂 기존 Simple 파일 로드: {latest_simple}")
        source_filename = os.path.basename(latest_simple)
        
        with open(latest_simple, 'r', encoding='utf-8') as f:
            existing_content = json.load(f)
            
            # 메타데이터 구조인지 확인
            if isinstance(existing_content, dict) and 'posts' in existing_content:
                existing_posts = existing_content['posts']
                if 'metadata' in existing_content and 'merge_history' in existing_content['metadata']:
                    existing_merge_history = existing_content['metadata']['merge_history']
            else:
                existing_posts = existing_content
    else:
        # [Backfill] Simple 파일이 없으면 Thread Full 파일에서 역으로 가져오기
        print("🔍 [Backfill] Simple 파일이 없어 Thread Full 파일에서 기초 목록을 생성합니다...")
        thread_full_files = glob.glob(f"{OUTPUT_DIR}/threads_py_full_*.json")
        if thread_full_files:
            thread_full_files.sort(reverse=True)
            latest_thread_full = thread_full_files[0]
            try:
                with open(latest_thread_full, 'r', encoding='utf-8') as f:
                    full_content = json.load(f)
                    full_posts = full_content.get('posts', [])
                    # 상세 정보는 빼고 기초 정보만 Simple로 변환
                    for p in full_posts:
                        simple_item = {
                            "code": p['code'],
                            "username": p.get('username'),
                            "full_text": p.get('full_text', '')[:100] + "...", # 스니펫화
                            "created_at": p.get('created_at'),
                            "post_url": p.get('post_url'),
                            "source": "backfill_from_full"
                        }
                        existing_posts.append(simple_item)
                print(f"✅ {len(existing_posts)}개의 과거 항목을 Thread Full에서 Simple Full로 복구했습니다.")
            except Exception as e:
                print(f"⚠️ Backfill 실패: {e}")
        else:
            print("⚠️ 기존 Simple 및 Thread Full 파일 없음 - 현재 결과를 Simple로 저장")

    # 중복 제거 및 병합
    existing_codes = {post['code'] for post in existing_posts}
    new_items = [p for p in new_data if p['code'] not in existing_codes]
    duplicate_count = len(new_data) - len(new_items)
    
    merged_posts = new_items + existing_posts
    if new_items:
        print(f"✅ Simple 병합 완료: {len(new_items)}개 신규 추가 + {len(existing_posts)}개 기존 = {len(merged_posts)}개")
    elif not existing_posts:
        print(f"✅ 초기 Simple 생성: {len(merged_posts)}개 저장 예정")
    
    # 메타데이터 및 저장
    now = datetime.now().isoformat()
    metadata = {
        "version": "1.0",
        "crawled_at": now,
        "total_count": len(merged_posts),
        "source_file_count": len(new_items),
        "merge_history": existing_merge_history + [{
            "merged_at": now,
            "new_items_count": len(new_items),
            "duplicates_removed": duplicate_count,
            "stop_code": stop_code
        }] if latest_simple and new_items else existing_merge_history
    }
    
    full_data = {"metadata": metadata, "posts": merged_posts}
    
    with open(today_simple, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=4)
    print(f"📦 Simple 버전 저장 완료: {today_simple}")
    return today_simple


def manage_login(context, page):
    print("🌐 Threads 저장 페이지 접속 시도...")
    try:
        page.goto("https://www.threads.net/saved")
        time.sleep(3)
    except:
        pass

    if "login" in page.url:
        print("⚠️ 로그인 필요. 자동 입력 시도...")
        if THREADS_ID and THREADS_PW:
            try:
                page.fill('input[name="username"]', THREADS_ID)
                time.sleep(1)
                page.fill('input[name="password"]', THREADS_PW)
                time.sleep(1)
                page.click('button[type="submit"]')
                print("⏳ 로그인 버튼 클릭함.")
            except Exception as e:
                print(f"⚠️ 자동 입력 실패: {e}")

        print("\n" + "="*60)
        print("🛑 [로그인 확인 필요]")
        print("   로그인을 완료하고 '저장됨' 페이지가 보이면 Enter를 누르세요.")
        print("="*60)
        input(">>> 로그인 완료 후 Enter 입력: ")

        print("💾 세션 저장 중...")
        context.storage_state(path=AUTH_FILE)
    else:
        print("✅ 자동 로그인 성공!")

def run():
    start_time_dt = datetime.now()
    collected_data = []
    stop_codes = []  # 중단 기준 code 리스트
    stop_code_found = False  # 중단 플래그
    crawl_start_time = start_time_dt.isoformat()  # 크롤링 시작 시간
    
    # "update only" 모드: 최신 Simple 파일의 최상단 code 가져오기
    if CRAWL_MODE == "update only":
        latest_simple = find_latest_simple_file()
        if latest_simple:
            try:
                with open(latest_simple, 'r', encoding='utf-8') as f:
                    full_data = json.load(f)
                    if full_data:
                        # 메타데이터 구조인지 확인
                        if isinstance(full_data, dict) and 'posts' in full_data:
                            posts = full_data['posts']
                        else:
                            # 레거시 구조
                            posts = full_data
                        
                        if posts:
                            # 최신순 5개 추출 (삭제 방지용 징검다리 전략)
                            stop_codes = [p['code'] for p in posts[:5]]
                            print(f"🔄 UPDATE ONLY 모드: {stop_codes} 중 하나라도 발견 시 수집을 중단합니다.")
            except Exception as e:
                print(f"⚠️ Simple 파일 읽기 실패: {e}")
        else:
            print("⚠️ Simple 파일 없음 - 전체 수집으로 전환")
 

    with sync_playwright() as p:
        print("🚀 브라우저 실행 중...")
        browser = p.chromium.launch(
            headless=False,
            args=[
                f"--window-position={WINDOW_X},{WINDOW_Y}",
                f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"
            ]
        )
        
        # viewport를 None으로 설정 (창 크기 따라감) 또는 고정
        context_opts = {
            "viewport": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}
        }
        
        if os.path.exists(AUTH_FILE):
            context_opts["storage_state"] = AUTH_FILE
            
        context = browser.new_context(**context_opts)

        page = context.new_page()

        manage_login(context, page)

        # -------------------------------------------------
        # 네트워크 핸들러
        # -------------------------------------------------
        def handle_response(response):
            # 목표 개수 도달 시 더 이상 처리하지 않음
            if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT:
                return

            if response.request.resource_type in ["xhr", "fetch"]:
                try:
                    if "graphql" in response.url or "query" in response.url:
                        json_data = response.json()
                        data_part = json_data.get("data", {})
                        if not data_part: return

                        # 구조 1: edges 방식 (xdt_text_app_viewer)
                        viewer = data_part.get("xdt_text_app_viewer") or data_part.get("viewer")
                        if viewer and viewer.get("saved_media"):
                            edges = viewer["saved_media"].get("edges", [])
                            if edges:
                                for edge in edges:
                                    if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT: break
                                    node = edge.get("node", {})
                                    if node: process_network_post(node)

                        # 구조 2: sections 방식 (최신 JS 방식)
                        saved_posts = data_part.get("text_post_app_user_saved_posts", {})
                        sections = saved_posts.get("sections", [])
                        if sections:
                            for section in sections:
                                items = section.get("items", [])
                                for item in items:
                                    if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT: break
                                    # item 자체를 넘겨야 thread_items 전체를 볼 수 있음
                                    process_network_post(item)
                except: pass

        def process_network_post(node):
            nonlocal stop_code_found
            if not node: return
            
            # 1. 포스트 목록 확보 (단일 포스트 or 스레드)
            posts_to_process = []
            
            # thread_items가 있는 경우 (스레드/답글 구조)
            thread_items = node.get("thread_items", [])
            if thread_items:
                posts_to_process = [item.get("post", {}) for item in thread_items]
            else:
                # 단일 포스트인 경우 (또는 node 자체가 post인 경우)
                # post 필드가 있으면 그걸 쓰고, 없으면 node 자체를 시도
                post = node.get("post") or node
                posts_to_process = [post]

            if not posts_to_process: return

            # 2. Root Post(첫 번째 글) 식별
            root_post = posts_to_process[0]
            root_code = root_post.get("code")
            root_user_pk = root_post.get("user", {}).get("pk")
            
            if not root_code: return

            # 3. 스레드 순회하며 수집
            for i, post in enumerate(posts_to_process):
                # 목표 개수 체크
                if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT: return

                code = post.get("code")
                if not code: continue

                # ⛔ UPDATE ONLY 모드: stop_codes 중 하나 발견 시 중단
                if stop_codes and code in stop_codes:
                    print(f"✋ 기준 게시물 발견! (code: {code}) - 크롤링 중단")
                    stop_code_found = True
                    return # 함수 종료
                
                # 이미 수집된 목록에 있는지 확인 (중복 방지)
                if any(p['code'] == code for p in collected_data):
                    continue

                # ==================================================
                # 🛡️ [필터링 로직] 작성자 및 답글 대상 검증
                # ==================================================
                current_user_pk = post.get("user", {}).get("pk")
                
                # 조건 1: 작성자가 Root 작성자와 동일해야 함
                if current_user_pk != root_user_pk:
                    continue 

                # 조건 2: 답글인 경우, '누구에게 쓴 답글인가' 확인 (타인 답글 제외)
                # 첫 번째 글(Root)은 무조건 수집 (i==0)
                if i > 0:
                    text_post_app_info = post.get("text_post_app_info", {})
                    reply_to_author_id = text_post_app_info.get("reply_to_author", {}).get("id")
                    
                    # '내 글에 대한 답글'이 아니면 건너뜀 (타인 댓글에 대한 답글 등)
                    # 단, reply_to_author 정보가 없으면(None) 그냥 수집 (안전장치)
                    if reply_to_author_id and reply_to_author_id != root_user_pk:
                        continue
                # ==================================================

                user = post.get("user", {})
                caption = post.get("caption", {})
                extra_info = post.get("text_post_app_info", {})
                
                # 미디어 추출 및 타입 결정
                images = []
                video_versions = post.get("video_versions", [])
                carousel_media = post.get("carousel_media", [])
                image_versions2 = post.get("image_versions2", {})

                content_type = "text"
                
                if carousel_media:
                    content_type = "carousel"
                    for item in carousel_media:
                        candidates = item.get("image_versions2", {}).get("candidates", [])
                        if candidates:
                            best = sorted(candidates, key=lambda x: x.get("width", 0), reverse=True)[0]
                            images.append(best["url"])
                        if item.get("video_versions"):
                            images.append(item["video_versions"][0]["url"])
                            
                elif video_versions:
                    content_type = "video"
                    images.append(video_versions[0]["url"])
                    
                elif image_versions2:
                    content_type = "image"
                    candidates = image_versions2.get("candidates", [])
                    if candidates:
                        best = sorted(candidates, key=lambda x: x.get("width", 0), reverse=True)[0]
                        images.append(best["url"])

                created_at, time_text = format_timestamp(post.get("taken_at"))

                post_info = {
                    "code": code,
                    "root_code": root_code, # 그룹화용 필드
                    "pk": post.get("pk"),
                    "username": user.get("username"),
                    "user_link": f"https://www.threads.net/@{user.get('username')}",
                    "full_text": caption.get("text") if caption else "",
                    "like_count": post.get("like_count", 0),
                    "reply_count": extra_info.get("direct_reply_count", 0),
                    "repost_count": extra_info.get("repost_count", 0),
                    "quote_count": extra_info.get("quote_count", 0),
                    "created_at": created_at,
                    "time_text": time_text,
                    "post_url": f"https://www.threads.net/t/{code}",
                    "images": images,
                    "media_type": post.get("media_type"),
                    "content_type": content_type,
                    "source": "network",
                    "sequence_id": 0 # 나중에 일괄 부여
                }

                # 유효성 검사: 텍스트가 없고 이미지도 없는 경우 제외
                if not post_info['full_text'] and not post_info['images']:
                    continue

                collected_data.append(post_info)
                msg = post_info['full_text'].replace('\n', ' ')[:15]
                prefix = "└─" if i > 0 else "■ root"
                print(f"   + [Net] {prefix} [{code}] root:{root_code} | {msg}... ({len(collected_data)}개)")

        page.on("response", handle_response)

        # -------------------------------------------------
        # 1단계: 초기 화면 DOM 수집
        # -------------------------------------------------
        print("\n🔍 [1단계] 초기 화면(DOM) 스캔 중...")
        if "saved" not in page.url:
            page.goto("https://www.threads.net/saved")
            time.sleep(3)
        else:
            time.sleep(2)

        try:
            post_elements = page.locator('div[data-pressable-container="true"]').all()
            for element in post_elements:
                # 목표 체크
                if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT:
                    print("✋ 테스트 목표 달성 (DOM 단계)")
                    break

                try:
                    raw_text = element.inner_text()
                    lines = raw_text.split('\n')
                    link_locator = element.locator('a[href*="/post/"]').first

                    if link_locator.count() > 0:
                        href = link_locator.get_attribute("href")
                        parts = href.split('/')
                        if len(parts) >= 4:
                            username = parts[1].replace('@', '')
                            code = parts[3].split('?')[0]
                            
                            # ⛔ UPDATE ONLY 모드: stop_codes 중 하나 발견 시 중단
                            if stop_codes and code in stop_codes:
                                print(f"✋ 기준 게시물 발견! (code: {code}) - DOM 스캔 중단")
                                stop_code_found = True
                                break
                            
                            # [날짜 추출] 상대적 시간 감지
                            relative_date_str = None
                            date_patterns = [r'^\d+시간$', r'^\d+분$', r'^\d+일$', r'^\d+주$', r'^\d{4}-\d{2}-\d{2}$']
                            for line in lines[1:4]: # 이름 바로 다음 몇 줄 확인
                                line = line.strip()
                                if any(re.match(ptr, line) for ptr in date_patterns):
                                    relative_date_str = line
                                    break
                            
                            created_at, time_text = parse_relative_time(relative_date_str, start_time_dt)
                            cleaned_text = clean_text(raw_text, username)
                            
                            # 중복 체크 (code 기준)
                            if any(p['code'] == code for p in collected_data):
                                continue

                            images = []
                            for img in element.locator('img').all():
                                src = img.get_attribute("src")
                                if src and "scontent" in src and "s150x150" not in src:
                                    images.append(src)

                            post_info = {
                                "code": code,
                                "pk": None, # DOM에서는 PK 알 수 없음
                                "username": username,
                                "user_link": f"https://www.threads.net/@{username}",
                                "full_text": cleaned_text,
                                "like_count": -1,
                                "reply_count": -1,
                                "repost_count": -1,
                                "quote_count": -1,
                                "created_at": created_at,
                                "time_text": time_text,
                                "post_url": f"https://www.threads.net/t/{code}",
                                "images": list(set(images)),
                                "media_type": None,
                                "content_type": "carousel" if len(images) > 1 else ("image" if images else "text"),
                                "source": "initial_dom"
                            }
                            collected_data.append(post_info)
                            print(f"   + [DOM] [{code}] {cleaned_text.replace('\n', ' ')[:15]}... (현재 {len(collected_data)}/{TARGET_LIMIT if TARGET_LIMIT else '무제한'})")
                except: continue
        except Exception as e:
            print(f"⚠️ DOM 스캔 오류: {e}")

        # -------------------------------------------------
        # 2단계: 스크롤 자동화
        # -------------------------------------------------
        if TARGET_LIMIT == 0 or len(collected_data) < TARGET_LIMIT:
            print("\n📜 [2단계] 스크롤 시작 (네트워크 패킷 캡처)")
            no_new_data_count = 0
            last_len = len(collected_data)

            for i in range(1, 51):
                # 목표 달성 체크
                if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT:
                    print(f"\n🎉 목표 수집 개수({TARGET_LIMIT}개) 도달! 스크롤 종료.")
                    break
                
                # ⛔ UPDATE ONLY 모드: stop_code 발견 시 스크롤 중단
                if stop_code_found:
                    print(f"\n✋ 기준 게시물 수집 완료! 스크롤 종료")
                    break

                try:
                    if page.is_closed(): break
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    print(f"⬇️ 스크롤 {i}회차...", end="\r")
                    time.sleep(3)

                    current_len = len(collected_data)
                    if current_len > last_len:
                        print(f"\n✅ 데이터 추가됨! (누적 {current_len}개)")
                        last_len = current_len
                        no_new_data_count = 0
                    else:
                        no_new_data_count += 1
                        print(f"\nzzz... 대기 중 ({no_new_data_count}/5)")

                    if no_new_data_count >= 5:
                        print("\n🏁 더 이상 새로운 데이터가 없습니다.")
                        break
                except:
                    time.sleep(2)
                    continue
        else:
            print(f"\n⏩ 1단계에서 이미 목표({TARGET_LIMIT}개)를 달성하여 스크롤을 생략합니다.")

        # -------------------------------------------------
        # 3단계: 저장
        # -------------------------------------------------
        if collected_data:
            # 중복 제거 (Network 데이터 우선)
            unique_posts = {}
            for p in [x for x in collected_data if x['source'] == 'initial_dom']:
                unique_posts[p['code']] = p
            for p in [x for x in collected_data if x['source'] == 'network']:
                unique_posts[p['code']] = p

            final_list = list(unique_posts.values())
            
            # 최종 리스트에서도 개수 제한 적용 (병합 과정에서 늘어날 수 있으므로)
            if TARGET_LIMIT > 0:
                final_list = final_list[:TARGET_LIMIT]

            print(f"\n💾 최종 데이터 {len(final_list)}개 저장 중...")
            
            # output 폴더가 없으면 자동 생성
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            
            # [1] 신규 크롤링 결과 저장
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(final_list, f, ensure_ascii=False, indent=4)
            
            dom_cnt = sum(1 for p in final_list if p['source'] == 'initial_dom')
            net_cnt = sum(1 for p in final_list if p['source'] == 'network')
            print(f"✅ 신규 크롤링 저장: {OUTPUT_FILE}")
            print(f"   - Network 기반: {net_cnt}개")
            print(f"   - DOM 기반: {dom_cnt}개")
            
            # [추가] 🎨 2-Pass 연동을 위해 pending_list.json 저장
            try:
                pending_list = []
                seen_in_pending = set()
                for p in final_list:
                    code = p.get('code')
                    if code and code not in seen_in_pending:
                        pending_list.append({
                            "code": code,
                            "username": p.get('username'),
                            "captured_at": datetime.now().isoformat()
                        })
                        seen_in_pending.add(code)
                
                if pending_list:
                    with open("pending_list.json", "w", encoding="utf-8") as f:
                        json.dump(pending_list, f, ensure_ascii=False, indent=4)
                    print(f"📂 [2-Pass] {len(pending_list)}개의 작업이 pending_list.json에 저장되었습니다.")
            except Exception as e:
                print(f"⚠️ [2-Pass] pending_list 저장 실패: {e}")

            # [2] Simple 버전 업데이트
            if CRAWL_MODE == "update only":
                representative_stop = stop_codes[0] if stop_codes else None
                update_simple_version(final_list, representative_stop, crawl_start_time)
            else:
                # "all" 모드는 현재 결과를 새로운 Simple Full로 저장
                today = datetime.now().strftime('%Y%m%d')
                simple_filename = f"{OUTPUT_DIR}/threads_py_simple_full_{today}.json"
                os.makedirs(os.path.dirname(simple_filename), exist_ok=True)
                
                metadata = {
                    "version": "1.0",
                    "crawled_at": datetime.now().isoformat(),
                    "total_count": len(final_list),
                    "crawl_mode": "all"
                }
                
                save_data = {"metadata": metadata, "posts": final_list}
                
                with open(simple_filename, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=4)
                print(f"\n📦 Simple Full 버전 생성 완료: {simple_filename}")
        else:
            print("\n😭 수집된 데이터가 없습니다.")

        browser.close()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        print("\n" + "="*40)
        print(f"시작시간 : {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"종료시간 : {end_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요시간: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print("="*40)

if __name__ == "__main__":
    run()