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

def test_parse_linkedin_post_keeps_opencli_high_res_feedshare_media():
    item = {
        "$type": "com.linkedin.voyager.dash.search.EntityResultViewModel",
        "entityUrn": "urn:li:fsd_entityResultViewModel:(urn:li:activity:7417789055347863552,SEARCH_SRP,DEFAULT)",
        "navigationUrl": "https://www.linkedin.com/feed/update/urn:li:activity:7417789055347863552",
        "actorNavigationUrl": "https://www.linkedin.com/in/testuser/",
        "title": {"text": "Test User"},
        "summary": {"text": "OpenCLI high-res media test"},
        "primarySubtitle": {"text": "Software Engineer"},
        "secondarySubtitle": {"text": "1h"},
        "image": {
            "$type": "com.linkedin.voyager.dash.common.image.ImageViewModel",
            "attributes": [
                {
                    "detailData": {
                        "nonEntityProfilePicture": {
                            "vectorImage": {
                                "$type": "com.linkedin.common.VectorImage",
                                "rootUrl": "",
                                "artifacts": [
                                    {
                                        "fileIdentifyingUrlPathSegment": "https://media.licdn.com/dms/image/v2/D5603AQProfile/profile-displayphoto-shrink_100_100/profile-displayphoto-shrink_100_100/0/profile.jpg",
                                        "width": 100,
                                    }
                                ],
                            }
                        }
                    }
                }
            ],
        },
        "entityEmbeddedObject": {
            "image": {
                "$type": "com.linkedin.voyager.dash.common.image.ImageViewModel",
                "attributes": [
                    {
                        "detailData": {
                            "vectorImage": {
                                "$type": "com.linkedin.common.VectorImage",
                                "rootUrl": "https://media.licdn.com/dms/image/v2/D5622AQEF1D2ssqQ5gw/feedshare-",
                                "artifacts": [
                                    {
                                        "fileIdentifyingUrlPathSegment": "shrink_800/B56ZvFH1jXJ0Ak-/0/test.jpg",
                                        "width": 800,
                                    },
                                    {
                                        "fileIdentifyingUrlPathSegment": "image-high-res/B56ZvFH1jXJ0AY-/0/test.jpg",
                                        "width": 2048,
                                    },
                                ],
                            }
                        }
                    }
                ],
            }
        },
    }

    post = parse_linkedin_post(item, include_images=True, crawl_start_time=datetime(2026, 7, 7, 12, 0, 0))

    assert post is not None
    assert len(post["media"]) == 1
    assert "feedshare-image-high-res" in post["media"][0]
    assert "profile-displayphoto" not in post["media"][0]
