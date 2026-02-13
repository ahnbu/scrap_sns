import os
import time
import json
import re
from playwright.sync_api import sync_playwright

# ===========================
# Configuration
# ===========================
TARGET_URL = "https://x.com/aiwithjainam/status/1994363245512241167"
TARGET_USER = "aiwithjainam"
USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")

def observe_scrap():
    print("Starting observation mode for: " + TARGET_URL)
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0]
        
        try:
            print("Accessing page...")
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            
            print("Please check the browser window. Waiting for 10 seconds for popups/ads...")
            time.sleep(10) 
            
            articles = page.locator('article[data-testid="tweet"]').all()
            print("\nFound " + str(len(articles)) + " article elements.")
            
            for i, article in enumerate(articles):
                print("\n--- [Article " + str(i) + "] ---")
                
                # 1. Check Author Links
                links = article.locator('a[href^="/"]').all()
                hrefs = []
                for link in links:
                    h = link.get_attribute("href")
                    if h: hrefs.append(h)
                print("   Hrefs: " + str(hrefs[:5]))
                
                # 2. Check Text
                text_els = article.locator('div[data-testid="tweetText"]').all()
                for j, t_el in enumerate(text_els):
                    txt = t_el.inner_text()
                    print("   Text " + str(j) + ": " + txt[:100].replace("\n", " "))

            print("\n" + "="*50)
            print("Browser remains open for observation.")
            print("Press Enter in this terminal to close and exit.")
            print("="*50)
            input(">>> Press Enter to finish: ")
            
        except Exception as e:
            print("Error occurred: " + str(e))
        finally:
            context.close()

if __name__ == "__main__":
    observe_scrap()
