from utils.media_expiry import (
    get_media_url_expiry,
    has_live_media_url,
    is_media_url_expired,
)

NOW = 1_788_000_000  # 2026-08-31 무렵 KST
LIVE_URL = f"https://media.licdn.com/dms/image/v2/AAA/feedshare-image/0/1/?e={NOW + 86_400}&v=beta"
DEAD_URL = f"https://media.licdn.com/dms/image/v2/BBB/feedshare-image/0/1/?e={NOW - 86_400}&v=beta"
NO_EXPIRY_URL = "https://scontent.cdninstagram.com/v/t51.jpg?oh=abc&oe=DEADBEEF"
NON_NUMERIC_URL = "https://media.licdn.com/dms/image/v2/CCC/0/1/?e=soon&v=beta"


def test_get_media_url_expiry_reads_integer_epoch():
    assert get_media_url_expiry(LIVE_URL) == NOW + 86_400


def test_get_media_url_expiry_returns_none_without_e_param():
    assert get_media_url_expiry(NO_EXPIRY_URL) is None


def test_get_media_url_expiry_returns_none_for_non_numeric():
    assert get_media_url_expiry(NON_NUMERIC_URL) is None


def test_expired_url_is_detected():
    assert is_media_url_expired(DEAD_URL, now_ts=NOW) is True


def test_live_url_is_not_expired():
    assert is_media_url_expired(LIVE_URL, now_ts=NOW) is False


def test_missing_expiry_is_not_treated_as_expired():
    """fbcdn 처럼 `e=` 규약을 안 쓰는 CDN 을 통째로 버리면 안 된다."""
    assert is_media_url_expired(NO_EXPIRY_URL, now_ts=NOW) is False


def test_non_numeric_expiry_is_not_treated_as_expired():
    assert is_media_url_expired(NON_NUMERIC_URL, now_ts=NOW) is False


def test_empty_url_is_not_expired():
    assert is_media_url_expired("", now_ts=NOW) is False
    assert is_media_url_expired(None, now_ts=NOW) is False


def test_has_live_media_url_true_when_any_url_is_live():
    assert has_live_media_url([DEAD_URL, LIVE_URL], now_ts=NOW) is True


def test_has_live_media_url_false_when_all_expired():
    assert has_live_media_url([DEAD_URL, DEAD_URL], now_ts=NOW) is False


def test_has_live_media_url_ignores_video():
    """mp4 는 이미지 다운로드 대상이 아니라 살아있음의 근거가 될 수 없다."""
    assert has_live_media_url(["https://cdn.example.com/clip.mp4"], now_ts=NOW) is False


def test_has_live_media_url_false_for_empty_list():
    assert has_live_media_url([], now_ts=NOW) is False
    assert has_live_media_url(None, now_ts=NOW) is False
