import os
import json
import re
from playwright.sync_api import sync_playwright

def test_extraction(file_path, real_user):
    print("--- Testing: " + file_path + " (User: " + real_user + ") ---")
    abs_path = "file://" + os.path.abspath(file_path).replace("\\", "/")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(abs_path)
        
        articles = page.locator('article[data-testid="tweet"]').all()
        print("Found " + str(len(articles)) + " articles.")
        
        if articles:
            article = articles[0]
            links = article.locator('a').all()
            print("Hrefs in first article:")
            for link in links:
                href = link.get_attribute("href")
                if href:
                    print("  - " + href)
        
        browser.close()

if __name__ == "__main__":
    test_extraction("docs/twitter_saved/twitter_each_body.html", "aiwithmayank")
    test_extraction("docs/twitter_saved/twitter_each_full.html", "aiwithmayank")
