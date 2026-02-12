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
WINDOW_X = 0
WINDOW_Y = 0
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800

OUTPUT_DIR = "output_twitter/python"
OUTPUT_FILE_PATTERN = "twitter_py_simple_full_{date}.json"

# ✨ 테스트용 제한 개수 (0: 무제한)
TARGET_LIMIT = 0 

parser = argparse.ArgumentParser(description='X(Twitter) 목록 수집기 (Producer) - Refined')
parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
args = parser.parse_args()

def clean_text(text):
    if not text: return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip().replace('\n', ' ')

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
            body = tweet_results.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {}).get('text', "")
            if not body: body = legacy.get('full_text', "")
            
            media = [f"https://wsrv.nl/?url={m.get('media_url_https')}" for m in (legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])) if m.get('media_url_https')]
            ts_full, ts_short = parse_twitter_date(legacy.get('created_at'))
            post_id = tweet_results.get('rest_id')
            
            if post_id:
                posts.append({
                    "id": post_id,
                    "user": username or "Unknown",
                    "display_name": display_name,
                    "full_text": body,
                    "media": media,
                    "timestamp": ts_full,
                    "date": ts_short,
                    "url": f"https://x.com/{username}/status/{post_id}" if username else f"https://x.com/i/status/{post_id}",
                    "sns_platform": "x",
                    "source": "network",
                    "is_detail_collected": False
                })
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
            text_div = article.find('div', {'data-testid': 'tweetText'})
            body = text_div.get_text('\n') if text_div else ""
            
            dt_str = time_tag.get('datetime')
            ts_full, ts_short = (None, None)
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                ts_full, ts_short = dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
            
            name_div = article.find('div', {'data-testid': 'User-Name'})
            display_name = name_div.find('span').get_text() if name_div and name_div.find('span') else ""

            posts.append({
                "id": post_id,
                "user": username,
                "display_name": display_name,
                "full_text": body,
                "media": [f"https://wsrv.nl/?url={img.get('src')}" for img in article.find_all('img') if 'media' in img.get('src', '')],
                "timestamp": ts_full,
                "date": ts_short,
                "url": f"https://x.com/{username}/status/{post_id}",
                "sns_platform": "x",
                "source": source_label,
                "is_detail_collected": False
            })
        except: pass
    return posts

def main():
    start_time = datetime.now()
    all_posts_map = {}
    stop_ids = set()
    initial_count = 0
    new_count = 0

    print(f"🚀 X(Twitter) 목록 수집기 시작 (Mode: {args.mode})", flush=True)

    # 1. 기존 데이터 로드
    full_files = glob.glob(os.path.join(OUTPUT_DIR, "twitter_py_simple_full_*.json"))
    if full_files:
        latest_full = sorted(full_files, reverse=True)[0]
        with open(latest_full, 'r', encoding='utf-8-sig') as f:
            try:
                old_posts = json.load(f).get('posts', [])
                for p in old_posts[:20]: stop_ids.add(p['id'])
                for p in old_posts: all_posts_map[p['id']] = p
                initial_count = len(old_posts)
                print(f"📡 기존 데이터 {initial_count}개 로드됨. (중단점: {len(stop_ids)}개 설정)", flush=True)
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
                        pid = post['id']
                        # 💡 [개선] 기존 수집 상태 확인
                        was_collected = pid in all_posts_map and all_posts_map[pid].get('is_detail_collected', False)
                        
                        if pid not in all_posts_map or len(post['full_text']) > len(all_posts_map[pid].get('full_text', '')):
                            if pid not in all_posts_map: new_count += 1
                            all_posts_map[pid] = post
                            # 💡 기존 수집 완료 상태라면 True 유지
                            all_posts_map[pid]['is_detail_collected'] = was_collected
                            
                            if not was_collected:
                                msg = clean_text(post['full_text'])[:30]
                                print(f"   + [Net] @{post['user']} | {msg}... ({len(all_posts_map)}개)", flush=True)
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
            html_posts = extract_from_html(page.content(), "initial_dom" if scroll_count == 0 else "network")
            round_new = 0
            found_stop = False

            for post in html_posts:
                pid = post['id']
                if args.mode == 'update' and pid in stop_ids:
                    found_stop = True; break
                
                # 💡 [개선] 상세 수집 완료 여부 확인
                was_collected = pid in all_posts_map and all_posts_map[pid].get('is_detail_collected', False)
                
                if pid not in all_posts_map:
                    all_posts_map[pid] = post
                    all_posts_map[pid]['is_detail_collected'] = was_collected
                    new_count += 1
                    round_new += 1
                    msg = clean_text(post['full_text'])[:30]
                    print(f"   + [DOM] @{post['user']} | {msg}... ({len(all_posts_map)}개)", flush=True)
                elif not was_collected and len(post['full_text']) > len(all_posts_map[pid].get('full_text', '')):
                    all_posts_map[pid].update(post)
            
            if found_stop:
                print(f"\n✋ 기존 수집 지점({pid}) 도달. 수집을 종료합니다.", flush=True)
                break
                
            if round_new == 0: 
                consecutive_no_new += 1
            else: 
                consecutive_no_new = 0
                print(f"   ✅ 신규 데이터 {round_new}개 추가됨! (누계: {len(all_posts_map)}개)", flush=True)

            if consecutive_no_new >= 5: 
                print("\n🏁 더 이상 새로운 게시물이 없습니다.", flush=True)
                break
                
            if TARGET_LIMIT > 0 and len(all_posts_map) >= TARGET_LIMIT: 
                print(f"\n🎯 목표 개수({TARGET_LIMIT})에 도달했습니다.", flush=True)
                break

            page.mouse.wheel(0, 2000)
            scroll_count += 1
            time.sleep(2.5)
            print(f"⬇️ 스크롤 {scroll_count}회차 진행 중...", end="\r", flush=True)

        # 결과 저장
        final_posts = sorted(all_posts_map.values(), key=lambda x: x.get('timestamp') or '', reverse=True)
        if final_posts:
            today = datetime.now().strftime('%Y%m%d')
            full_file = os.path.join(OUTPUT_DIR, OUTPUT_FILE_PATTERN.format(date=today))
            os.makedirs(os.path.dirname(full_file), exist_ok=True)
            
            with open(full_file, 'w', encoding='utf-8-sig') as f:
                json.dump({
                    "metadata": {
                        "updated_at": datetime.now().isoformat(),
                        "total_count": len(final_posts),
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
    main()
