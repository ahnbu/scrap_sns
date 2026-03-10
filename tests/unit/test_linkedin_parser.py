import os
import json
import pytest
from datetime import datetime
from utils.linkedin_parser import parse_linkedin_post, extract_urn_id

@pytest.fixture
def sample_json():
    fixture_path = os.path.join("tests", "fixtures", "linkedin_sample.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_extract_urn_id():
    urn = "urn:li:activity:7422622332021604353"
    assert extract_urn_id(urn) == "7422622332021604353"
    
    invalid_urn = "urn:li:member:123"
    assert extract_urn_id(invalid_urn) == "urn:li:member:123"

def test_parse_linkedin_post(sample_json):
    items = sample_json.get("included", [])
    valid_item = items[0]
    
    crawl_time = datetime(2026, 3, 10, 12, 0, 0)
    post = parse_linkedin_post(valid_item, include_images=True, crawl_start_time=crawl_time)
    
    assert post is not None
    assert post["platform_id"] == "7422622332021604353"
    assert post["sns_platform"] == "linkedin"
    assert post["username"] == "testuser"
    assert post["display_name"] == "Test User"
    assert post["full_text"] == "Hello LinkedIn TDD!"
    assert post["url"] == "https://www.linkedin.com/feed/update/urn:li:activity:7422622332021604353"
    assert post["time_text"] == "2h"
    assert post["profile_slogan"] == "Software Engineer"
    
    # Image check
    assert len(post["media"]) > 0
    assert "media.licdn.com" in post["media"][0]
    assert "feedshare-shrink_800/img.jpg" in post["media"][0]

def test_parse_linkedin_post_invalid(sample_json):
    items = sample_json.get("included", [])
    invalid_item = items[1]
    
    # extract_urn_id('urn:li:activity:INVALID') returns 'urn:li:activity:INVALID'
    # get_date_from_snowflake_id('urn:li:activity:INVALID') returns None
    post = parse_linkedin_post(invalid_item)
    assert post is not None
    assert post["platform_id"] == "urn:li:activity:INVALID"
    assert post["created_at"] is None
