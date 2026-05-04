from scripts.auth_runtime.verify_x_auth import (
    build_probe_report,
    classify_producer_probe,
    is_transient_browser_launch_error,
    x_probe_launch_configs,
)


def test_classify_producer_probe_accepts_bookmark_network_response():
    assert classify_producer_probe(
        current_url="https://x.com/i/bookmarks",
        bookmark_response_seen=True,
        parsed_bookmark_count=1,
        article_count=0,
    ) == (True, "bookmark_response")


def test_classify_producer_probe_rejects_login_url():
    assert classify_producer_probe(
        current_url="https://x.com/i/flow/login",
        bookmark_response_seen=False,
        parsed_bookmark_count=0,
        article_count=0,
    ) == (False, "login_required")


def test_build_probe_report_is_machine_readable():
    assert build_probe_report(producer_ok=True, consumer_ok=True) == {
        "producer_ok": True,
        "consumer_ok": True,
    }


def test_is_transient_browser_launch_error_detects_chrome_window_race():
    assert is_transient_browser_launch_error(
        Exception("Browser.getWindowForTarget: Browser window not found")
    )
    assert is_transient_browser_launch_error(
        Exception("BrowserType.launch_persistent_context: Target page, context or browser has been closed")
    )
    assert not is_transient_browser_launch_error(Exception("login_required"))


def test_x_probe_launch_configs_try_chrome_then_bundled_chromium():
    configs = x_probe_launch_configs()

    assert configs[0]["channel"] == "chrome"
    assert "channel" not in configs[1]
    assert all(config["headless"] is True for config in configs)
