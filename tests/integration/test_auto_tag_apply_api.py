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


def test_auto_tag_apply_uses_canonical_url_key(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    response = client.post(
        "/api/auto-tag/apply",
        json={
            "rules": [
                {
                    "keyword": "hello",
                    "tag": "hello-tag",
                    "match_field": "all",
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["url_to_auto_tags"] == {
        "https://www.threads.com/@alice/post/ABC123": ["hello-tag"],
        "https://x.com/bob/status/999": ["hello-tag"],
    }


def test_auto_tag_apply_returns_gzip_and_vary_for_large_json(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    rules = [
        {
            "keyword": "hello",
            "tag": f"hello-tag-{index:02d}",
            "match_field": "all",
        }
        for index in range(1, 16)
    ]
    rules.extend(
        [
            {
                "keyword": "alice",
                "tag": "alice-tag",
                "match_field": "all",
            },
            {
                "keyword": "bob",
                "tag": "bob-tag",
                "match_field": "all",
            },
        ]
    )
    response = client.post(
        "/api/auto-tag/apply",
        json={"rules": rules},
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["Vary"] == "Accept-Encoding"

    payload = json.loads(gzip.decompress(response.data))
    assert payload["matched_post_count"] == 2


def test_auto_tag_apply_merges_vary_with_origin_on_gzip(app, tmp_path, monkeypatch):
    import server

    _write_total_payload(tmp_path)
    _reset_posts_cache(server, monkeypatch, tmp_path)

    client = app.test_client()
    rules = [
        {
            "keyword": "hello",
            "tag": f"hello-tag-{index:02d}",
            "match_field": "all",
        }
        for index in range(1, 16)
    ]
    response = client.post(
        "/api/auto-tag/apply",
        json={"rules": rules},
        headers={
            "Accept-Encoding": "gzip",
            "Origin": "https://example.com",
        },
    )

    assert response.status_code == 200
    vary_values = {value.strip() for value in response.headers["Vary"].split(",")}
    assert vary_values == {"Origin", "Accept-Encoding"}
