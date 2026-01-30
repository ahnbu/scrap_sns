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
from datetime import datetime
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('.env.local')

# ===========================
# ⚙️ 설정 (여기만 수정하세요)
# ===========================
OUTPUT_FILE = f"output/threads_saved_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
AUTH_FILE = "auth.json"
THREADS_ID = os.getenv("THREADS_ID")
THREADS_PW = os.getenv("THREADS_PW")

# ✨ 테스트용 제한 개수 (0으로 설정하면 제한 없이 끝까지 수집)
TARGET_LIMIT = 0

# 🔄 크롤링 범위 설정
# - "all": 처음부터 끝까지 전체 수집
# - "update only": 최신 full 버전의 최상단 code까지만 수집 (신규 게시물만)
CRAWL_MODE = "update only"  # "all" 또는 "update only"
#CRAWL_MODE = "all"  # "all" 또는 "update only"

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

def find_latest_full_file():
    """output 폴더에서 최신 threads_saved_full_*.json 파일 찾기"""
    pattern = "output/threads_saved_full_*.json"
    files = glob.glob(pattern)
    
    if not files:
        return None
    
    # 파일명에서 날짜 추출 후 정렬
    file_info = []
    for file in files:
        match = re.search(r'_full_(\d{8})', file)
        if match:
            date_str = match.group(1)
            mtime = os.path.getmtime(file)
            file_info.append((file, date_str, mtime))
    
    # 날짜 최신순, 그 다음 수정시간 최신순 정렬
    file_info.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    return file_info[0][0] if file_info else None

def update_full_version(new_data, stop_code, crawl_start_time):
    """
    기존 Full 파일을 읽어와서 신규 데이터와 병합한 후,
    오늘 날짜로 새로운 Full 파일 생성 (메타데이터 포함)
    """
    today = datetime.now().strftime('%Y%m%d')
    today_full = f"output/threads_saved_full_{today}.json"
    
    # 1. 오늘 날짜 Full 파일이 이미 있는지 확인
    if os.path.exists(today_full):
        print(f"\n⚠️ 오늘 날짜의 Full 파일이 이미 존재합니다: {today_full}")
        print(f"   기존 파일을 최신 버전으로 사용하여 병합합니다.")
        latest_full = today_full
    else:
        latest_full = find_latest_full_file()
    
    # 2. 기존 Full 파일 읽기
    existing_posts = []
    existing_merge_history = []
    source_filename = None
    
    if latest_full:
        print(f"📂 기존 Full 파일 로드: {latest_full}")
        source_filename = os.path.basename(latest_full)
        
        with open(latest_full, 'r', encoding='utf-8') as f:
            existing_content = json.load(f)
            
            # 기존 파일이 메타데이터 구조인지 확인
            if isinstance(existing_content, dict) and 'posts' in existing_content:
                existing_posts = existing_content['posts']
                # 기존 merge_history 가져오기
                if 'metadata' in existing_content and 'merge_history' in existing_content['metadata']:
                    existing_merge_history = existing_content['metadata']['merge_history']
            else:
                # 레거시 구조 (배열만 있음)
                existing_posts = existing_content
        
        # 3. 기존 데이터의 code 집합 생성 및 최대 sequence_id 찾기
        existing_codes = {post['code'] for post in existing_posts}
        max_existing_seq = max((p.get('sequence_id', 0) for p in existing_posts), default=0)
        
        # 3-1. 레거시 데이터 처리 (sequence_id가 없는 경우 한 번만 부여)
        has_legacy = any('sequence_id' not in p for p in existing_posts)
        if has_legacy:
            print(f"   📋 레거시 데이터 발견 - sequence_id 부여 중...")
            total_existing = len(existing_posts)
            for i, post in enumerate(existing_posts):
                if 'sequence_id' not in post:
                    post['sequence_id'] = total_existing - i  # 역순: 최신이 큰 번호
                    post['crawled_at'] = None  # 레거시는 시간 정보 없음
            max_existing_seq = total_existing
        
        # 4. 신규 데이터에서 중복 필터링 및 sequence_id, crawled_at 추가
        new_items = []
        duplicate_count = 0
        
        for post in new_data:
            # 기존에 없는 것만 추가
            if post['code'] not in existing_codes:
                new_items.append(post)
            else:
                duplicate_count += 1
                print(f"   ⚠️ 중복 제거: {post['code']}")
        
        # 4-1. 신규 데이터에 sequence_id와 crawled_at 부여 (역순)
        new_count = len(new_items)
        for i, post in enumerate(new_items):
            post['sequence_id'] = max_existing_seq + new_count - i  # 예: 105, 104, 103...
            post['crawled_at'] = crawl_start_time
        
        # 5. 병합: [신규 필터링] + [기존] (순서 유지)
        merged_posts = new_items + existing_posts
        
        print(f"✅ 병합 완료: {len(new_items)}개 신규 추가 + {len(existing_posts)}개 기존 = {len(merged_posts)}개")
        if duplicate_count > 0:
            print(f"   (중복 {duplicate_count}개 자동 제거됨)")
    else:
        # Full 파일 없으면 현재 데이터를 그대로 사용
        print("⚠️ 기존 Full 파일 없음 - 현재 결과를 Full로 저장")
        
        # sequence_id와 crawled_at 부여 (역순)
        total_count = len(new_data)
        for i, post in enumerate(new_data):
            post['sequence_id'] = total_count - i  # 역순
            post['crawled_at'] = crawl_start_time
        
        merged_posts = new_data
        new_items = new_data
    
    # 6. 메타데이터 생성
    now = datetime.now().isoformat()
    legacy_count = sum(1 for p in merged_posts if not p.get('crawled_at'))
    verified_count = sum(1 for p in merged_posts if p.get('crawled_at'))
    max_sequence_id = max((p.get('sequence_id', 0) for p in merged_posts), default=0)
    
    # 7. merge_history 생성
    merge_history = existing_merge_history.copy()
    
    # 새 병합 이벤트 추가 (실제로 신규 데이터가 있을 때만)
    if latest_full and len(new_items) > 0:
        merge_event = {
            "merged_at": now,
            "new_items_count": len(new_items),
            "duplicates_removed": duplicate_count if 'duplicate_count' in locals() else 0,
            "source_file": source_filename,
            "stop_code": stop_code
        }
        merge_history.append(merge_event)
    
    metadata = {
        "version": "1.0",
        "crawled_at": now,
        "total_count": len(merged_posts),
        "max_sequence_id": max_sequence_id,
        "first_code": merged_posts[0]['code'] if merged_posts else None,
        "last_code": merged_posts[-1]['code'] if merged_posts else None,
        "crawl_mode": "update only",
        "legacy_data_count": legacy_count,
        "verified_data_count": verified_count,
        "merge_history": merge_history
    }
    
    # 8. 최종 구조 생성
    full_data = {
        "metadata": metadata,
        "posts": merged_posts
    }
    
    # 8. 파일 저장
    os.makedirs(os.path.dirname(today_full), exist_ok=True)
    with open(today_full, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=4)
    
    action = "업데이트" if latest_full == today_full else "생성"
    print(f"\n📦 Full 버전 {action}: {today_full}")
    print(f"   📊 데이터 품질: 타임스탬프 있음 {verified_count}개 / 레거시 {legacy_count}개")
    print(f"   🔢 Sequence ID 범위: 1 ~ {max_sequence_id}")
    if latest_full and latest_full != today_full:
        print(f"   (기존 파일 '{latest_full}' 은 보존됨)")
    
    return today_full


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
    collected_data = []
    stop_codes = []  # 중단 기준 code 리스트
    stop_code_found = False  # 중단 플래그
    crawl_start_time = datetime.now().isoformat()  # 크롤링 시작 시간
    
    # "update only" 모드: 최신 full 파일의 최상단 code 가져오기
    if CRAWL_MODE == "update only":
        latest_full = find_latest_full_file()
        if latest_full:
            try:
                with open(latest_full, 'r', encoding='utf-8') as f:
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
                print(f"⚠️ Full 파일 읽기 실패: {e}")
        else:
            print("⚠️ Full 파일 없음 - 전체 수집으로 전환")
 

    with sync_playwright() as p:
        print("🚀 브라우저 실행 중...")
        browser = p.chromium.launch(headless=False)
        
        if os.path.exists(AUTH_FILE):
            context = browser.new_context(viewport={"width": 1280, "height": 1000}, storage_state=AUTH_FILE)
        else:
            context = browser.new_context(viewport={"width": 1280, "height": 1000})

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
                        viewer = data_part.get("xdt_text_app_viewer") or data_part.get("viewer")
                        if not viewer: return
                        saved_media = viewer.get("saved_media")
                        if not saved_media: return
                        edges = saved_media.get("edges", [])
                        if edges:
                            print(f"\n⚡ [네트워크 감지] 추가 데이터 {len(edges)}개 포착!")
                            for edge in edges:
                                # 목표 개수 체크
                                if TARGET_LIMIT > 0 and len(collected_data) >= TARGET_LIMIT:
                                    break
                                node = edge.get("node", {})
                                thread_items = node.get("thread_items", [])
                                if thread_items:
                                    process_network_post(thread_items[0].get("post", {}))
                except: pass

        def process_network_post(post):
            nonlocal stop_code_found  # 외부 변수 수정 가능하도록
            if not post: return
            pk = post.get("pk")
            code = post.get("code")
            
            # ⛔ UPDATE ONLY 모드: stop_codes 중 하나 발견 시 중단
            if stop_codes and code in stop_codes:
                print(f"✋ 기준 게시물 발견! (code: {code}) - 크롤링 중단")
                stop_code_found = True
                return
            
            # 이미 수집된 목록에 있는지 확인 (중복 방지)
            if any(p['pk'] == pk for p in collected_data):
                return

            user = post.get("user", {})
            caption = post.get("caption", {})
            extra_info = post.get("text_post_app_info", {})
            
            images = []
            if post.get("image_versions2"):
                images = [img["url"] for img in post.get("image_versions2", {}).get("candidates", [])]
            if post.get("video_versions"):
                 images.append(post.get("video_versions", [{}])[0].get("url", ""))

            post_info = {
                "pk": pk,
                "code": post.get("code"),
                "username": user.get("username"),
                "text": caption.get("text") if caption else "",
                "like_count": post.get("like_count", 0),
                "reply_count": extra_info.get("direct_reply_count", 0),
                "repost_count": extra_info.get("repost_count", 0),
                "quote_count": extra_info.get("quote_count", 0),
                "posted_at": post.get("taken_at"),
                "url": f"https://www.threads.net/@{user.get('username')}/post/{post.get('code')}",
                "images": images,
                "source": "network"
            }
            collected_data.append(post_info)
            print(f"   + [Network] [{post_info['code']}] {post_info['text'][:15]}... (현재 {len(collected_data)}/{TARGET_LIMIT if TARGET_LIMIT else '무제한'})")

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
                                "pk": f"dom_{code}",
                                "code": code,
                                "username": username,
                                "text": cleaned_text,
                                "like_count": -1,
                                "reply_count": -1,
                                "repost_count": -1,
                                "quote_count": -1,
                                "posted_at": None,
                                "url": f"https://www.threads.net{href}",
                                "images": list(set(images)),
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
            
            # [2] Full 버전 업데이트
            if CRAWL_MODE == "update only":
                # 병합 로직에는 stop_codes 중 발견된 특정 코드를 전달할 수도 있으나, 
                # 현재 update_full_version은 단순히 중복 제거 기반이므로 리스트의 첫 번째 요소를 대표로 전달
                representative_stop = stop_codes[0] if stop_codes else None
                update_full_version(final_list, representative_stop, crawl_start_time)
            else:
                # "all" 모드는 현재 결과를 새로운 full로 저장 (메타데이터 포함)
                today = datetime.now().strftime('%Y%m%d')
                full_filename = f"output/threads_saved_full_{today}.json"
                os.makedirs(os.path.dirname(full_filename), exist_ok=True)
                
                # sequence_id와 crawled_at 부여 (역순)
                total_count = len(final_list)
                for i, post in enumerate(final_list):
                    post['sequence_id'] = total_count - i  # 역순: 최신(배열 0번)이 최대값
                    post['crawled_at'] = crawl_start_time
                
                # 메타데이터 생성
                now = datetime.now().isoformat()
                max_sequence_id = total_count
                metadata = {
                    "version": "1.0",
                    "crawled_at": now,
                    "total_count": total_count,
                    "max_sequence_id": max_sequence_id,
                    "first_code": final_list[0]['code'] if final_list else None,
                    "last_code": final_list[-1]['code'] if final_list else None,
                    "crawl_mode": "all",
                    "legacy_data_count": 0,
                    "verified_data_count": total_count,
                    "merge_history": []  # "all" 모드는 병합이 없으므로 빈 배열
                }
                
                full_data = {
                    "metadata": metadata,
                    "posts": final_list
                }
                
                with open(full_filename, "w", encoding="utf-8") as f:
                    json.dump(full_data, f, ensure_ascii=False, indent=4)
                print(f"\n📦 Full 버전 생성: {full_filename}")
                print(f"   📊 데이터 품질: 타임스탬프 있음 {total_count}개 / 레거시 0개")
                print(f"   🔢 Sequence ID 범위: 1 ~ {max_sequence_id}")
        else:
            print("\n😭 수집된 데이터가 없습니다.")

        browser.close()

if __name__ == "__main__":
    run()