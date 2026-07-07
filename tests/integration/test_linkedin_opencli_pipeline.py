import pytest

from linkedin_scrap import (
    configure_text_output,
    merge_linkedin_full_posts,
    validate_opencli_payload,
)


class FakeCp949Stream:
    encoding = "cp949"

    def __init__(self):
        self.reconfigured = None

    def reconfigure(self, **kwargs):
        self.reconfigured = kwargs


def test_configure_text_output_switches_cp949_stream_to_utf8():
    stream = FakeCp949Stream()

    configure_text_output(stream)

    assert stream.reconfigured == {"encoding": "utf-8", "errors": "replace"}


def test_opencli_pipeline_merges_without_deleting_unobserved_existing():
    old_posts = [
        {"platform_id": "111", "sequence_id": 1, "full_text": "old retained", "media": []},
        {
            "platform_id": "222",
            "sequence_id": 2,
            "crawled_at": "2026-07-01T10:00:00",
            "full_text": "old updated",
            "media": [],
        },
    ]
    opencli_posts = [
        {"platform_id": "222", "sequence_id": 0, "full_text": "new text", "media": ["m1"]},
        {"platform_id": "333", "sequence_id": 0, "full_text": "new saved", "media": []},
    ]

    final_posts, new_items, report = merge_linkedin_full_posts(old_posts, opencli_posts, "update only")

    ids = {post["platform_id"] for post in final_posts}
    assert ids == {"111", "222", "333"}
    assert len(new_items) == 1
    assert report["unobserved_existing_count"] == 1
    updated = next(post for post in final_posts if post["platform_id"] == "222")
    assert updated["sequence_id"] == 2
    assert updated["crawled_at"] == "2026-07-01T10:00:00"
    assert updated["media"] == ["m1"]


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"parsed_post_count": 0}, "OpenCLI parsed post count is zero"),
        (
            {"parsed_post_count": 1, "duplicate_platform_id_count": 1},
            "OpenCLI duplicate platform_id detected",
        ),
        (
            {"parsed_post_count": 1, "parser_failed_count": 1},
            "OpenCLI parser failed for one or more posts",
        ),
        (
            {"parsed_post_count": 1, "entity_without_save_state_count": 1},
            "OpenCLI SaveState verification failed",
        ),
        (
            {"parsed_post_count": 1, "entity_without_cluster_reference_count": 1},
            "OpenCLI cluster reference verification failed",
        ),
    ],
)
def test_validation_failure_stops_before_writing_full_file(metadata, message):
    payload = {
        "metadata": {
            "parsed_post_count": 1,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
            **metadata,
        },
        "posts": [],
    }

    with pytest.raises(RuntimeError, match=message):
        validate_opencli_payload(payload)


def test_validate_opencli_payload_accepts_clean_payload():
    payload = {
        "metadata": {
            "parsed_post_count": 1,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
        },
        "posts": [{"platform_id": "333"}],
    }

    validate_opencli_payload(payload)
