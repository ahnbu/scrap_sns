"""뷰어 상태 파일 경로 바꿔 끼우기 — 검증 전용 서버가 운영 태그·카탈로그·사용자메타를 쓰지 않는다.

검증 페이지는 로드 때 자동 태그를 적용해 태그 파일 전체를 저장한다. 운영 파일을 같이 쓰면
표본 볼트 키가 운영 태그에 섞인다(2026-09-11 실측 4건). 계획: _docs/20260911_02 (W2 T2-c)
"""
import json
import os


def test_state_files_follow_env_overrides(client, monkeypatch, tmp_path):
    alt = tmp_path / "alt"
    alt.mkdir()
    paths = {
        "SNS_TAGS_PATH": alt / "tags.json",
        "SNS_TAG_CATALOG_PATH": alt / "catalog.json",
        "SNS_USER_METADATA_PATH": alt / "meta.json",
    }
    for name, path in paths.items():
        monkeypatch.setenv(name, str(path))

    assert client.post("/api/save-tags", json={"https://a": ["x"]}).status_code == 200
    assert client.post("/api/save-tag-catalog", json={"x": {"aliases": [], "primary": False}}).status_code == 200
    assert client.post("/api/save-user-metadata", json={"threads:1": {"favorite": True}}).status_code == 200

    def read(name):
        return json.loads(paths[name].read_text(encoding="utf-8"))

    assert read("SNS_TAGS_PATH") == {"https://a": ["x"]}
    assert read("SNS_TAG_CATALOG_PATH") == {"x": {"aliases": [], "primary": False}}
    assert read("SNS_USER_METADATA_PATH") == {"threads:1": {"favorite": True}}
    assert client.get("/api/get-tags").get_json() == {"https://a": ["x"]}
    assert client.get("/api/get-tag-catalog").get_json() == {"x": {"aliases": [], "primary": False}}
    assert client.get("/api/get-user-metadata").get_json() == {"threads:1": {"favorite": True}}

    # 기본 자리(conftest 가 WEB_VIEWER_DIR 로 바꿔 끼운 tmp_path)에는 아무것도 생기지 않는다.
    for name in ("sns_tags.json", "sns_tag_catalog.json", "sns_user_metadata.json"):
        assert not (tmp_path / name).exists()


def test_default_paths_stay_in_web_viewer_dir(monkeypatch):
    import scrap_sns_server as server

    for name in ("SNS_TAGS_PATH", "SNS_TAG_CATALOG_PATH", "SNS_USER_METADATA_PATH"):
        monkeypatch.delenv(name, raising=False)
    assert server._get_tags_path() == os.path.join(server.WEB_VIEWER_DIR, "sns_tags.json")
    assert server._get_tag_catalog_path() == os.path.join(server.WEB_VIEWER_DIR, "sns_tag_catalog.json")
    assert server._get_user_metadata_path() == os.path.join(server.WEB_VIEWER_DIR, "sns_user_metadata.json")
