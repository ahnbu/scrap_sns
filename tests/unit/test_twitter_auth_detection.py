from twitter_scrap import should_require_x_auth


def test_should_not_require_auth_when_bookmark_response_parsed_posts():
    assert (
        should_require_x_auth(
            current_url="https://x.com/i/bookmarks",
            has_tweet_article=False,
            bookmark_response_seen=True,
            parsed_bookmark_count=3,
        )
        is False
    )


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


def test_should_require_auth_when_no_bookmark_signal_exists():
    assert (
        should_require_x_auth(
            current_url="https://x.com/i/bookmarks",
            has_tweet_article=False,
            bookmark_response_seen=False,
            parsed_bookmark_count=0,
        )
        is True
    )
