import pytest
import os
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_linkedin_debug_view():
    auth_file = "auth/auth_linkedin.json"
    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=auth_file,
            user_agent=user_agent
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/my-items/saved-posts/")
        page.wait_for_timeout(10000) # 더 길게 대기
        
        print(f"Final URL: {page.url}")
        print(f"Page Title: {page.title()}")
        
        # 스크린샷 저장
        os.makedirs(".screenshot", exist_ok=True)
        page.screenshot(path=".screenshot/linkedin_saved_posts.png")
        
        # 텍스트 일부 출력
        content = page.content()
        print(f"Content length: {len(content)}")
        
        # h1, h2 태그 내용 출력
        headers = page.locator("h1, h2").all_inner_texts()
        print(f"Headers: {headers}")
        
        browser.close()
