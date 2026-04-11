import os
import pytest
from utils.threads_parser import extract_json_from_html, extract_items_multi_path

@pytest.fixture
def sample_html():
    fixture_path = os.path.join("tests", "fixtures", "threads_sample.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return f.read()

def test_extract_json_from_html_success(sample_html):
    """HTML 샘플에서 JSON 데이터가 성공적으로 추출되는지 확인"""
    # 현재 Mock HTML에는 '"result":{"data"' 문자열이 포함되어 있어야 함
    # 실제 파서 로직에 맞춰 샘플 HTML 구조를 다시 조정해야 할 수도 있음
    data = extract_json_from_html(sample_html)
    assert data is not None
    assert "data" in data
    assert "thread_items" in data["data"]

def test_extract_items_multi_path_content(sample_html):
    """추출된 JSON에서 게시글 내용이 정확한지 확인"""
    data = extract_json_from_html(sample_html)
    posts = extract_items_multi_path(data, "ROOT123", "testuser")
    
    assert len(posts) > 0
    post = posts[0]
    assert post["platform_id"] == "TESTCODE123"
    assert post["code"] == "TESTCODE123"
    assert post["full_text"] == "Hello TDD World!"
    assert post["username"] == "testuser"
    assert post["display_name"] == "testuser"
    assert post["url"] == "https://www.threads.net/@testuser/post/TESTCODE123"
    assert post["sns_platform"] == "threads"

def test_extract_json_from_invalid_html():
    """잘못된 HTML에서 None을 반환하는지 확인"""
    invalid_html = "<html><body>No data here</body></html>"
    data = extract_json_from_html(invalid_html)
    assert data is None
