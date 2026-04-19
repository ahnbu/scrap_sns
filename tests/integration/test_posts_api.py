import gzip
import json


def _write_total_payload(tmp_path):
    payload = {
        "metadata": {
            "total_count": 2,
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
            },
            {
                "sequence_id": 2,
                "platform_id": "XYZ999",
                "sns_platform": "twitter",
                "code": "XYZ999",
                "username": "bob",
                "display_name": "Bob",
                "url": "https://x.com/bob/status/999",
                "created_at": "2026-04-20T09:00:00",
                "date": "2026-04-20",
                "source": "consumer_detail",
                "full_text": "world",
                "media": [],
                "local_images": [],
                "is_detail_collected": True,
                "is_merged_thread": False,
            },
        ],
    }
    target = tmp_path / "total_full_20260419.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def test_posts_api_returns_meta_only(app, tmp_path, monkeypatch):
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
    response = client.get("/api/posts", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"

    payload = json.loads(gzip.decompress(response.data))
    assert [post["sequence_id"] for post in payload["posts"]] == [2, 1]
    post = payload["posts"][1]

    assert post["canonical_url"] == "https://www.threads.com/@alice/post/ABC123"
    assert "full_text" not in post
    assert "media" not in post


def test_posts_api_returns_304_when_if_none_match_matches(app, tmp_path, monkeypatch):
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
    first_response = client.get("/api/posts")
    etag = first_response.headers["ETag"]

    response = client.get("/api/posts", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.data == b""


def test_posts_api_applies_sequence_sort(app, tmp_path, monkeypatch):
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
    response = client.get("/api/posts?sort=sequence")

    assert response.status_code == 200
    payload = response.get_json()
    assert [post["sequence_id"] for post in payload["posts"]] == [2, 1]


def test_posts_api_returns_304_for_weak_if_none_match(app, tmp_path, monkeypatch):
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

    response = client.get("/api/posts", headers={"If-None-Match": f"W/{etag}"})

    assert response.status_code == 304
    assert response.data == b""


def test_posts_api_sets_vary_header_without_gzip(app, tmp_path, monkeypatch):
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
    response = client.get("/api/posts")

    assert response.status_code == 200
    assert response.headers["Vary"] == "Accept-Encoding"


def test_get_tags_is_not_304_from_posts_etag(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))
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

    response = client.get("/api/get-tags", headers={"If-None-Match": etag})

    assert response.status_code == 200
    assert response.get_json() == {}
