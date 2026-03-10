import pytest
import os
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_linkedin_find_locators():
    auth_file = "auth/auth_linkedin.json"
    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=auth_file, user_agent=user_agent)
        page = context.new_page()
        page.goto("https://www.linkedin.com/my-items/saved-posts/")
        page.wait_for_timeout(5000)
        
        # 특정 클래스 패턴을 가진 요소들 찾기
        # 'result'나 'post' 단어가 포함된 클래스들
        elements = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.className && typeof el.className === 'string' && el.className.includes('result')) {
                        results.push(el.className);
                    }
                });
                return [...new Set(results)].slice(0, 20);
            }
        """)
        print(f"Found class names with 'result': {elements}")
        
        # 게시물로 추정되는 요소의 갯수 확인
        print(f"li count: {page.locator('li').count()}")
        print(f"article count: {page.locator('article').count()}")
        
        browser.close()
