import os
import json
import re
from playwright.sync_api import sync_playwright

def test_extraction(file_path, real_user):
    print(f"\n--- Testing: {file_path} (User: {real_user}) ---")
    abs_path = "file://" + os.path.abspath(file_path).replace("\\", "/")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(abs_path)
        
        tweet_texts = []
        tweet_media = set()
        
        # twitter_scrap_single.py의 로직 복제
        articles = page.locator('article[data-testid="tweet"]').all()
        print(f"Found {len(articles)} articles.")
        
        for i, article in enumerate(articles):
            try:
                # 작성자 확인 로직 (대소문자 무시)
                links = article.locator('a[href^="/"]').all()
                is_author = False
                found_hrefs = []
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        found_hrefs.append(href)
                        if href.lower() == f"/{real_user.lower()}":
                            is_author = True
                            break
                
                if not is_author:
                    # print(f"  [Article {i}] Not author. Found hrefs: {found_hrefs[:5]}...")
                    continue
                
                text_els = article.locator('div[data-testid="tweetText"]').all()
                article_body = ""
                
                for t_el in text_els:
                    article_body = t_el.inner_text()
                    break 
                
                if article_body:
                    print(f"  [Article {i}] Text: {article_body[:50]}...")
                    if article_body not in tweet_texts:
                        tweet_texts.append(article_body)
                
                imgs = article.locator('img[src*="media"]').all()
                for img in imgs:
                    src = img.get_attribute("src")
                    if src:
                        tweet_media.add(src)
            except Exception as e:
                print(f"  [Article {i}] Error: {e}")

        print(f"Result: {len(tweet_texts)} texts, {len(tweet_media)} images.")
        browser.close()

if __name__ == "__main__":
    test_extraction("docs/twitter_saved/twitter_each_body.html", "aiwithmayank")
    test_extraction("docs/twitter_saved/twitter_each_full.html", "aiwithmayank")
