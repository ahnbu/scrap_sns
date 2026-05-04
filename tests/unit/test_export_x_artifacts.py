import json
import importlib
from pathlib import Path

import pytest

export_mod = importlib.import_module("scripts.auth_runtime.export_x_artifacts")
from scripts.auth_runtime.export_x_artifacts import (
    _refresh_link,
    extract_token_pair,
    flat_cookie_link_name,
    flat_storage_link_name,
)


class FakeXContext:
    def __init__(self, cookies):
        self._cookies = cookies
        self.storage_state_paths = []
        self.cookies_urls = []

    def storage_state(self, path):
        self.storage_state_paths.append(path)
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"cookies": [], "origins": []}, file)

    def cookies(self, url):
        self.cookies_urls.append(url)
        return self._cookies


def test_extract_token_pair_returns_required_values():
    cookies = [
        {"name": "auth_token", "value": "aaa"},
        {"name": "ct0", "value": "bbb"},
        {"name": "lang", "value": "ko"},
    ]

    assert extract_token_pair(cookies) == {"auth_token": "aaa", "ct0": "bbb"}


def test_extract_token_pair_returns_none_when_ct0_missing():
    cookies = [{"name": "auth_token", "value": "aaa"}]

    assert extract_token_pair(cookies) is None


def test_flat_link_names_are_stable():
    assert flat_cookie_link_name() == "x_cookies_current.json"
    assert flat_storage_link_name() == "x_storage_state_current.json"


def test_refresh_link_replaces_existing_symlink(tmp_path):
    target_a = tmp_path / "target_a.json"
    target_b = tmp_path / "target_b.json"
    link_path = tmp_path / "current.json"
    target_a.write_text("a", encoding="utf-8")
    target_b.write_text("b", encoding="utf-8")
    link_path.symlink_to(target_a)

    _refresh_link(link_path, target_b)

    assert link_path.is_symlink()
    assert Path(link_path.resolve()) == target_b.resolve()


def test_export_x_artifacts_from_context_writes_current_cookie_links(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_HOME", str(tmp_path))

    context = FakeXContext(
        [
            {"name": "auth_token", "value": "token"},
            {"name": "ct0", "value": "ct0"},
        ]
    )

    cookie_path, storage_path = export_mod.export_x_artifacts_from_context(
        context,
        stamp="20260505_1200",
    )

    assert cookie_path.name == "cookies_20260505_1200.json"
    assert storage_path.name == "storage_state.json"
    assert context.cookies_urls == ["https://x.com"]
    assert (tmp_path / "x" / "cookies.json").resolve().name == "cookies_20260505_1200.json"
    assert (tmp_path / "x_cookies_current.json").is_symlink()


def test_export_x_artifacts_from_context_rejects_missing_tokens_without_relink(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("AUTH_HOME", str(tmp_path))
    x_dir = tmp_path / "x"
    x_dir.mkdir(parents=True)
    old_cookie = x_dir / "cookies_20260504_1800.json"
    old_cookie.write_text(
        json.dumps(
            [
                {"name": "auth_token", "value": "old"},
                {"name": "ct0", "value": "old-ct0"},
            ]
        ),
        encoding="utf-8",
    )
    (x_dir / "cookies.json").symlink_to(old_cookie.name)

    context = FakeXContext([{"name": "auth_token", "value": "new"}])

    with pytest.raises(RuntimeError, match="auth_token/ct0 missing"):
        export_mod.export_x_artifacts_from_context(context, stamp="20260505_1200")

    assert (x_dir / "cookies.json").resolve().name == "cookies_20260504_1800.json"
