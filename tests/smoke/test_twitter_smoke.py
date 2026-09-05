import pytest
from playwright.sync_api import Playwright

from scripts.auth_runtime.verify_x_auth import probe_consumer, probe_producer


@pytest.mark.smoke
def test_twitter_session_validity(playwright: Playwright):
    """Twitter(X) Persistent Context의 유효성을 검사합니다.

    fixture 가 만든 playwright 를 넘긴다. 안 넘기면 probe_producer 가 자기
    sync_playwright() 를 여는데, 같은 스모크 스위트의 LinkedIn·Threads 테스트가
    session 스코프 fixture 로 이미 루프를 잡고 있어 중첩으로 끊긴다
    (단독 실행은 통과하고 함께 돌리면 실패해 순서 의존으로 보였다).
    """
    try:
        producer_ok, reason = probe_producer(playwright)
        consumer_ok = probe_consumer()
        assert producer_ok, f"Twitter(X) producer 세션이 유효하지 않습니다: {reason}"
        assert consumer_ok, "Twitter(X) consumer 쿠키 토큰을 찾지 못했습니다."
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chrome executable not found. Skip Twitter smoke test.")
        raise
