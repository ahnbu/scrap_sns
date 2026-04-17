import os

import pytest
from playwright.sync_api import Playwright


@pytest.mark.smoke
def test_threads_session_validity(playwright: Playwright):
    """Threads 세션 파일의 유효성을 검사합니다."""
    auth_file = "auth/auth_threads.json"
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=auth_file)
    page = context.new_page()

    page.goto("https://www.threads.com/saved")
    page.wait_for_timeout(3000)

    login_input = page.locator('input[name="username"]')
    is_logged_in = login_input.count() == 0

    current_url = page.url
    context.close()
    browser.close()

    assert is_logged_in, f"Threads 세션이 만료되었습니다. 다시 로그인이 필요합니다. (URL: {current_url})"


@pytest.mark.smoke
def test_threads_scraping_smoke(playwright: Playwright):
    """Threads에서 실제 1개 이상의 게시물을 가로챌 수 있는지 확인합니다."""
    auth_file = "auth/auth_threads.json"
    assert os.path.exists(auth_file), f"세션 파일이 없습니다: {auth_file}"

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=auth_file)
    page = context.new_page()

    collected = []

    def handle_response(response):
        if "graphql" in response.url:
            try:
                data = response.json()
                if "data" in data:
                    collected.append(data)
            except Exception:
                pass

    page.on("response", handle_response)
    page.goto("https://www.threads.com/saved")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)

    context.close()
    browser.close()

    assert len(collected) > 0, "Threads GraphQL 응답을 가로채지 못했습니다. 네트워크 상태나 세션을 확인하세요."
