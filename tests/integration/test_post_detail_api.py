import json


def _write_total_payload(tmp_path):
    payload = {
        "metadata": {
            "total_count": 1,
            "updated_at": "2026-04-19T09:00:00",
        },
        "posts": [
            {
                "sequence_id": 1,
                "platform_id": "ABC123",
                "sns_platform": "threads",
                "code": "ABC123",
                "username": "alice",
                "display_name": "Alice",
                "url": "https://www.threads.net/@alice/post/ABC123",
                "created_at": "2026-04-19T09:00:00",
                "date": "2026-04-19",
                "source": "consumer_detail",
                "full_text": "hello",
                "media": ["https://cdn.example.com/image.jpg"],
                "local_images": [],
                "is_detail_collected": True,
                "is_merged_thread": False,
            }
        ],
    }
    target = tmp_path / "total_full_20260419.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def test_post_detail_api_returns_full_post(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_POSTS_CACHE",
        {
            "path": None,
            "mtime": None,
            "size": None,
            "posts_full": None,
            "posts_meta": None,
            "etag": None,
        },
        raising=False,
    )

    client = app.test_client()
    response = client.get("/api/post/1")

    assert response.status_code == 200

    payload = response.get_json()
    assert payload["full_text"] == "hello"
    assert payload["media"] == ["https://cdn.example.com/image.jpg"]
    assert payload["canonical_url"] == "https://www.threads.com/@alice/post/ABC123"
    assert "_searchable" not in payload
    assert response.headers["Vary"] == "Accept-Encoding"


def test_post_detail_missing_post_ignores_if_none_match(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_POSTS_CACHE",
        {
            "path": None,
            "mtime": None,
            "size": None,
            "posts_full": None,
            "posts_meta": None,
            "etag": None,
        },
        raising=False,
    )

    client = app.test_client()
    etag = client.get("/api/posts").headers["ETag"]

    response = client.get("/api/post/999", headers={"If-None-Match": etag})

    assert response.status_code == 404
    assert response.get_json() == {"error": "Post not found"}


def test_post_detail_does_not_reuse_posts_etag(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_POSTS_CACHE",
        {
            "path": None,
            "mtime": None,
            "size": None,
            "posts_full": None,
            "posts_meta": None,
            "etag": None,
        },
        raising=False,
    )

    client = app.test_client()
    posts_response = client.get("/api/posts")
    posts_etag = posts_response.headers["ETag"]

    response = client.get("/api/post/1", headers={"If-None-Match": posts_etag})

    assert response.status_code == 200
    assert response.headers["ETag"] != posts_etag


def test_post_detail_returns_304_when_own_etag_matches(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_POSTS_CACHE",
        {
            "path": None,
            "mtime": None,
            "size": None,
            "posts_full": None,
            "posts_meta": None,
            "etag": None,
        },
        raising=False,
    )

    client = app.test_client()
    detail_response = client.get("/api/post/1")
    detail_etag = detail_response.headers["ETag"]

    response = client.get("/api/post/1", headers={"If-None-Match": detail_etag})

    assert response.status_code == 304
    assert response.data == b""
