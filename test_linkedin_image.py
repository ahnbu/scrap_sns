import json
import time
import os
from playwright.sync_api import sync_playwright

AUTH_FILE = "auth/auth_linkedin.json"
TEST_URL = "https://www.linkedin.com/feed/update/urn:li:activity:7427324639552581632/"

def test_image_scraping():
    print(f"🚀 이미지 스크랩 테스트 시작: {TEST_URL}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context_options = {}
        if os.path.exists(AUTH_FILE):
            context_options["storage_state"] = AUTH_FILE
        
        context = browser.new_context(**context_options)
        page = context.new_page()
        
        # 네트워크 응답 캡처
        captured_data = []
        def handle_response(response):
            if "voyager/api/graphql" in response.url:
                try:
                    captured_data.append(response.json())
                except:
                    pass
        
        page.goto(TEST_URL)
        time.sleep(5) 
        
        # DOM 분석을 통해 이미지 추출
        images = page.query_selector_all('img')
        found_images = []
        for img in images:
            src = img.get_attribute('src')
            if src and 'media.licdn.com/dms/image' in src:
                alt = img.get_attribute('alt') or ''
                found_images.append({"src": src, "alt": alt})
        
        print(f"📸 발견된 이미지: {len(found_images)}개")
        for idx, img in enumerate(found_images):
            print(f"   [{idx+1}] {img['src'][:100]}... (Alt: {img['alt']})")

        with open("docs/linkedin_saved/debug_image_dom.json", "w", encoding="utf-8") as f:
            json.dump(found_images, f, ensure_ascii=False, indent=2)

        
        browser.close()

if __name__ == "__main__":
    test_image_scraping()
