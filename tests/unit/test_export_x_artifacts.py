from pathlib import Path

from scripts.auth_runtime.export_x_artifacts import (
    _refresh_link,
    extract_token_pair,
    flat_cookie_link_name,
    flat_storage_link_name,
)


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
