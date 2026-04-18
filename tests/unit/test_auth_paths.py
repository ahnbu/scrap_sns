import importlib
import json
import sys
from pathlib import Path


def _reload_auth_paths():
    sys.modules.pop("utils.auth_paths", None)
    import utils.auth_paths as auth_paths

    return importlib.reload(auth_paths)


def _write_cookie_file(path: Path, auth_token: str, ct0: str) -> None:
    path.write_text(
        json.dumps(
            [
                {"name": "auth_token", "value": auth_token},
                {"name": "ct0", "value": ct0},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_x_cookies_latest_prefers_nested_cookies_link(tmp_path, monkeypatch):
    x_dir = tmp_path / "x"
    x_dir.mkdir(parents=True)
    dated = x_dir / "cookies_20260418_1810.json"
    _write_cookie_file(dated, "new-token", "new-ct0")
    (x_dir / "cookies.json").symlink_to(dated.name)
    monkeypatch.setenv("AUTH_HOME", str(tmp_path))
    auth_paths = _reload_auth_paths()

    assert auth_paths.x_cookies_latest() == x_dir / "cookies.json"


def test_validate_x_cookie_target_rejects_stale_link(tmp_path, monkeypatch):
    x_dir = tmp_path / "x"
    x_dir.mkdir(parents=True)
    old_dated = x_dir / "cookies_20260418_1800.json"
    new_dated = x_dir / "cookies_20260418_1810.json"
    _write_cookie_file(old_dated, "old-token", "old-ct0")
    _write_cookie_file(new_dated, "new-token", "new-ct0")
    (x_dir / "cookies.json").symlink_to(old_dated.name)
    monkeypatch.setenv("AUTH_HOME", str(tmp_path))
    auth_paths = _reload_auth_paths()

    assert auth_paths.validate_x_cookie_target(new_dated.name) is False


def test_flat_compatibility_paths_resolve_under_auth_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_HOME", str(tmp_path))
    auth_paths = _reload_auth_paths()

    assert auth_paths.x_flat_cookie() == tmp_path / "x_cookies_current.json"
    assert auth_paths.x_flat_storage() == tmp_path / "x_storage_state_current.json"
