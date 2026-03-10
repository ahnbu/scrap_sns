import pytest
import os
import requests
import time
from playwright.sync_api import Page, expect

@pytest.fixture(scope="session", autouse=True)
def check_server():
    url = "http://localhost:5000/api/status"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True
    except requests.exceptions.ConnectionError:
        pytest.skip("Flask server is not running on http://localhost:5000.")
    return False

@pytest.mark.e2e
def test_web_viewer_loading(page: Page):
    page.goto("http://localhost:5000/")
    
    # Masonry 그리드 존재 확인
    expect(page.locator("#masonryGrid")).to_be_visible(timeout=10000)
    
    # 데이터 로딩 대기 (로컬 호스트이므로 빠르지만, fetch 시간이 필요할 수 있음)
    page.wait_for_timeout(3000)
    
    # 게시물이 1개 이상 노출되는지 확인
    # index.html 구조상 .group.relative.bg-card 요소 확인
    cards = page.locator("#masonryGrid > div")
    count = cards.count()
    print(f"Loaded posts count: {count}")
    assert count > 0, "No posts loaded in the viewer."

@pytest.mark.e2e
def test_sns_filtering(page: Page):
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)
    
    # filterContainer 내의 버튼들 확인
    # 예: "Threads" 텍스트를 가진 버튼
    threads_btn = page.locator("#filterContainer button:has-text('Threads')")
    if threads_btn.count() > 0:
        threads_btn.click()
        page.wait_for_timeout(1000)
        
        # 필터링 후 가시적인 카드 확인
        visible_posts = page.locator("#masonryGrid > div:visible")
        assert visible_posts.count() > 0, "Filtered posts should be visible."
    else:
        pytest.skip("Threads filter button not found.")

@pytest.mark.e2e
def test_api_status_check():
    url = "http://localhost:5000/api/status"
    response = requests.get(url)
    assert response.status_code == 200
    assert response.json()["status"] == "running"

@pytest.mark.e2e
def test_management_modal_open(page: Page):
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)
    
    settings_btn = page.locator("#settingsBtn")
    expect(settings_btn).to_be_visible()
    settings_btn.click()
    
    # 모달 가시성 확인
    expect(page.locator("#managementModal")).to_be_visible()
    
    # 닫기 버튼 클릭
    close_btn = page.locator("#closeManagementModal")
    close_btn.click()
    expect(page.locator("#managementModal")).not_to_be_visible()
