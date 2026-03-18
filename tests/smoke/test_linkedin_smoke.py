import pytest
import os
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_linkedin_session_validity():
    """LinkedIn 세션 파일의 유효성을 검사합니다."""
    auth_file = "auth/auth_linkedin.json"
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"
    
    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=auth_file,
            user_agent=user_agent,
            locale="ko-KR"
        )
        page = context.new_page()
        
        # 저장된 게시물 페이지 접속
        print(f"🔗 LinkedIn 저장된 게시물 페이지 접속 중...")
        page.goto("https://www.linkedin.com/my-items/saved-posts/", wait_until="domcontentloaded")
        
        # 로그인 화면으로 리다이렉트되었는지 확인
        is_login_page = "login" in page.url or "signup" in page.url
        
        # 게시물 요소가 나타날 때까지 대기 (분석된 클래스 중 하나 선택)
        has_posts = False
        try:
            page.wait_for_selector('.entity-result__content-container', timeout=15000)
            has_posts = True
            print(f"✅ 게시물 발견! (Selector: .entity-result__content-container)")
        except Exception:
            # 보조 확인
            count = page.locator('li').count()
            if count > 10: # li가 많으면 목록이 로드된 것으로 간주 (LinkedIn 특성)
                has_posts = True
                print(f"✅ 게시물 발견! (li count: {count})")
        
        current_url = page.url
        browser.close()
        
        assert not is_login_page, f"LinkedIn 세션이 만료되었습니다. (URL: {current_url})"
        assert has_posts, f"LinkedIn 저장된 게시물 목록을 로드하지 못했습니다. (URL: {current_url})"
