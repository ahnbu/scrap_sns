import json


def test_returns_empty_items_when_file_missing(app, tmp_path, monkeypatch):
    """수집기를 한 번도 안 돌린 상태에서도 뷰어가 살아야 한다."""
    import scrap_sns_server as server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))

    response = app.test_client().get("/api/get-external-summaries")

    assert response.status_code == 200
    assert response.get_json() == {"items": {}}


def test_returns_mapping_as_is(app, tmp_path, monkeypatch):
    import scrap_sns_server as server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))
    payload = {
        "generated_at_kst": "2026-08-28 18:21:00 KST",
        "sources": {
            "lilys": {"collected_at_kst": "2026-08-28 18:18:49 KST", "count": 156},
            "livewiki": {"collected_at_kst": "2026-08-28 18:18:56 KST", "count": 742},
        },
        "total_video_count": 2,
        "items": {
            "fPgZhHMJc_I": {"lilys": "https://lilys.ai/digest/11132480", "livewiki": None},
            "bA2Rg0JE7xA": {
                "lilys": None,
                "livewiki": "https://livewiki.com/ko/content/8900bc8e-053d-4214-9a42-051fb59f5a60",
            },
        },
    }
    (tmp_path / "sns_external_summaries.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    response = app.test_client().get("/api/get-external-summaries")

    assert response.status_code == 200
    assert response.get_json() == payload


def test_malformed_file_degrades_to_empty_items(app, tmp_path, monkeypatch):
    """형태가 깨져도 500 대신 빈 매핑으로 떨어뜨린다. 뷰어가 죽으면 안 된다."""
    import scrap_sns_server as server

    monkeypatch.setattr(server, "WEB_VIEWER_DIR", str(tmp_path))
    (tmp_path / "sns_external_summaries.json").write_text(
        json.dumps({"items": ["not", "a", "dict"]}), encoding="utf-8"
    )

    response = app.test_client().get("/api/get-external-summaries")

    assert response.status_code == 200
    assert response.get_json() == {"items": {}}


def test_no_save_endpoint_exists(app):
    """이 매핑은 사용자 상태가 아니라 스크립트 산출물이다. 쓰기 경로를 열지 않는다."""
    response = app.test_client().post("/api/save-external-summaries", json={})

    assert response.status_code in (404, 405)
