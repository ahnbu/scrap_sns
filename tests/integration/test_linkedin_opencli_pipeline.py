from datetime import datetime

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


def test_collect_opencli_posts_cleans_browser_session_before_daemon_stop(monkeypatch):
    import linkedin_scrap

    events = []

    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend(["unbind", "close"]),
        raising=False,
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append("stop"), raising=False)
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_whoami",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: (
            "raw",
            {"pages_collected": 1, "total_unique_activity_ids": 1},
        ),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: {
            "metadata": {
                "parsed_post_count": 1,
                "duplicate_platform_id_count": 0,
                "parser_failed_count": 0,
                "entity_without_save_state_count": 0,
                "entity_without_cluster_reference_count": 0,
            },
            "posts": [{"platform_id": "1"}],
        },
    )

    posts, metadata = linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert posts == [{"platform_id": "1"}]
    assert metadata["opencli_collection"] == {"pages_collected": 1, "total_unique_activity_ids": 1}
    assert events == ["unbind", "close", "stop"]


def test_collect_opencli_posts_keeps_browser_cleanup_when_daemon_stop_is_disabled(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setenv("SCRAP_SNS_KEEP_OPENCLI_DAEMON", "1")
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend(["unbind", "close"]),
        raising=False,
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append("stop"), raising=False)
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_whoami",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: (
            "raw",
            {"pages_collected": 1, "total_unique_activity_ids": 1},
        ),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: {
            "metadata": {
                "parsed_post_count": 1,
                "duplicate_platform_id_count": 0,
                "parser_failed_count": 0,
                "entity_without_save_state_count": 0,
                "entity_without_cluster_reference_count": 0,
            },
            "posts": [{"platform_id": "1"}],
        },
    )

    linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == ["unbind", "close"]


def test_cleanup_opencli_browser_session_attempts_close_after_unbind_failure(monkeypatch):
    import linkedin_scrap

    events = []

    def fake_browser_command(action, session=linkedin_scrap.OPENCLI_PRODUCTION_SESSION):
        events.append(action)
        return action != "unbind"

    monkeypatch.setattr(linkedin_scrap, "run_opencli_browser_session_command", fake_browser_command)

    linkedin_scrap.cleanup_opencli_browser_session()

    assert events == ["unbind", "close"]
