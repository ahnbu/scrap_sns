import json
from pathlib import Path

from utils.threads_parser import extract_items_multi_path, extract_json_from_html


def test_extract_json_from_html_handles_braces_inside_strings():
    html = Path(
        "tests/fixtures/snapshots/threads/snapshot_1777853522.html"
    ).read_text(encoding="utf-8")

    data = extract_json_from_html(html)
    items = extract_items_multi_path(data, "DXu-Y9XCov1", "aicoffeechat")

    assert [item["code"] for item in items] == [
        "DXu-Y9XCov1",
        "DXvrp3FE_vc",
        "DXvrqXrEzJb",
        "DXvrq20E1aZ",
        "DXvrrXyk7zD",
        "DXvrr5VkyS_",
        "DXvrsa_E1-q",
        "DXvrsu0k556",
        "DXvrtI5k8vF",
        "DXvrtxyk1Iw",
        "DXvru3OE1J3",
    ]


def test_extract_items_multi_path_handles_null_text_post_app_info():
    payload = {
        "result": {
            "data": {
                "data": {
                    "thread_items": [
                        {
                            "post": {
                                "code": "ROOT123",
                                "pk": "root-pk",
                                "user": {
                                    "pk": "12345",
                                    "username": "testuser",
                                    "full_name": "testuser",
                                },
                                "caption": {"text": "Root text"},
                                "taken_at": 1700000000,
                            }
                        },
                        {
                            "post": {
                                "code": "REPLY123",
                                "pk": "reply-pk",
                                "user": {
                                    "pk": "12345",
                                    "username": "testuser",
                                    "full_name": "testuser",
                                },
                                "caption": {"text": "Reply text"},
                                "taken_at": 1700000010,
                                "text_post_app_info": None,
                            }
                        },
                    ]
                }
            }
        }
    }

    # Ensure the fixture stays JSON-serializable like the embedded Threads payload.
    payload = json.loads(json.dumps(payload))

    items = extract_items_multi_path(payload, "ROOT123", "testuser")

    assert [item["code"] for item in items] == ["ROOT123", "REPLY123"]


def test_extract_items_multi_path_handles_null_caption():
    payload = {
        "result": {
            "data": {
                "data": {
                    "thread_items": [
                        {
                            "post": {
                                "code": "ROOT123",
                                "pk": "root-pk",
                                "user": {
                                    "pk": "12345",
                                    "username": "testuser",
                                    "full_name": "testuser",
                                },
                                "caption": {"text": "Root text"},
                                "taken_at": 1700000000,
                            }
                        },
                        {
                            "post": {
                                "code": "REPLY123",
                                "pk": "reply-pk",
                                "user": {
                                    "pk": "12345",
                                    "username": "testuser",
                                    "full_name": "testuser",
                                },
                                "caption": None,
                                "taken_at": 1700000010,
                                "image_versions2": {
                                    "candidates": [{"url": "https://example.com/image.jpg"}]
                                },
                            }
                        },
                    ]
                }
            }
        }
    }

    items = extract_items_multi_path(payload, "ROOT123", "testuser")

    assert items[1]["code"] == "REPLY123"
    assert items[1]["full_text"] == ""
    assert items[1]["media"] == ["https://example.com/image.jpg"]
