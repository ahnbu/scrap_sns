def test_root_serves_repo_index_shell(app):
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="masonryGrid"' in body
    assert 'web_viewer/script.js' in body


def test_web_viewer_script_is_public(app):
    client = app.test_client()

    resp = client.get("/web_viewer/script.js")

    assert resp.status_code == 200
    assert "DOMContentLoaded" in resp.get_data(as_text=True)


def test_non_public_repo_file_is_not_served(app):
    client = app.test_client()

    resp = client.get("/README.md")

    assert resp.status_code in (403, 404)
