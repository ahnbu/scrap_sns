from twitter_scrap import classify_x_auth_state, is_transient_x_browser_error, should_require_x_auth


def test_classify_x_auth_state_accepts_bookmark_response_parsed_posts():
    assert classify_x_auth_state(
        current_url="https://x.com/i/bookmarks",
        has_tweet_article=False,
        bookmark_response_seen=True,
        parsed_bookmark_count=3,
    ) == (True, "bookmark_response")


def test_classify_x_auth_state_rejects_login_url():
    assert classify_x_auth_state(
        current_url="https://x.com/i/flow/login",
        has_tweet_article=False,
        bookmark_response_seen=False,
        parsed_bookmark_count=0,
    ) == (False, "login_required")


def test_should_not_require_auth_when_bookmarks_url_has_no_signal_yet():
    assert (
        should_require_x_auth(
            current_url="https://x.com/i/bookmarks",
            has_tweet_article=False,
            bookmark_response_seen=False,
            parsed_bookmark_count=0,
        )
        is False
    )


def test_classify_x_auth_state_marks_no_signal_as_indeterminate_not_login():
    assert classify_x_auth_state(
        current_url="https://x.com/i/bookmarks",
        has_tweet_article=False,
        bookmark_response_seen=False,
        parsed_bookmark_count=0,
    ) == (False, "no_bookmark_signal")


def test_should_require_auth_on_login_url():
    assert (
        should_require_x_auth(
            current_url="https://x.com/i/flow/login",
            has_tweet_article=False,
            bookmark_response_seen=False,
            parsed_bookmark_count=0,
        )
        is True
    )


def test_is_transient_x_browser_error_detects_window_race():
    assert is_transient_x_browser_error(
        Exception("Browser.getWindowForTarget: Browser window not found")
    )
    assert is_transient_x_browser_error(
        Exception("Target page, context or browser has been closed")
    )
    assert not is_transient_x_browser_error(Exception("login_required"))
