from utils.post_schema import normalize_post, validate_post


def test_normalize_post_converts_legacy_threads_fields():
    legacy = {
        "sns_platform": "threads",
        "code": "DUn02Eukm2o",
        "user": "winter_kyul",
        "timestamp": "2026-02-12 12:34:56",
        "full_text": "test",
        "is_merged_thread": True,
    }

    normalized = normalize_post(legacy)

    assert normalized["platform_id"] == "DUn02Eukm2o"
    assert normalized["username"] == "winter_kyul"
    assert normalized["display_name"] == "winter_kyul"
    assert normalized["created_at"] == "2026-02-12 12:34:56"
    assert normalized["url"] == "https://www.threads.net/@winter_kyul/post/DUn02Eukm2o"
    assert validate_post(normalized) == []
    assert "user" not in normalized
    assert "timestamp" not in normalized


def test_validate_post_reports_missing_required_fields():
    missing = validate_post(
        {
            "sns_platform": "threads",
            "full_text": "body only",
        }
    )

    assert missing == ["username", "url", "created_at"]
