import json
import time
import re
import os
import glob
import argparse
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# 환경 변수 로드
load_dotenv('.env.local')

# ===========================
# ⚙️ 설정
# ===========================
WINDOW_X = 0              # 초기 확인을 위해 0으로 설정 (안정화 후 5000으로 변경 예정)
WINDOW_Y = 0
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800

OUTPUT_DIR = "output_twitter/python"
OUTPUT_FILE_PATTERN = "twitter_py_full_{date}.json"
UPDATE_FILE_PATTERN = "twitter_py_update_{timestamp}.json"
AUTH_FILE = "auth/auth_twitter.json"

# ✨ 테스트용 제한 개수 (0으로 설정하면 제한 없이 끝까지 수집)
TARGET_LIMIT = 0 

# 🔄 크롤링 범위 설정 (CLI 인자로 받음)
parser = argparse.ArgumentParser(description='X(Twitter) 북마크 실시간 스크래퍼')
parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드 (all: 전체, update: 증분)')
args = parser.parse_args()
# ===========================

def clean_text(text):
    if not text: return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_twitter_date(date_str):
    """X의 API 날짜 형식 변환"""
    try:
        dt = datetime.strptime(date_str, '%a %b %d %H:%M:%S +0000 %Y')
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except:
        return None, None

def extract_from_json(json_data):
    """JSON 패킷에서 트윗 추출"""
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
            
            if 'tweet' in tweet_results: tweet_results = tweet_results['tweet']
            legacy = tweet_results.get('legacy', {})
            user_results = tweet_results.get('core', {}).get('user_results', {}).get('result', {})
            user_info = user_results.get('legacy', {})
            
            body = tweet_results.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {}).get('text', "")
            if not body: body = legacy.get('full_text', "")
            
            media = [f"https://wsrv.nl/?url={m.get('media_url_https')}" for m in (legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])) if m.get('media_url_https')]
            
            ts_full, ts_short = parse_twitter_date(legacy.get('created_at'))
            post_id = tweet_results.get('rest_id')
            username = user_info.get('screen_name')
            
            posts.append({
                "id": post_id,
                "user": username,
                "display_name": user_info.get('name'),
                "full_text": clean_text(body),
                "media": media,
                "timestamp": ts_full,
                "date": ts_short,
                "url": f"https://x.com/{username}/status/{post_id}",
                "sns_platform": "twitter",
                "conversation_id": legacy.get('conversation_id_str')
            })
    except: pass
    return posts

def extract_from_html(html_content):
    """HTML DOM에서 트윗 추출"""
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
            href = link_tag.get('href', '')
            match = re.search(r'/([^/]+)/status/(\d+)', href)
            if not match: continue
            
            username = match.group(1)
            post_id = match.group(2)
            text_div = article.find('div', {'data-testid': 'tweetText'})
            body = text_div.get_text('\n') if text_div else ""
            
            dt_str = time_tag.get('datetime')
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                ts_full = dt.strftime('%Y-%m-%d %H:%M:%S')
                ts_short = dt.strftime('%Y-%m-%d')
            else:
                ts_full, ts_short = None, None
            
            media = [f"https://wsrv.nl/?url={img.get('src')}" for img in article.find_all('img') if 'media' in img.get('src', '')]
            
            name_div = article.find('div', {'data-testid': 'User-Name'})
            display_name = name_div.find('span').get_text() if name_div and name_div.find('span') else ""

            posts.append({
                "id": post_id,
                "user": username,
                "display_name": display_name,
                "full_text": clean_text(body),
                "media": media,
                "timestamp": ts_full,
                "date": ts_short,
                "url": f"https://x.com/{username}/status/{post_id}",
                "sns_platform": "twitter"
            })
        except: pass
    return posts

def main():
    all_posts_map = {}
    stop_ids = set()

    # 1. 기존 데이터 로드 (중단점 파악용)
    full_files = glob.glob(os.path.join(OUTPUT_DIR, "twitter_py_full_*.json"))
    if full_files:
        latest_full = sorted(full_files, reverse=True)[0]
        with open(latest_full, 'r', encoding='utf-8-sig') as f:
            try:
                old_posts = json.load(f).get('posts', [])
                for p in old_posts[:10]: # 최신 10개 ID를 중단점으로 설정
                    stop_ids.add(p['id'])
                for p in old_posts:
                    all_posts_map[p['url']] = p
                print(f"📡 기존 데이터 {len(old_posts)}개 로드됨. (중단점: {list(stop_ids)})")
            except: pass

    # 영구 사용자 데이터 폴더 경로 설정 (auth/x_user_data)
    USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    with sync_playwright() as p:
        print(f"🚀 실제 크롬 브라우저 실행 중... (데이터 폴더: {USER_DATA_DIR})")
        
        # 1단계: 별도의 창으로 독립된 크롬 실행 (Persistent Context)
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",  # 실제 구글 크롬 사용
            headless=False,
            args=[
                f"--window-position={WINDOW_X},{WINDOW_Y}",
                f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
                "--disable-blink-features=AutomationControlled", # 자동화 플래그 제거
                "--no-sandbox"
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}
        )
        
        page = context.pages[0] # 첫 번째 탭 사용

        # 네트워크 응답 가로채기 핸들러
        def handle_response(response):
            if "Bookmarks?variables=" in response.url and response.status == 200:
                try:
                    data = response.json()
                    new_posts = extract_from_json(data)
                    for post in new_posts:
                        if post['url'] not in all_posts_map:
                            print(f"   [Network] 신규 발견: @{post['user']} - {post['url']}")
                        all_posts_map[post['url']] = post
                except: pass

        page.on("response", handle_response)

        # 2단계: 북마크 페이지 직접 접속
        print("🌐 X 북마크 페이지 접속 중...")
        page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
        time.sleep(3)

        # 3단계: 로그인 여부 체크 및 무한 대기
        if not page.query_selector('article[data-testid="tweet"]'):
            print("⚠️ 로그인이 되어 있지 않거나 차단되었습니다.")
            print("💡 새로 뜬 브라우저 창에서 로그인을 완료해주세요! (로그인이 완료되면 자동으로 시작됩니다)")
            
            try:
                # 로그인 완료 대기 (어떤 종류의 트윗이라도 나타나면 로그인 성공으로 간주)
                page.wait_for_selector('article[data-testid="tweet"]', timeout=0)
                print("✅ 로그인 확인됨!")
            except Exception as e:
                print(f"❌ 대기 중 오류 발생: {e}")
                context.close()
                return

        # [추가] 로그인 후 홈으로 튕겼을 경우를 대비해 북마크 페이지로 재이동
        if "/i/bookmarks" not in page.url:
            print("🔄 북마크 페이지로 재이동합니다...")
            page.goto("https://x.com/i/bookmarks", wait_until="networkidle")
            time.sleep(3)

        # 최종 URL 확인
        if "/i/bookmarks" not in page.url:
            print(f"❌ 현재 페이지({page.url})가 북마크 페이지가 아닙니다. 수집을 중단합니다.")
            context.close()
            return

        # 4단계: 무한 스크롤 및 수집 루프
        print("📜 북마크 수집 및 스크롤 시작...")
        scroll_count = 0
        consecutive_no_new = 0
        new_total_collected = 0
        
        while True:
            # DOM 스캔
            current_content = page.content()
            html_posts = extract_from_html(current_content)
            
            if not html_posts and scroll_count == 0:
                print("⏳ 게시물이 아직 로딩되지 않았습니다. 잠시 대기...")
                time.sleep(3)
                continue

            found_stop_id = False
            new_in_this_round = 0

            for post in html_posts:
                if args.mode == 'update' and post['id'] in stop_ids:
                    found_stop_id = True
                    break
                if post['url'] not in all_posts_map:
                    all_posts_map[post['url']] = post
                    new_in_this_round += 1
                    new_total_collected += 1
                    print(f"   [DOM] 신규 발견: @{post['user']} - {post['url']}")

            if found_stop_id:
                print("✋ 기존 수집된 지점에 도달했습니다. (수집 종료)")
                break

            if new_in_this_round == 0:
                consecutive_no_new += 1
            else:
                consecutive_no_new = 0

            if consecutive_no_new > 10: # 충분히 기다림
                if new_total_collected > 0:
                    print(f"🏁 신규 {new_total_collected}개 수집 후 종료합니다.")
                else:
                    print("⚠️ 새로운 게시물을 찾지 못했습니다. 로그인이 풀렸거나 데이터가 더 이상 없습니다.")
                break

            if TARGET_LIMIT > 0 and len(all_posts_map) >= TARGET_LIMIT:
                print(f"🎯 목표 개수({TARGET_LIMIT})에 도달했습니다.")
                break

            # 스크롤
            page.mouse.wheel(0, 2000)
            scroll_count += 1
            time.sleep(2.5)
            print(f"⬇️ 스크롤 {scroll_count}회차... (신규 수집: {new_total_collected}개)", end="\r")

        # 최종 저장 및 병합
        print("\n🧹 데이터 정제 및 타래 병합 중...")
        # (타래 병합 로직 - 이전 코드와 동일)
        conv_groups = {}
        for p in all_posts_map.values():
            cid = p.get('conversation_id')
            if cid:
                if cid not in conv_groups: conv_groups[cid] = []
                conv_groups[cid].append(p)
        
        merged_posts = []
        processed_urls = set()
        for cid, group in conv_groups.items():
            if len(group) > 1:
                group.sort(key=lambda x: x.get('timestamp') or '')
                main_post = group[0].copy()
                combined_body, combined_media, seen_media = [], [], set()
                for p in group:
                    if p['full_text']: combined_body.append(p['full_text'])
                    for m in p.get('media', []):
                        if m not in seen_media: combined_media.append(m); seen_media.add(m)
                    processed_urls.add(p['url'])
                main_post['full_text'] = "\n\n---\n\n".join(combined_body)
                main_post['media'] = combined_media
                merged_posts.append(main_post)

        for url, p in all_posts_map.items():
            if url not in processed_urls: merged_posts.append(p)

        final_posts = sorted(merged_posts, key=lambda x: x.get('timestamp') or '', reverse=True)
        
        if final_posts:
            today = datetime.now().strftime('%Y%m%d')
            full_file = os.path.join(OUTPUT_DIR, OUTPUT_FILE_PATTERN.format(date=today))
            os.makedirs(os.path.dirname(full_file), exist_ok=True)
            
            # 메타데이터 구성 (Threads 형식 준수)
            metadata = {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "new_items_count": new_total_collected,
                "latest_post_url": final_posts[0]['url'] if final_posts else None,
                "crawl_mode": args.mode,
                "platform": "twitter"
            }

            # Full 데이터 저장
            with open(full_file, 'w', encoding='utf-8-sig') as f:
                json.dump({
                    "metadata": metadata,
                    "posts": final_posts
                }, f, ensure_ascii=False, indent=4)
            
            # Update 데이터 저장 (total_scrap 연동용 리스트 형식 유지)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            update_file = os.path.join(OUTPUT_DIR, "update", UPDATE_FILE_PATTERN.format(timestamp=ts))
            os.makedirs(os.path.dirname(update_file), exist_ok=True)
            with open(update_file, 'w', encoding='utf-8-sig') as f:
                json.dump(final_posts, f, ensure_ascii=False, indent=4)
            
            print(f"✨ 수집 완료! 총 {len(final_posts)}개 저장됨 (신규: {new_total_collected}개).")
            print(f"📂 Full: {full_file}")
            print(f"📂 Update: {update_file}")

        context.close()

if __name__ == "__main__":
    main()
