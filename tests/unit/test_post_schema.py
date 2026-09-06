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
    assert normalized["url"] == "https://www.threads.com/@winter_kyul/post/DUn02Eukm2o"
    assert validate_post(normalized) == []
    assert "user" not in normalized
    assert "timestamp" not in normalized


def test_validate_post_reports_missing_required_fields():
    missing = validate_post(
        {
            "sns_platform": "threads",
        }
    )

    assert missing == ["username", "url", "created_at", "full_text_or_media"]


def test_validate_post_allows_image_only_posts():
    missing = validate_post(
        {
            "sns_platform": "threads",
            "username": "media_only_user",
            "url": "https://www.threads.com/@media_only_user/post/ABC123",
            "created_at": "2026-01-03 08:43:04",
            "media": ["https://example.com/image.jpg"],
            "full_text": "",
        }
    )

    assert missing == []


def test_normalize_post_defaults_is_saved_to_true():
    """이 필드가 없던 시절의 레코드는 전부 내 북마크였다.

    False 로 두면 뷰어의 `보임 = is_saved OR 켜진 벤치마킹 계정` 이 거짓이 되어
    기존 저장글이 통째로 화면에서 사라진다. 계획: _docs/20260906_01 (D14)
    """
    normalized = normalize_post(
        {
            "sns_platform": "youtube",
            "username": "someone",
            "url": "https://www.youtube.com/watch?v=abc",
            "created_at": "2026-09-06 10:00:00",
            "full_text": "hello",
        }
    )

    assert normalized["is_saved"] is True
    assert normalized["benchmark_accounts"] == []
    assert normalized["channel_id"] == ""


def test_normalize_post_keeps_explicit_benchmark_fields():
    normalized = normalize_post(
        {
            "sns_platform": "youtube",
            "username": "someone",
            "url": "https://www.youtube.com/watch?v=abc",
            "created_at": "2026-09-06 10:00:00",
            "full_text": "hello",
            "is_saved": False,
            "benchmark_accounts": ["builderjosh"],
            "channel_id": "UCxj3eVTAv9KLdrowXcuCFDQ",
        }
    )

    assert normalized["is_saved"] is False
    assert normalized["benchmark_accounts"] == ["builderjosh"]
    assert normalized["channel_id"] == "UCxj3eVTAv9KLdrowXcuCFDQ"
