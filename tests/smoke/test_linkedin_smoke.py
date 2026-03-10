import pytest
import os
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_linkedin_session_validity():
    """LinkedIn 세션 파일의 유효성을 검사합니다."""
    auth_file = "auth/auth_linkedin.json"
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()
        
        # 저장된 게시물 페이지 접속
        page.goto("https://www.linkedin.com/my-items/saved-posts/")
        page.wait_for_timeout(5000)
        
        # 로그인 화면으로 리다이렉트되었는지 확인
        is_login_page = "login" in page.url or "signup" in page.url
        
        # 특정 게시물 컨테이너가 로딩되는지 확인
        post_container = page.locator('.reusable-search__entity-result-list')
        has_posts = post_container.count() > 0
        
        current_url = page.url
        browser.close()
        
        assert not is_login_page, f"LinkedIn 세션이 만료되었습니다. (URL: {current_url})"
        assert has_posts, "LinkedIn 저장된 게시물 목록을 로드하지 못했습니다."
