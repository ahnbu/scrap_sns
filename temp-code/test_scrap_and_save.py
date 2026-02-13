import asyncio
import os
import json
import re
from playwright.async_api import async_playwright
from datetime import datetime

# ===========================
# Configuration
# ===========================
TARGETS = [
    {"url": "https://x.com/aiwithjainam/status/1994363245512241167", "user": "aiwithjainam", "id": "1994363245512241167"},
    {"url": "https://x.com/AIBopyo/status/2001386676153729456", "user": "AIBopyo", "id": "2001386676153729456"},
    {"url": "https://x.com/dotey/status/2013044625238339994", "user": "dotey", "id": "2013044625238339994"}
]
USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")
SAVE_PATH = "output_twitter/python/update/twitter_test_save_20260212.json"

async def scrape_target(page, target):
    url = target["url"]
    real_user = target["user"]
    print(f"\n[Thread Scraping] @{real_user} -> {url}")
    
    collected_data = None
    try:
        await page.goto(url, wait_until="domcontentloaded")
        
        tweet_texts = []
        tweet_media = set()
        last_count = 0
        stable_rounds = 0
        
        for scroll_step in range(8):
            if "for-you" in page.url:
                print(f"   ⚠️ @{real_user}: Redirected! Finalizing.")
                break
            
            # Click "Show more"
            show_more = page.locator('span:has-text("Show more"), span:has-text("더 보기")').first
            if await show_more.count() > 0:
                try: await show_more.click(); await asyncio.sleep(1)
                except: pass

            articles = await page.locator('article[data-testid="tweet"]').all()
            current_texts = []
            
            for i, article in enumerate(articles):
                is_author = await article.evaluate('''(el, user) => {
                    let links = el.querySelectorAll('a[href^="/"]');
                    for(let l of links) {
                        let href = l.getAttribute('href').toLowerCase();
                        if(href === '/' + user.toLowerCase() || href === '/' + user.toLowerCase() + '/') return true;
                    }
                    return false;
                }''', real_user)
                
                if is_author or i == 0:
                    text_el = article.locator('div[data-testid="tweetText"]').first
                    if await text_el.count() > 0:
                        txt = await text_el.inner_text()
                        if txt and txt not in current_texts:
                            current_texts.append(txt)
            
            if len(current_texts) > last_count:
                tweet_texts = current_texts
                last_count = len(tweet_texts)
                stable_rounds = 0
                print(f"   📥 @{real_user}: Found {last_count} segments.")
            else:
                stable_rounds += 1
            
            if stable_rounds >= 3: break
            
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(1.5)

        if tweet_texts:
            collected_data = {
                "platform_id": target["id"],
                "username": real_user,
                "full_text": "\n\n---\n\n".join(tweet_texts),
                "url": url,
                "is_detail_collected": True,
                "source": "async_logged_in_scrap",
                "segment_count": len(tweet_texts)
            }
            
    except Exception as e:
        print(f"   ⚠️ @{real_user} Error: {e}")
    
    return collected_data

async def main():
    print("🚀 Starting Login-Aware Thread Scraping...")
    
    # Clean lock
    lock_file = os.path.join(USER_DATA_DIR, "SingletonLock")
    if os.path.exists(lock_file):
        try: os.remove(lock_file)
        except: pass

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1000, "height": 800}
        )
        
        page = context.pages[0]
        print("\n🔍 Checking login status...")
        await page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
        
        # Check if we are on the login page or bookmarks
        if "login" in page.url or not await page.locator('article[data-testid="tweet"]').first.count() > 0:
            print("\n" + "!"*60)
            print("🛑 LOGIN REQUIRED: Please log in to X in the browser window.")
            print("   The script will resume automatically once bookmarks are visible.")
            print("!"*60)
            # Wait until bookmarks (tweets) are visible
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=0)
            print("✅ Login detected! Proceeding to targets...")
        else:
            print("✅ Session active. Proceeding...")

        # Now open tabs for targets
        pages = [page] # Use the current page for the first target
        for _ in range(len(TARGETS) - 1):
            pages.append(await context.new_page())
            
        # Execute (sequentially for better focus during observation, but tabs remain)
        results = []
        for i, target in enumerate(TARGETS):
            post = await scrape_target(pages[i], target)
            if post: results.append(post)
            await asyncio.sleep(1)

        if results:
            os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
            with open(SAVE_PATH, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            print(f"\n✨ Success! Saved {len(results)} posts to {SAVE_PATH}")

        print("\n" + "="*60)
        print("🛑 Observation Mode: Tabs are open.")
        print("   Verify the thread content and press Enter to finish.")
        print("="*60)
        await asyncio.get_event_loop().run_in_executor(None, input, ">>> Press Enter: ")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
