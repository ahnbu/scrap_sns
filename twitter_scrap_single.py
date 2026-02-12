import json
import time
import os
import glob
import re
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

# ===========================
# ⚙️ 설정
# ===========================
OUTPUT_DIR = "output_twitter/python"
SIMPLE_FILE_PATTERN = "twitter_py_simple_full_*.json"
FULL_FILE_PATTERN = "twitter_py_full_{date}.json"
FAILURE_FILE = "scrap_failures_twitter.json" # 💡 X(Twitter) 전용 파일

# 명령줄 인자 설정
parser = argparse.ArgumentParser(description='X(Twitter) 상세 수집기')
parser.add_argument('--limit', type=int, default=0, help='수집할 최대 개수 (0: 무제한)')
args = parser.parse_args()

def clean_text(text):
    if not text: return ""
    return text.strip()

def load_failures():
    if os.path.exists(FAILURE_FILE):
        with open(FAILURE_FILE, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_failures(failures):
    with open(FAILURE_FILE, 'w', encoding='utf-8') as f:
        json.dump(failures, f, ensure_ascii=False, indent=4)

def scrape_full_thread(page, target_url, target_user):
    """개별 트윗 페이지에서 동일 작성자의 연속된 답글(타래) 수집 및 실제 사용자명 확인"""
    if 'None' in target_url:
        post_id = target_url.split('/')[-1]
        target_url = f"https://x.com/i/status/{post_id}"

    print(f"   🔍 상세 수집 중: {target_url}")
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        
        real_user = None
        current_url = page.url
        match = re.search(r'x\.com/([^/]+)/status/\d+', current_url)
        if match and match.group(1) != 'i' and match.group(1) != 'None':
            real_user = match.group(1)
            
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
    failures = load_failures()
    
    simple_files = glob.glob(os.path.join(OUTPUT_DIR, SIMPLE_FILE_PATTERN))
    if not simple_files:
        print("❌ Simple 파일을 찾을 수 없습니다.")
        return
    
    latest_simple = sorted(simple_files, reverse=True)[0]
    print(f"📂 목록 로드: {os.path.basename(latest_simple)}")
    with open(latest_simple, 'r', encoding='utf-8-sig') as f:
        simple_data = json.load(f)
    
    posts = simple_data.get('posts', [])
    
    # 💡 [개선] 3회 실패 제외 로직 적용
    targets = []
    skipped_count = 0
    for p in posts:
        pid = str(p['id'])
        if p.get('is_detail_collected'): continue
        
        fail_info = failures.get(pid, {})
        fail_count = fail_info.get('count', 0)
        
        if fail_count >= 3:
            skipped_count += 1
            continue
        
        targets.append(p)
    
    if skipped_count > 0:
        print(f"⏩ [Skip] {skipped_count}개 항목 제외 (3회 이상 실패)")

    if not targets:
        print("✨ 상세 수집할 새로운 항목이 없습니다. (메타데이터 동기화만 진행)")

    updated_count = 0
    if targets:
        # 💡 [추가] 개수 제한 적용
        if args.limit > 0:
            print(f"🎯 테스트 모드: {args.limit}개만 수집합니다.")
            targets = targets[:args.limit]

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

            total_targets = len(targets)
            for i, post in enumerate(targets):
                pid = str(post['id'])
                url = post['url']
                user = post['user']
                
                # 진척률 계산
                current_num = i + 1
                progress_percent = int((current_num / total_targets) * 100)
                progress_msg = f"({current_num}/{total_targets}, {progress_percent}%)"
                
                full_text, media, real_user = scrape_full_thread(page, url, user)
                
                if full_text:
                    post['user'] = real_user
                    post['url'] = f"https://x.com/{real_user}/status/{post['id']}"
                    post['full_text'] = full_text
                    post['media'] = list(set((post.get('media', []) or []) + media))
                    post['is_detail_collected'] = True
                    post['source'] = 'full_thread_scan'
                    post['sns_platform'] = 'x'
                    
                    if not post.get('timestamp'):
                        post['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        post['date'] = datetime.now().strftime('%Y-%m-%d')
                    
                    # 성공 시 실패 이력 제거
                    if pid in failures: del failures[pid]
                    updated_count += 1
                    print(f"   ✅ 수집 완료: @{real_user} {progress_msg}")
                else:
                    # 💡 실패 시 카운트 증가
                    fail_info = failures.get(pid, {"count": 0, "last_fail": ""})
                    fail_info['count'] += 1
                    fail_info['last_fail'] = datetime.now().isoformat()
                    fail_info['url'] = url
                    failures[pid] = fail_info
                    print(f"   ❌ 수집 실패 ({fail_info['count']}/3): {url} {progress_msg}")
                
                save_failures(failures) # 실시간 저장
                time.sleep(3)
            context.close()

    # 결과 저장 (Full)
    today = datetime.now().strftime('%Y%m%d')
    full_file = os.path.join(OUTPUT_DIR, FULL_FILE_PATTERN.format(date=today))
        
    # 💡 [개선] 기존 Full 데이터 로드 시 max_sequence_id 파악
    all_full_posts = []
    max_sequence_id = 0
    if os.path.exists(full_file):
        with open(full_file, 'r', encoding='utf-8-sig') as f:
            try: 
                full_data_existing = json.load(f)
                all_full_posts = full_data_existing.get('posts', [])
                max_sequence_id = full_data_existing.get('metadata', {}).get('max_sequence_id', 0)
            except: pass
    
    # 💡 [핵심] simple 파일(posts)에서 수집 완료된 모든 항목을 우선순위로 병합
    full_map = {str(p['id']): p for p in all_full_posts}
    for p in posts:
        if p.get('is_detail_collected'):
            pid = str(p['id'])
            # simple 파일의 메타데이터(sequence_id, crawled_at)를 full 파일에 강제 주입
            if pid in full_map:
                full_map[pid].update(p)
            else:
                full_map[pid] = p
            
            # max_sequence_id 갱신
            sid = p.get('sequence_id', 0)
            if sid > max_sequence_id: max_sequence_id = sid
    
    final_posts = sorted(full_map.values(), key=lambda x: x.get('sequence_id', 0), reverse=True)
    
    if final_posts:
        with open(full_file, 'w', encoding='utf-8-sig') as f:
            json.dump({
                "metadata": {
                    "updated_at": datetime.now().isoformat(), 
                    "total_count": len(final_posts), 
                    "max_sequence_id": max_sequence_id,
                    "platform": "x"
                },
                "posts": final_posts
            }, f, ensure_ascii=False, indent=4)
        print(f"📦 최종 상세 데이터 동기화 완료: {full_file} (max_sequence_id: {max_sequence_id}, total: {len(final_posts)})")
    
    # 💡 [추가] 상세 수집 업데이트 파일 생성
    if updated_count > 0:
        newly_updated_posts = [p for p in targets if p.get('is_detail_collected')]
        update_dir = os.path.join(OUTPUT_DIR, "update")
        os.makedirs(update_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        update_file = os.path.join(update_dir, f"twitter_py_full_update_{timestamp}.json")
        
        with open(update_file, 'w', encoding='utf-8-sig') as f:
            json.dump(newly_updated_posts, f, ensure_ascii=False, indent=4)
        print(f"📂 상세 수집 업데이트 저장: {update_file} ({updated_count}개)")

    with open(latest_simple, 'w', encoding='utf-8-sig') as f:
        json.dump(simple_data, f, ensure_ascii=False, indent=4)
        
    print(f"\n✨ 상세 수집 마감! 총 {updated_count}개 신규 갱신됨.")

if __name__ == "__main__":
    main()
