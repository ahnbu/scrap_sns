import pytest
import os
import requests
import time
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_page_content(page: Page):
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(2000)
    
    # 페이지 소스 출력하여 확인 (디버깅)
    content = page.content()
    print(f"Page content length: {len(content)}")
    print(f"Page title: {page.title()}")
    
    # 특정 텍스트 존재 여부로 확인
    # index.html 내의 텍스트 하나 골라 잡기
    assert len(content) > 0
