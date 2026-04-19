import gzip
import json


def _write_total_payload(tmp_path):
    large_text = "hello " * 120
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
                "full_text": large_text,
                "media": ["https://cdn.example.com/image.jpg"],
                "local_images": [],
                "is_detail_collected": True,
                "is_merged_thread": False,
            },
            {
                "sequence_id": 2,
                "platform_id": "XYZ999",
                "sns_platform": "x",
                "code": "XYZ999",
                "username": "bob",
                "display_name": "Bob",
                "url": "https://x.com/bob/status/999",
                "created_at": "2026-04-20T09:00:00",
                "date": "2026-04-20",
                "source": "consumer_detail",
                "full_text": large_text + " extra",
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


def _reset_posts_cache(server, monkeypatch, tmp_path):
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


def test_search_api_requires_q(app):
    client = app.test_client()

    response = client.get("/api/search")

    assert response.status_code == 400
    assert response.get_json() == {"error": "q is required"}


def test_search_api_rejects_blank_q_after_trim(app):
    client = app.test_client()

    response = client.get("/api/search?q=%20%20%20")

    assert response.status_code == 400
    assert response.get_json() == {"error": "q is required"}


def test_search_api_matches_preheated_text(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.get("/api/search?q=HELLO&platform=threads&limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_matched"] == 1
    assert payload["posts"][0]["canonical_url"] == "https://www.threads.com/@alice/post/ABC123"


def test_search_api_platform_all_behaves_like_no_filter(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    all_response = client.get("/api/search?q=hello&platform=all&limit=10")
    no_filter_response = client.get("/api/search?q=hello&limit=10")

    assert all_response.status_code == 200
    assert all_response.get_json()["total_matched"] == 2
    assert all_response.get_json() == no_filter_response.get_json()


def test_search_api_platform_x_and_twitter_are_compatible(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.get("/api/search?q=extra&platform=twitter&limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_matched"] == 1
    assert payload["posts"][0]["sns_platform"] == "x"


def test_search_api_sort_sequence_orders_descending_sequence_id(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.get("/api/search?q=hello&sort=sequence&limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert [post["sequence_id"] for post in payload["posts"]] == [2, 1]


def test_search_api_returns_gzip_vary_and_query_specific_etag(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.get("/api/search?q=hello&limit=10", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["Vary"] == "Accept-Encoding"
    assert "/api/search?q=hello&limit=10" in response.headers["ETag"]

    payload = json.loads(gzip.decompress(response.data))
    assert payload["total_matched"] == 2


def test_search_api_merges_vary_with_origin_on_gzip(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.get(
        "/api/search?q=hello&limit=10",
        headers={
            "Accept-Encoding": "gzip",
            "Origin": "https://example.com",
        },
    )

    assert response.status_code == 200
    vary_values = {value.strip() for value in response.headers["Vary"].split(",")}
    assert vary_values == {"Origin", "Accept-Encoding"}


def test_search_api_returns_304_when_if_none_match_matches(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    first_response = client.get("/api/search?q=hello&limit=10")
    etag = first_response.headers["ETag"]

    response = client.get("/api/search?q=hello&limit=10", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.data == b""
