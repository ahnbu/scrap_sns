import os
import pytest
from utils.twitter_parser import parse_twitter_html

@pytest.fixture
def sample_html():
    fixture_path = os.path.join("tests", "fixtures", "twitter_sample.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return f.read()

def test_parse_twitter_html(sample_html):
    full_text, media, real_user = parse_twitter_html(
        sample_html, 
        target_user="fallback_user", 
        original_url="https://x.com/test_user_x/status/12345"
    )
    
    assert real_user == "test_user_x"
    
    # 두 개의 트윗 본문이 병합되어야 함
    assert "Hello Twitter TDD!" in full_text
    assert "And here is the thread continuation." in full_text
    assert "ignored" not in full_text # 다른 유저의 답글은 무시됨
    
    # 미디어 URL 변환 검증 (wsrv.nl 프록시)
    assert len(media) == 1
    assert media[0] == "https://wsrv.nl/?url=https://pbs.twimg.com/media/xyz.jpg"

def test_parse_twitter_html_no_url(sample_html):
    # URL 없이 HTML 내부의 User-Name 태그에서 유저명 추출하는지 테스트
    full_text, media, real_user = parse_twitter_html(
        sample_html, 
        target_user="fallback_user", 
        original_url=None
    )
    
    assert real_user == "test_user_x"
