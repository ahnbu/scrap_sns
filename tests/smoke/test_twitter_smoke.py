import pytest
import os
from playwright.sync_api import sync_playwright

@pytest.mark.smoke
def test_twitter_session_validity():
    """Twitter(X) Persistent Context의 유효성을 검사합니다."""
    user_data_dir = os.path.join(os.getcwd(), "auth", "x_user_data")
    assert os.path.exists(user_data_dir), f"세션 디렉토리가 없습니다: {user_data_dir}"

    with sync_playwright() as p:
        # 실제 Chrome 채널을 사용하여 세션 로드
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                channel="chrome"
            )
            page = context.pages[0]
            
            page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            is_login_page = "login" in page.url or "i/flow/login" in page.url
            
            # 페이지 제목이나 기사 요소 확인
            has_content = page.locator('article').count() > 0 or "Bookmarks" in page.title()
            
            current_url = page.url
            context.close()

            assert not is_login_page, f"Twitter(X) 세션이 만료되었습니다. (URL: {current_url})"
            assert has_content, "Twitter(X) 북마크 목록을 로드하지 못했습니다."
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                pytest.skip("Chrome executable not found. Skip Twitter smoke test.")
            else:
                raise e
