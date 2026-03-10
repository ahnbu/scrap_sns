import json
import time
import re
import os
import glob
import argparse
import sys
import io
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# 환경 변수 로드
load_dotenv('.env.local')

# Windows 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===========================
# ⚙️ 설정
# ===========================
WINDOW_X = 900
WINDOW_Y = 0
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 600

OUTPUT_DIR = "output_twitter/python"
OUTPUT_FILE_PATTERN = "twitter_py_simple_{date}.json"

# ✨ 테스트용 제한 개수 (0: 무제한)
TARGET_LIMIT = 0 

def clean_text(text):
    if not text: return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip().replace('\n', ' ')

def reorder_post(post):
    STANDARD_FIELD_ORDER = [
        "sequence_id", "platform_id", "sns_platform", "username", "display_name",
        "full_text", "media", "url", "created_at", "date", "crawled_at", "source", "local_images"
    ]
    ordered_post = {}
    for field in STANDARD_FIELD_ORDER:
        if field in post: ordered_post[field] = post[field]
    for key, value in post.items():
        if key not in ordered_post: ordered_post[key] = value
    return ordered_post

def parse_twitter_date(date_str):
    try:
        dt = datetime.strptime(date_str, '%a %b %d %H:%M:%S +0000 %Y')
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except:
        return None, None

def get_user_info(tweet_results):
    user_res = tweet_results.get('core', {}).get('user_results', {}).get('result', {})
    if not user_res:
        user_res = tweet_results.get('tweet', {}).get('core', {}).get('user_results', {}).get('result', {})
    
    username = None
    display_name = "Unknown"

    if user_res:
        u_core = user_res.get('core', {})
        username = u_core.get('screen_name')
        display_name = u_core.get('name')
        if not username:
            u_legacy = user_res.get('legacy', {})
            username = u_legacy.get('screen_name')
            display_name = u_legacy.get('name')
            
    return username, display_name

def extract_from_json(json_data):
    posts = []
    try:
        instructions = json_data.get('data', {}).get('bookmark_timeline_v2', {}).get('timeline', {}).get('instructions', [])
        entries = []
        for inst in instructions:
            if inst.get('type') == 'TimelineAddEntries':
                entries = inst.get('entries', [])
                break
        
        for entry in entries:
            content = entry.get('content', {})
            item_content = content.get('itemContent', {})
            if item_content.get('itemType') != 'TimelineTweet': continue
                
            tweet_results = item_content.get('tweet_results', {}).get('result', {})
            if not tweet_results: continue
            
            legacy = tweet_results.get('legacy', {})
            if not legacy and 'tweet' in tweet_results:
                legacy = tweet_results['tweet'].get('legacy', {})

            username, display_name = get_user_info(tweet_results)
            
            # 💡 [개선] 본문 추출 우선순위: NoteTweet(긴 트윗) > Legacy Full Text
            # NoteTweet 결과가 있으면 그걸 먼저 사용 (인용된 트윗의 본문이 아닌 현재 트윗의 본문임을 확인)
            body = ""
            note_tweet_res = tweet_results.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {})
            if note_tweet_res:
                body = note_tweet_res.get('text', "")
            
            if not body:
                body = legacy.get('full_text', "")
            
            # 💡 [추가] 인용 트윗 주소 제거 (Twitter API는 인용 트윗의 URL을 본문 끝에 붙임)
            # 수집 데이터의 순수성을 위해 마지막의 t.co 링크가 인용 링크라면 제거 고려 가능
            # 여기서는 일단 그대로 두되, 본문이 중복되는 원인이 인용 본문 오인식인지 확인용 로그 강화
            
            media = [f"https://wsrv.nl/?url={m.get('media_url_https')}" for m in (legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])) if m.get('media_url_https')]
            ts_full, ts_short = parse_twitter_date(legacy.get('created_at'))
            post_id = tweet_results.get('rest_id')
            
            if post_id:
                posts.append(reorder_post({
                    "platform_id": post_id,
                    "username": username or "Unknown",
                    "display_name": display_name,
                    "full_text": body,
                    "media": media,
                    "created_at": ts_full,
                    "date": ts_short,
                    "url": f"https://x.com/{username}/status/{post_id}" if username else f"https://x.com/i/status/{post_id}",
                    "sns_platform": "x",
                    "source": "network",
                    "is_detail_collected": False
                }))
    except: pass
    return posts

def extract_from_html(html_content, source_label="initial_dom"):
    posts = []
    if not BeautifulSoup: return posts
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = soup.find_all('article', {'data-testid': 'tweet'})
    
    for article in articles:
        try:
            time_tag = article.find('time')
            if not time_tag: continue
            link_tag = time_tag.find_parent('a')
            if not link_tag: continue
            match = re.search(r'/([^/]+)/status/(\d+)', link_tag.get('href', ''))
            if not match: continue
            
            username, post_id = match.group(1), match.group(2)
            
            # 💡 [개선] 인용 트윗 본문을 제외하고 메인 본문만 추출
            # data-testid="tweetText" 중 인용 컨테이너(quoted_status 등) 내부에 있지 않은 것 탐색
            all_text_divs = article.find_all('div', {'data-testid': 'tweetText'})
            body = ""
            for t_div in all_text_divs:
                # 부모 중에 인용 트윗임을 나타내는 요소가 있는지 확인
                is_quoted = False
                parent = t_div.parent
                while parent and parent.name != 'article':
                    # Twitter의 인용 트윗 컨테이너 특징 (테두리가 있는 div 등)
                    if parent.get('role') == 'link' or (parent.name == 'div' and 'border' in parent.get('class', [])):
                        # 인용 트윗 내부의 본문임
                        is_quoted = True
                        break
                    parent = parent.parent
                
                if not is_quoted:
                    body = t_div.get_text('\n')
                    break
            
            # 위 로직으로 못 찾은 경우 첫 번째 것 시도 (폴백)
            if not body and all_text_divs:
                body = all_text_divs[0].get_text('\n')
            
            dt_str = time_tag.get('datetime')
            ts_full, ts_short = (None, None)
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                ts_full, ts_short = dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
            
            name_div = article.find('div', {'data-testid': 'User-Name'})
            display_name = name_div.find('span').get_text() if name_div and name_div.find('span') else ""

            posts.append(reorder_post({
                "platform_id": post_id,
                "username": username,
                "display_name": display_name,
                "full_text": body,
                "media": [f"https://wsrv.nl/?url={img.get('src')}" for img in article.find_all('img') if 'media' in img.get('src', '')],
                "created_at": ts_full,
                "date": ts_short,
                "url": f"https://x.com/{username}/status/{post_id}",
                "sns_platform": "x",
                "source": source_label,
                "is_detail_collected": False
            }))
        except: pass
    return posts

def main(args):
    start_time = datetime.now()
    all_posts_map = {}
    stop_ids = set()
    initial_count = 0
    new_count = 0
    max_sequence_id = 0

    print(f"🚀 X(Twitter) 목록 수집기 시작 (Mode: {args.mode})", flush=True)

    # 1. 기존 데이터 로드
    full_files = glob.glob(os.path.join(OUTPUT_DIR, "twitter_py_simple_*.json"))
    if full_files:
        latest_full = sorted(full_files, reverse=True)[0]
        with open(latest_full, 'r', encoding='utf-8-sig') as f:
            try:
                data = json.load(f)
                old_posts = data.get('posts', [])
                metadata = data.get('metadata', {})
                max_sequence_id = metadata.get('max_sequence_id', 0)
                
                # 메타데이터에 없으면 수동 계산 (레거시 지원)
                if max_sequence_id == 0 and old_posts:
                    max_sequence_id = max((p.get('sequence_id', 0) for p in old_posts), default=0)

                for p in old_posts:
                    # 💡 [보정] crawled_at이 없는 레거시 데이터 보정
                    if not p.get('crawled_at'):
                        p['crawled_at'] = p.get('created_at') or datetime.now().isoformat()
                    
                    pid = p.get('platform_id') or p.get('id')
                    stop_ids.add(pid)
                    all_posts_map[pid] = p
                
                # 중단점은 최신 20개로 제한 유지
                stop_ids = set(list(all_posts_map.keys())[:20])
                
                initial_count = len(old_posts)
                print(f"📡 기존 데이터 {initial_count}개 로드됨. (max_sequence_id: {max_sequence_id}, 중단점: {len(stop_ids)}개 설정)", flush=True)
            except: pass

    USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=[f"--window-position={WINDOW_X},{WINDOW_Y}", "--disable-blink-features=AutomationControlled"],
            viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}
        )
        page = context.pages[0]

        def handle_response(response):
            nonlocal new_count
            if "Bookmarks?variables=" in response.url and response.status == 200:
                try:
                    new_posts = extract_from_json(response.json())
                    for post in new_posts:
                        pid = post['platform_id']
                        # 💡 [개선] 기존 수집 상태 및 메타데이터 보존
                        existing = all_posts_map.get(pid)
                        was_collected = existing.get('is_detail_collected', False) if existing else False
                        
                        if pid not in all_posts_map or len(post['full_text']) > len(all_posts_map[pid].get('full_text', '')):
                            if pid not in all_posts_map: 
                                new_count += 1
                                post['crawled_at'] = datetime.now().isoformat(timespec='milliseconds')
                            else:
                                # 기존 메타데이터 보존
                                post['crawled_at'] = existing.get('crawled_at')
                                post['sequence_id'] = existing.get('sequence_id')
                                
                            all_posts_map[pid] = post
                            all_posts_map[pid]['is_detail_collected'] = was_collected
                            
                            if not was_collected:
                                msg = clean_text(post['full_text'])[:30]
                                print(f"   + [Net] @{post['username']} | {msg}... ({len(all_posts_map)}개)", flush=True)
                except: pass

        page.on("response", handle_response)
        
        print("\n🔍 [1단계] 북마크 페이지 접속 중...", flush=True)
        page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
        time.sleep(3)

        if not page.query_selector('article[data-testid="tweet"]'):
            print("💡 로그인이 필요합니다. 브라우저에서 진행해주세요...", flush=True)
            page.wait_for_selector('article[data-testid="tweet"]', timeout=0)

        print("\n📜 [2단계] 스크롤 및 실시간 수집 시작", flush=True)
        scroll_count = 0
        consecutive_no_new = 0
        
        while True:
            before_count = len(all_posts_map)
            
            # 1. DOM 스캔
            html_posts = extract_from_html(page.content(), "initial_dom" if scroll_count == 0 else "network")
            found_stop = False

            for post in html_posts:
                pid = post['platform_id']
                if args.mode == 'update' and pid in stop_ids:
                    found_stop = True
                    break
                
                # 💡 [개선] 기존 메타데이터 확인
                existing = all_posts_map.get(pid)
                was_collected = existing.get('is_detail_collected', False) if existing else False
                
                if pid not in all_posts_map:
                    post['crawled_at'] = datetime.now().isoformat(timespec='milliseconds')
                    all_posts_map[pid] = post
                    all_posts_map[pid]['is_detail_collected'] = was_collected
                    new_count += 1
                    msg = clean_text(post['full_text'])[:30]
                    print(f"   + [DOM] @{post['username']} | {msg}... ({len(all_posts_map)}개)", flush=True)
                elif not was_collected and len(post['full_text']) > len(all_posts_map[pid].get('full_text', '')):
                    # 업데이트 시 기존 메타데이터 유지하며 내용만 갱신
                    c_at = existing.get('crawled_at')
                    s_id = existing.get('sequence_id')
                    all_posts_map[pid].update(post)
                    all_posts_map[pid]['crawled_at'] = c_at
                    all_posts_map[pid]['sequence_id'] = s_id
            
            if found_stop:
                print(f"\n✋ 기존 수집 지점({pid}) 도달. 수집을 종료합니다.", flush=True)
                break
            
            # 2. 신규 데이터 발견 여부 판단 (Network + DOM 통합)
            after_count = len(all_posts_map)
            if after_count > before_count:
                print(f"   ✅ 신규 데이터 {after_count - before_count}개 추가됨! (누계: {after_count}개)", flush=True)
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1
                print(f"   zzz... 대기 중 ({consecutive_no_new}/5)", flush=True)

            if consecutive_no_new >= 5: 
                print("\n🏁 더 이상 새로운 게시물이 없습니다.", flush=True)
                break
                
            if TARGET_LIMIT > 0 and len(all_posts_map) >= TARGET_LIMIT: 
                print(f"\n🎯 목표 개수({TARGET_LIMIT})에 도달했습니다.", flush=True)
                break

            # 3. 스크롤 수행
            page.mouse.wheel(0, 3000) # 스크롤 양 약간 증가
            scroll_count += 1
            time.sleep(3.0) # 네트워크 응답 대기를 위해 시간 약간 증가
            print(f"⬇️ 스크롤 {scroll_count}회차 진행 중...", end="\r", flush=True)

        # 결과 저장
        # 💡 [개선] 신규 게시물에 sequence_id 부여
        # crawled_at 기준 오름차순(과거->최신)으로 정렬하여 ID 순차 부여
        new_posts_to_id = [p for p in all_posts_map.values() if p.get('sequence_id') is None]
        new_posts_to_id.sort(key=lambda x: x.get('crawled_at') or '')
        
        for p in new_posts_to_id:
            max_sequence_id += 1
            p['sequence_id'] = max_sequence_id

        # 💡 [추가] 본문 중복 체크 (Deduplication Check)
        text_map = {}
        duplicates_found = 0
        for p in all_posts_map.values():
            txt = p.get('full_text', '')
            if len(txt) > 20: # 짧은 텍스트는 제외
                if txt in text_map:
                    text_map[txt].append(p.get('platform_id'))
                    duplicates_found += 1
                else:
                    text_map[txt] = [p.get('platform_id')]
        
        if duplicates_found > 0:
            print(f"\n⚠️ 주의: 본문 내용이 완전히 동일한 항목이 {duplicates_found}개 발견되었습니다.")
            for txt, ids in text_map.items():
                if len(ids) > 1:
                    print(f"   - 중복 텍스트 ({len(ids)}회): {txt[:50]}... | IDs: {ids}")

        final_posts = sorted(all_posts_map.values(), key=lambda x: x.get('sequence_id', 0), reverse=True)
        if final_posts:
            today = datetime.now().strftime('%Y%m%d')
            full_file = os.path.join(OUTPUT_DIR, OUTPUT_FILE_PATTERN.format(date=today))
            os.makedirs(os.path.dirname(full_file), exist_ok=True)
            
            with open(full_file, 'w', encoding='utf-8-sig') as f:
                json.dump({
                    "metadata": {
                        "updated_at": datetime.now().isoformat(),
                        "total_count": len(final_posts),
                        "max_sequence_id": max_sequence_id,
                        "duplicates_found": duplicates_found,
                        "platform": "x"
                    },
                    "posts": final_posts
                }, f, ensure_ascii=False, indent=4)
            
            # 💡 [추가] Simple Update 파일 생성
            if new_count > 0:
                update_dir = os.path.join(OUTPUT_DIR, "update")
                os.makedirs(update_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                update_file = os.path.join(update_dir, f"twitter_py_simple_update_{timestamp}.json")
                
                # 이번 수집에서 새로 추가된 것만 필터링 (is_detail_collected가 False인 최신 데이터들)
                new_items = [p for p in final_posts if not p.get('is_detail_collected')][:new_count]
                
                with open(update_file, 'w', encoding='utf-8-sig') as f:
                    json.dump(new_items, f, ensure_ascii=False, indent=4)
                print(f"📂 목록 업데이트 저장: {update_file} ({new_count}개)")

            end_time = datetime.now()
            duration = end_time - start_time
            
            # Threads 스타일 최종 요약 통계
            print("\n" + "="*40, flush=True)
            print(f"시작시간 : {start_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"종료시간 : {end_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"소요시간 : {str(duration).split('.')[0]}", flush=True)
            print("="*40, flush=True)
            print(f"📊 최종 수집 결과 요약", flush=True)
            print(f"기존 게시물 : {initial_count}개", flush=True)
            print(f"신규 추가 : {new_count}개", flush=True)
            print(f"전체 목록 : {len(final_posts)}개", flush=True)
            print(f"저장 경로 : {full_file}", flush=True)
            print("="*40, flush=True)

        context.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='X(Twitter) 목록 수집기 (Producer) - Refined')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    args = parser.parse_args()
    main(args)
