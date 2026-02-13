import os
import time
import json
import re
from playwright.sync_api import sync_playwright

# ===========================
# Configuration
# ===========================
TARGETS = [
    {"url": "https://x.com/aiwithjainam/status/1994363245512241167", "user": "aiwithjainam"},
    {"url": "https://x.com/AIBopyo/status/2001386676153729456", "user": "AIBopyo"},
    {"url": "https://x.com/dotey/status/2013044625238339994", "user": "dotey"}
]
USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")

def fast_scrape_test(page, target_url, target_user):
    print("\n[Fast Scraping Attempt] " + target_url)
    try:
        # Start navigation
        page.goto(target_url, wait_until="commit")
        
        # Wait for tweet content or redirect
        # We use a short timeout and poll frequently
        found_content = False
        start_time = time.time()
        
        while time.time() - start_time < 10: # Max 10 seconds total
            if "for-you" in page.url:
                print("   ⚠️ Redirected to 'For You' page! Stopping.")
                break
            
            # Check if tweet text is present
            tweets = page.locator('article[data-testid="tweet"]').all()
            if tweets:
                # Try to find the author's tweet text
                for i, tweet in enumerate(tweets):
                    text_el = tweet.locator('div[data-testid="tweetText"]').first
                    if text_el.count() > 0:
                        txt = text_el.inner_text()
                        if txt and len(txt) > 10:
                            print("   ✨ Content detected before redirect! (Length: " + str(len(txt)) + ")")
                            print("      Text Preview: " + txt[:100].replace("\n", " "))
                            found_content = True
                            break
                if found_content: break
            
            time.sleep(0.2) # High frequency polling
            
        if not found_content:
            print("   ❌ Failed to capture content before redirect/timeout.")
        else:
            print("   ✅ Capture Successful.")

    except Exception as e:
        print("   ⚠️ Error during fast scrape: " + str(e))

def main():
    print("🚀 Starting Fast Scraping Experiment...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # We will use one tab per target to observe them all
        pages = []
        for i, target in enumerate(TARGETS):
            if i == 0:
                page = context.pages[0]
            else:
                page = context.new_page()
            
            pages.append(page)
            fast_scrape_test(page, target["url"], target["user"])
            # Don't sleep too long between tabs, we want to see them load
            time.sleep(1)

        print("\n" + "="*60)
        print("🛑 All tabs are kept open for your observation.")
        print("   Check if the 'For You' redirect happened after capture.")
        print("   Press Enter in this terminal to close all and finish.")
        print("="*60)
        input(">>> Press Enter to finish: ")
        
        context.close()

if __name__ == "__main__":
    main()
