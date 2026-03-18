"""
파서 통합 테스트 (P1~P4)
fixture → 파서 체인 → 표준 스키마 검증

Unit 테스트와 중복 방지: 스키마 준수 + 필드 완전성에 집중
"""
import os
import json
import pytest

from utils.threads_parser import extract_json_from_html, extract_items_multi_path
from utils.linkedin_parser import parse_linkedin_post
from utils.twitter_parser import parse_twitter_html
from utils.common import clean_text

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")

REQUIRED_FIELDS = [
    "sns_platform", "full_text"
]

THREADS_REQUIRED = ["code", "user", "sns_platform", "full_text"]
LINKEDIN_REQUIRED = ["platform_id", "username", "full_text", "sns_platform"]
TWITTER_REQUIRED = ["full_text"]


@pytest.mark.integration
def test_p1_threads_full_pipeline():
    """P1: HTML → extract_json → extract_items → 표준 스키마"""
    html_path = os.path.join(FIXTURES_DIR, "threads_sample.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    data = extract_json_from_html(html)
    assert data is not None, "extract_json_from_html returned None"

    posts = extract_items_multi_path(data, "ROOT123", "testuser")
    assert len(posts) > 0, "No posts extracted from Threads HTML"

    for post in posts:
        for field in THREADS_REQUIRED:
            assert field in post, f"Missing field: {field}"
            assert post[field], f"Empty field: {field}"
        assert post["sns_platform"] == "threads"


@pytest.mark.integration
def test_p2_linkedin_full_pipeline():
    """P2: JSON → parse_linkedin_post → 표준 스키마"""
    json_path = os.path.join(FIXTURES_DIR, "linkedin_sample.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("included", [])
    parsed_posts = []
    for item in items:
        result = parse_linkedin_post(item)
        if result:
            parsed_posts.append(result)

    assert len(parsed_posts) > 0, "No valid posts parsed from LinkedIn JSON"

    # 유효한 게시물 (username, full_text가 있는 것)만 검증
    valid_posts = [p for p in parsed_posts if p.get("username") and p.get("full_text")]
    assert len(valid_posts) > 0, "No fully valid posts found"

    for post in valid_posts:
        for field in LINKEDIN_REQUIRED:
            assert field in post, f"Missing field: {field}"
            assert post[field], f"Empty field: {field}"
        assert post["sns_platform"] == "linkedin"


@pytest.mark.integration
def test_p3_twitter_full_pipeline():
    """P3: HTML → parse_twitter_html → 본문+미디어+유저"""
    html_path = os.path.join(FIXTURES_DIR, "twitter_sample.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    full_text, media, real_user = parse_twitter_html(html, "test_user_x")

    assert full_text, "Twitter full_text is empty"
    assert "Hello Twitter TDD" in full_text
    assert real_user == "test_user_x"
    assert isinstance(media, list)


@pytest.mark.integration
def test_p4_emoji_safety():
    """P4: 이모지/특수문자가 clean_text 통과 후 원본 유지"""
    emoji_texts = [
        "🚀 Launch day! 🎉",
        "한글 + English + 日本語 + 🇰🇷🇺🇸",
        "Math: 2 × 3 = 6, √4 = 2",
        "Special: \u00abquotes\u00bb \u201csmart\u201d \u2018single\u2019",
        "Zero-width: a\u200bb\u200cc",  # ZWS, ZWNJ
    ]
    for text in emoji_texts:
        result = clean_text(text)
        assert result == text.strip(), f"Emoji/special char corrupted: {repr(text)} → {repr(result)}"
