from datetime import datetime

from scripts.linkedin_opencli_shadow_parse import (
    extract_cluster_entity_result_urns,
    extract_save_state_activity_ids,
    parse_shadow_detail,
)


def make_detail():
    entity_urn_saved = "urn:li:fsd_entityResultViewModel:(urn:li:activity:100,SEARCH_SRP,DEFAULT)"
    entity_urn_unsaved = "urn:li:fsd_entityResultViewModel:(urn:li:activity:200,SEARCH_SRP,DEFAULT)"
    return {
        "body": {
            "data": {
                "data": {
                    "searchDashClustersByAll": {
                        "elements": [
                            {
                                "items": [
                                    {
                                        "item": {
                                            "*entityResult": entity_urn_saved,
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
            "included": [
                {
                    "$type": "com.linkedin.voyager.dash.feed.SaveState",
                    "entityUrn": "urn:li:fsd_saveState:(SAVE,urn:li:activity:100)",
                    "saved": True,
                },
                {
                    "$type": "com.linkedin.voyager.dash.search.EntityResultViewModel",
                    "entityUrn": entity_urn_saved,
                    "navigationUrl": "https://www.linkedin.com/feed/update/urn:li:activity:100",
                    "actorNavigationUrl": "https://www.linkedin.com/in/saved/",
                    "title": {"text": "Saved Author"},
                    "summary": {"text": "Saved post"},
                    "primarySubtitle": {"text": "Role"},
                    "secondarySubtitle": {"text": "1h"},
                },
                {
                    "$type": "com.linkedin.voyager.dash.search.EntityResultViewModel",
                    "entityUrn": entity_urn_unsaved,
                    "navigationUrl": "https://www.linkedin.com/feed/update/urn:li:activity:200",
                    "actorNavigationUrl": "https://www.linkedin.com/in/unsaved/",
                    "title": {"text": "Unsaved Author"},
                    "summary": {"text": "Included but not a cluster result"},
                    "primarySubtitle": {"text": "Role"},
                    "secondarySubtitle": {"text": "1h"},
                },
            ],
        }
    }


def test_extracts_cluster_references_and_save_state_ids():
    detail = make_detail()

    assert extract_cluster_entity_result_urns(detail) == {
        "urn:li:fsd_entityResultViewModel:(urn:li:activity:100,SEARCH_SRP,DEFAULT)"
    }
    assert extract_save_state_activity_ids(detail) == {"100"}


def test_parse_shadow_detail_requires_cluster_reference_and_save_state():
    result = parse_shadow_detail(
        make_detail(),
        raw_path="fixture.json",
        crawl_start_time=datetime(2026, 7, 7, 12, 0, 0),
        require_save_state=True,
    )

    assert [post["platform_id"] for post in result["posts"]] == ["100"]
    assert result["metadata"]["cluster_entity_result_count"] == 1
    assert result["metadata"]["save_state_activity_count"] == 1
    assert result["metadata"]["entity_result_count"] == 2
    assert result["metadata"]["cluster_save_state_matched_post_count"] == 1
    assert result["metadata"]["entity_without_cluster_reference_count"] == 1
    assert result["metadata"]["entity_without_save_state_count"] == 1
