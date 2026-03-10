import pytest
import os
import json
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_threads_session_validity():
    """Threads 세션 파일의 유효성을 검사합니다."""
    auth_file = "auth/auth_threads.json"
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()
        
        # 저장됨 페이지 접속
        page.goto("https://www.threads.net/saved")
        page.wait_for_timeout(3000)
        
        # 로그인 폼이 여전히 보이는지 확인 (세션 만료 여부)
        login_input = page.locator('input[name="username"]')
        is_logged_in = login_input.count() == 0
        
        # 로그인이 풀렸다면 현재 URL 확인
        current_url = page.url
        browser.close()
        
        assert is_logged_in, f"Threads 세션이 만료되었습니다. 다시 로그인이 필요합니다. (URL: {current_url})"

@pytest.mark.smoke
def test_threads_scraping_smoke():
    """Threads에서 실제 1개 이상의 게시물을 가로챌 수 있는지 확인합니다."""
    # 이 테스트는 실제 네트워크 상황에 따라 실패할 수 있으므로, 
    # 세션 유효성 확인을 주 목적으로 하며 데이터 수집은 덤으로 확인합니다.
    auth_file = "auth/auth_threads.json"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()
        
        collected = []
        def handle_response(response):
            if "graphql" in response.url:
                try:
                    data = response.json()
                    # 간단한 데이터 구조 확인
                    if "data" in data:
                        collected.append(data)
                except: pass

        page.on("response", handle_response)
        page.goto("https://www.threads.net/saved")
        
        # 스크롤 1회 수행하여 네트워크 호출 유도
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)
        
        browser.close()
        
        # 최소한의 네트워크 응답을 받았는지 확인
        assert len(collected) > 0, "Threads GraphQL 응답을 가로채지 못했습니다. 네트워크 상태나 세션을 확인하세요."
