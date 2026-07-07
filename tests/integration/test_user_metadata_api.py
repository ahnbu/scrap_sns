import json


def test_get_user_metadata_returns_empty_object_when_file_missing(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().get("/api/get-user-metadata")

    assert response.status_code == 200
    assert response.get_json() == {}


def test_save_and_get_user_metadata_roundtrip(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))
    client = app.test_client()
    payload = {
        "threads:ABC123": {
            "canonical_url": "https://www.threads.com/@alice/post/ABC123",
            "favorite": True,
            "hidden": False,
            "note": "강의 사례",
            "updated_at": "2026-07-07T11:06:00+09:00",
        }
    }

    save_response = client.post("/api/save-user-metadata", json=payload)
    assert save_response.status_code == 200
    assert save_response.get_json()["status"] == "success"

    stored = json.loads((tmp_path / "sns_user_metadata.json").read_text(encoding="utf-8"))
    assert stored == payload

    get_response = client.get("/api/get-user-metadata")
    assert get_response.status_code == 200
    assert get_response.get_json() == payload


def test_save_user_metadata_rejects_array_payload(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().post("/api/save-user-metadata", json=[])

    assert response.status_code == 400
