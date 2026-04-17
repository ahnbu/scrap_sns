import pytest

from thread_scrap_single import _assert_threads_schema, merge_thread_items
from utils.threads_parser import extract_items_multi_path, extract_json_from_html


@pytest.fixture
def sample_html():
    with open("tests/fixtures/threads_sample.html", "r", encoding="utf-8") as f:
        return f.read()


def test_extract_items_multi_path_returns_standard_threads_keys(sample_html):
    data = extract_json_from_html(sample_html)

    posts = extract_items_multi_path(data, "ROOT123", "testuser")

    assert len(posts) == 1
    post = posts[0]
    assert post["platform_id"] == "TESTCODE123"
    assert post["code"] == "TESTCODE123"
    assert post["username"] == "testuser"
    assert post["display_name"] == "testuser"
    assert post["url"] == "https://www.threads.com/@testuser/post/TESTCODE123"
    assert post["created_at"]
    assert post["date"] == post["created_at"].split(" ")[0]
    assert "user" not in post
    assert "timestamp" not in post


def test_merge_thread_items_normalizes_legacy_threads_fields():
    merged = merge_thread_items(
        [
            {
                "code": "TESTCODE123",
                "root_code": "ROOT123",
                "user": "testuser",
                "timestamp": "2026-04-11 10:00:00",
                "full_text": "first",
                "media": ["https://example.com/1.jpg"],
                "sns_platform": "threads",
            },
            {
                "code": "TESTCODE124",
                "root_code": "ROOT123",
                "user": "testuser",
                "timestamp": "2026-04-11 10:01:00",
                "full_text": "second",
                "media": ["https://example.com/2.jpg"],
                "sns_platform": "threads",
            },
        ]
    )

    assert merged["platform_id"] == "TESTCODE123"
    assert merged["username"] == "testuser"
    assert merged["display_name"] == "testuser"
    assert merged["url"] == "https://www.threads.com/@testuser/post/TESTCODE123"
    assert merged["is_merged_thread"] is True
    assert merged["original_item_count"] == 2
    assert merged["full_text"] == "first\n\n---\n\nsecond"
    assert "user" not in merged
    assert "timestamp" not in merged


def test_assert_threads_schema_rejects_legacy_threads_posts():
    with pytest.raises(RuntimeError):
        _assert_threads_schema(
            [
                {
                    "sns_platform": "threads",
                    "code": "TESTCODE123",
                    "user": "testuser",
                    "full_text": "body",
                }
            ],
            "test-bad",
        )


def test_assert_threads_schema_accepts_standard_threads_posts():
    _assert_threads_schema(
        [
            {
                "sns_platform": "threads",
                "platform_id": "TESTCODE123",
                "username": "testuser",
                "display_name": "testuser",
                "url": "https://www.threads.com/@testuser/post/TESTCODE123",
                "created_at": "2026-04-11 10:00:00",
                "full_text": "body",
            }
        ],
        "test-good",
    )
