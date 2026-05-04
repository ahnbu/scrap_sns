import pytest

from scripts.auth_runtime.verify_x_auth import probe_consumer, probe_producer


@pytest.mark.smoke
def test_twitter_session_validity():
    """Twitter(X) Persistent Context의 유효성을 검사합니다."""
    try:
        producer_ok, reason = probe_producer()
        consumer_ok = probe_consumer()
        assert producer_ok, f"Twitter(X) producer 세션이 유효하지 않습니다: {reason}"
        assert consumer_ok, "Twitter(X) consumer 쿠키 토큰을 찾지 못했습니다."
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chrome executable not found. Skip Twitter smoke test.")
        raise
