from migrate_threads_domain import (
    canonicalize_legacy_key,
    create_backup,
    migrate_url_key_dict,
    rewrite_threads_urls_in_value,
    scan_file_rewrites,
)


def test_canonicalize_legacy_key_prefers_latest_threads_post_url():
    canonical_by_code = {
        "ABC123": "https://www.threads.com/@ally/post/ABC123",
    }

    assert (
        canonicalize_legacy_key(
            "https://www.threads.net/@alice/post/ABC123",
            canonical_by_code,
        )
        == "https://www.threads.com/@ally/post/ABC123"
    )
    assert (
        canonicalize_legacy_key(
            "https://www.threads.net/t/ABC123",
            canonical_by_code,
        )
        == "https://www.threads.com/@ally/post/ABC123"
    )


def test_migrate_url_key_dict_merges_legacy_entries_into_canonical_key():
    canonical_by_code = {
        "ABC123": "https://www.threads.com/@ally/post/ABC123",
    }
    data = {
        "https://www.threads.net/@alice/post/ABC123": ["legacy-net"],
        "https://www.threads.net/t/ABC123": ["legacy-t"],
        "https://www.threads.com/@ally/post/ABC123": ["canonical"],
        "https://example.com/keep": ["other"],
    }

    migrated = migrate_url_key_dict(data, canonical_by_code)

    assert migrated == {
        "https://www.threads.com/@ally/post/ABC123": [
            "canonical",
            "legacy-net",
            "legacy-t",
        ],
        "https://example.com/keep": ["other"],
    }


def test_rewrite_threads_urls_in_value_normalizes_nested_net_urls():
    value = {
        "url": "https://www.threads.net/@ally/post/ABC123",
        "nested": [
            "https://www.threads.net/t/ABC123",
            {"source_url": "https://www.threads.net/@ally/post/ABC123"},
        ],
    }

    rewritten = rewrite_threads_urls_in_value(value)

    assert rewritten == {
        "url": "https://www.threads.com/@ally/post/ABC123",
        "nested": [
            "https://www.threads.com/t/ABC123",
            {"source_url": "https://www.threads.com/@ally/post/ABC123"},
        ],
    }


def test_scan_file_rewrites_skips_invalid_json_files(tmp_path):
    invalid_path = tmp_path / "broken.json"
    invalid_path.write_text("", encoding="utf-8")

    valid_path = tmp_path / "valid.json"
    valid_path.write_text(
        '{"url": "https://www.threads.net/@ally/post/ABC123"}',
        encoding="utf-8",
    )

    assert scan_file_rewrites([invalid_path, valid_path]) == 1


def test_create_backup_does_not_match_total_full_json_pattern(tmp_path):
    source_path = tmp_path / "total_full_20260417.json"
    source_path.write_text("{}", encoding="utf-8")

    backup_path = create_backup(source_path)

    assert backup_path.name.startswith("total_full_20260417")
    assert not backup_path.name.endswith(".json")
