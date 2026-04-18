import os

import pytest
from playwright.sync_api import Playwright

from utils.auth_paths import linkedin_storage


@pytest.mark.smoke
def test_linkedin_session_validity(playwright: Playwright):
    """LinkedIn 세션 파일의 유효성을 검사합니다."""
    auth_file = str(linkedin_storage())
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=auth_file,
        user_agent=user_agent,
        locale="ko-KR",
    )
    page = context.new_page()

    print("🔗 LinkedIn 저장된 게시물 페이지 접속 중...")
    page.goto("https://www.linkedin.com/my-items/saved-posts/", wait_until="domcontentloaded")

    is_login_page = "login" in page.url or "signup" in page.url

    has_posts = False
    try:
        page.wait_for_selector(".entity-result__content-container", timeout=15000)
        has_posts = True
        print("✅ 게시물 발견! (Selector: .entity-result__content-container)")
    except Exception:
        count = page.locator("li").count()
        if count > 10:
            has_posts = True
            print(f"✅ 게시물 발견! (li count: {count})")

    current_url = page.url
    context.close()
    browser.close()

    assert not is_login_page, f"LinkedIn 세션이 만료되었습니다. (URL: {current_url})"
    assert has_posts, f"LinkedIn 저장된 게시물 목록을 로드하지 못했습니다. (URL: {current_url})"
