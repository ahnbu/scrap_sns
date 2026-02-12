import json
import time
import os
import glob
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# ===========================
# ⚙️ 설정
# ===========================
OUTPUT_DIR = "output_twitter/python"
SIMPLE_FILE_PATTERN = "twitter_py_simple_full_*.json"
FULL_FILE_PATTERN = "twitter_py_full_{date}.json"

def clean_text(text):
    if not text: return ""
    return text.strip()

def scrape_full_thread(page, target_url, target_user):
    """개별 트윗 페이지에서 동일 작성자의 연속된 답글(타래) 수집 및 실제 사용자명 확인"""
    
    # 💡 [중요] 잘못된 URL(None 포함) 교정
    # x.com/None/status/ID 대신 x.com/i/status/ID를 쓰면 X가 실제 유저 주소로 보내줍니다.
    if 'None' in target_url:
        post_id = target_url.split('/')[-1]
        target_url = f"https://x.com/i/status/{post_id}"
        print(f"   🔄 URL 교정됨: {target_url}")

    print(f"   🔍 상세 수집 중: {target_url}")
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        
        # 실제 사용자명 추출 (리다이렉트된 후의 주소 또는 화면 요소에서)
        real_user = None
        
        # 방법 1: 현재 URL에서 추출 (리다이렉트 완료 후)
        current_url = page.url
        match = re.search(r'x\.com/([^/]+)/status/\d+', current_url)
        if match and match.group(1) != 'i' and match.group(1) != 'None':
            real_user = match.group(1)
            
        # 방법 2: 화면 요소에서 추출 (방법 1 실패 시)
        if not real_user:
            user_name_div = page.locator('div[data-testid="User-Name"]').first
            if user_name_div.count() > 0:
                links = user_name_div.locator('a[href^="/"]').all()
                for link in links:
                    href = link.get_attribute("href")
                    if href and href != "/" and "/status" not in href:
                        real_user = href.replace("/", "")
                        break
        
        if not real_user:
            real_user = target_user

        # "Show more" 또는 "더 보기" 버튼이 있으면 클릭
        show_more = page.locator('span:has-text("Show more"), span:has-text("더 보기")').first
        if show_more.count() > 0:
            try: show_more.click(); time.sleep(2)
            except: pass
            
    except Exception as e:
        print(f"      ⚠️ 페이지 접속 오류: {e}")
        return None, None, target_user

    thread_texts = []
    thread_media = set()
    
    articles = page.locator('article[data-testid="tweet"]').all()
    for i, article in enumerate(articles):
        try:
            # 실제 추출된 real_user와 비교
            user_handle_link = article.locator(f'a[href="/{real_user}"]').first
            
            if i > 0 and user_handle_link.count() == 0:
                break
            
            text_el = article.locator('div[data-testid="tweetText"]').first
            if text_el.count() > 0:
                text = text_el.inner_text()
                if text and text not in thread_texts:
                    thread_texts.append(text)
            
            imgs = article.locator('img[src*="media"]').all()
            for img in imgs:
                src = img.get_attribute("src")
                if src:
                    clean_src = f"https://wsrv.nl/?url={src.split('?')[0]}"
                    thread_media.add(clean_src)
                    
        except: continue

    full_text = "\n\n---\n\n".join(thread_texts)
    return full_text, list(thread_media), real_user

def main():
    # 1. 가장 최신 Simple 파일 로드
    simple_files = glob.glob(os.path.join(OUTPUT_DIR, SIMPLE_FILE_PATTERN))
    if not simple_files:
        print("❌ Simple 파일을 찾을 수 없습니다.")
        return
    
    latest_simple = sorted(simple_files, reverse=True)[0]
    print(f"📂 목록 로드: {os.path.basename(latest_simple)}")
    with open(latest_simple, 'r', encoding='utf-8-sig') as f:
        simple_data = json.load(f)
    
    posts = simple_data.get('posts', [])
    # 상세 수집 대상: is_detail_collected가 False이거나 None인 항목
    targets = [p for p in posts if not p.get('is_detail_collected')]
    
    if not targets:
        print("✨ 모든 항목이 이미 상세 수집되었습니다.")
        # 강제 재수집 테스트를 위해 첫 번째 항목만 시도해볼 수 있으나, 일단 스킵
        return

    print(f"🚀 총 {len(targets)}개의 신규 항목 상세 수집 시작...")

    USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0]

        updated_count = 0
        for post in targets:
            url = post['url']
            user = post['user']
            
            # 타래 수집 실행 (사용자 교정 정보 포함)
            full_text, media, real_user = scrape_full_thread(page, url, user)
            
            if full_text:
                # 💡 [교정] 실제 추출된 사용자명으로 업데이트
                post['user'] = real_user
                post['url'] = f"https://x.com/{real_user}/status/{post['id']}"
                post['full_text'] = full_text
                
                # 미디어 및 상태 업데이트
                combined_media = list(set((post.get('media', []) or []) + media))
                post['media'] = combined_media
                post['is_detail_collected'] = True
                post['source'] = 'full_thread_scan'
                post['sns_platform'] = 'x'
                
                # 날짜 정보 보강
                if not post.get('timestamp'):
                    post['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    post['date'] = datetime.now().strftime('%Y-%m-%d')
                
                updated_count += 1
                print(f"   ✅ 교정 및 수집 완료: @{real_user} ({len(full_text)}자)")
            else:
                print(f"   ⚠️ 수집 실패 또는 데이터 없음: {url}")
            
            time.sleep(3)

        # 2. 결과 저장 (Full)
        if updated_count > 0:
            today = datetime.now().strftime('%Y%m%d')
            full_file = os.path.join(OUTPUT_DIR, FULL_FILE_PATTERN.format(date=today))
            
            # 기존 Full 데이터가 있다면 로드하여 병합 (중복 방지)
            all_full_posts = []
            if os.path.exists(full_file):
                with open(full_file, 'r', encoding='utf-8-sig') as f:
                    try:
                        old_data = json.load(f)
                        all_full_posts = old_data.get('posts', [])
                    except: pass
            
            # ID 기반 병합 (이미 수집된 것은 유지, 새로 수집된 것으로 갱신)
            full_map = {str(p['id']): p for p in all_full_posts}
            for p in posts:
                if p.get('is_detail_collected'):
                    full_map[str(p['id'])] = p
            
            final_posts = sorted(full_map.values(), key=lambda x: x.get('timestamp') or '', reverse=True)
            
            # 메타데이터 포함하여 저장
            output_data = {
                "metadata": {
                    "updated_at": datetime.now().isoformat(),
                    "total_count": len(final_posts),
                    "platform": "x"
                },
                "posts": final_posts
            }
            
            with open(full_file, 'w', encoding='utf-8-sig') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=4)
            
            # Simple 파일 상태 업데이트 저장
            with open(latest_simple, 'w', encoding='utf-8-sig') as f:
                json.dump(simple_data, f, ensure_ascii=False, indent=4)
                
            print(f"\n✨ 상세 수집 마감 완료! 총 {len(final_posts)}개의 게시물이 정규화되었습니다.")
            print(f"📂 최종 결과: {full_file}")

        context.close()

if __name__ == "__main__":
    main()
