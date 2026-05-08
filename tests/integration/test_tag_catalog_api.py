import json


def test_get_tag_catalog_returns_empty_object_when_file_missing(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().get("/api/get-tag-catalog")

    assert response.status_code == 200
    assert response.get_json() == {}


def test_save_and_get_tag_catalog_roundtrip(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))
    client = app.test_client()
    payload = {
        "리서치": {
            "primary": False,
            "aliases": ["심층리서치", "research"],
        }
    }

    save_response = client.post("/api/save-tag-catalog", json=payload)

    assert save_response.status_code == 200
    assert save_response.get_json()["status"] == "success"

    catalog_path = tmp_path / "sns_tag_catalog.json"
    stored = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert stored == payload

    get_response = client.get("/api/get-tag-catalog")
    assert get_response.status_code == 200
    assert get_response.get_json() == payload


def test_save_tag_catalog_rejects_array_payload(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().post("/api/save-tag-catalog", json=[])

    assert response.status_code == 400


def test_save_tag_catalog_accepts_empty_object(app, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().post("/api/save-tag-catalog", json={})

    assert response.status_code == 200
    assert json.loads((tmp_path / "sns_tag_catalog.json").read_text(encoding="utf-8")) == {}
