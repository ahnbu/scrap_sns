from utils.post_meta import build_post_meta, canonicalize_url


def _make_post():
    return {
        "sequence_id": 7,
        "platform_id": "ABC123",
        "sns_platform": "threads",
        "code": "ABC123",
        "username": "alice",
        "display_name": "Alice",
        "url": "https://www.threads.net/@alice/post/ABC123",
        "created_at": "2026-04-19T09:00:00",
        "date": "2026-04-19",
        "source": "consumer_detail",
        "full_text": "A" * 240,
        "media": ["https://cdn.example.com/image.jpg"],
        "local_images": [],
        "is_detail_collected": True,
        "is_merged_thread": False,
    }


def test_canonicalize_url_converts_threads_net_to_threads_com():
    post = _make_post()

    assert canonicalize_url(post) == "https://www.threads.com/@alice/post/ABC123"


def test_build_post_meta_adds_preview_thumbnail_and_counts():
    meta = build_post_meta(_make_post())

    assert meta["canonical_url"] == "https://www.threads.com/@alice/post/ABC123"
    assert meta["full_text_preview"] == "A" * 200
    assert meta["full_text_length"] == 240
    assert meta["media_count"] == 1
    assert meta["local_images_count"] == 0
    assert (
        meta["thumbnail"]
        == "https://wsrv.nl/?url=https%3A%2F%2Fcdn.example.com%2Fimage.jpg&output=webp"
    )


def test_build_thumbnail_returns_existing_wsrv_proxy_unchanged():
    post = _make_post()
    post["media"] = [
        "https://wsrv.nl/?url=https%3A%2F%2Fcdn.example.com%2Fimage.jpg&output=webp"
    ]

    assert (
        build_post_meta(post)["thumbnail"]
        == "https://wsrv.nl/?url=https%3A%2F%2Fcdn.example.com%2Fimage.jpg&output=webp"
    )


def test_build_thumbnail_prefers_local_images_over_media():
    post = _make_post()
    post["local_images"] = ["/tmp/local-image.jpg"]

    assert build_post_meta(post)["thumbnail"] == "/tmp/local-image.jpg"


def test_build_thumbnail_passes_through_licdn_media_url():
    post = _make_post()
    post["media"] = ["https://media.licdn.com/dms/image/test.jpg"]

    assert build_post_meta(post)["thumbnail"] == "https://media.licdn.com/dms/image/test.jpg"


def test_canonicalize_url_normalizes_legacy_threads_t_path_from_raw_url():
    post = _make_post()
    post.pop("username")
    post["url"] = "https://www.threads.net/t/ABC123"

    assert canonicalize_url(post) == "https://www.threads.com/t/ABC123"


def test_canonicalize_url_normalizes_http_threads_host():
    post = _make_post()
    post["url"] = "http://www.threads.net/@alice/post/ABC123"

    assert canonicalize_url(post) == "https://www.threads.com/@alice/post/ABC123"
