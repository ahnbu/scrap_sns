import json
import subprocess
import sys
from pathlib import Path

from utils.twitter_cli_adapter import (
    TwitterCliDetail,
    build_twitter_cli_env,
    extract_tweet_id,
    fetch_tweet_detail,
    load_twitter_tokens,
    parse_twitter_cli_payload,
    select_focal_tweet,
)


def _load_fixture(name):
    fixture_path = Path("tests/fixtures/twitter_cli") / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _write_cookie_file(path, auth_token, ct0):
    path.write_text(
        json.dumps(
            [
                {"name": "auth_token", "value": auth_token},
                {"name": "ct0", "value": ct0},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_load_twitter_tokens_reads_latest_cookie_file(tmp_path):
    older = tmp_path / "x_cookies_20260417_090000.json"
    newer = tmp_path / "x_cookies_20260418_090000.json"
    _write_cookie_file(older, auth_token="old-token", ct0="old-ct0")
    _write_cookie_file(newer, auth_token="new-token", ct0="new-ct0")

    assert load_twitter_tokens(auth_dir=tmp_path) == {
        "auth_token": "new-token",
        "ct0": "new-ct0",
    }


def test_load_twitter_tokens_returns_none_when_latest_cookie_missing_required_token(tmp_path):
    older = tmp_path / "x_cookies_20260417_090000.json"
    newer = tmp_path / "x_cookies_20260418_090000.json"
    _write_cookie_file(older, auth_token="old-token", ct0="old-ct0")
    newer.write_text(
        json.dumps(
            [{"name": "auth_token", "value": "new-token"}],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    assert load_twitter_tokens(auth_dir=tmp_path) is None


def test_load_twitter_tokens_prefers_nested_current_link_over_legacy_flat_files(tmp_path):
    legacy = tmp_path / "x_cookies_20260417_090000.json"
    _write_cookie_file(legacy, auth_token="old-token", ct0="old-ct0")

    x_dir = tmp_path / "x"
    x_dir.mkdir()
    actual = x_dir / "cookies_20260418_090000.json"
    _write_cookie_file(actual, auth_token="new-token", ct0="new-ct0")
    (x_dir / "cookies.json").symlink_to(actual.name)

    assert load_twitter_tokens(auth_dir=tmp_path) == {
        "auth_token": "new-token",
        "ct0": "new-ct0",
    }


def test_build_twitter_cli_env_injects_expected_keys():
    env = build_twitter_cli_env({"PATH": "ok"}, {"auth_token": "aaa", "ct0": "bbb"})

    assert env["PATH"] == "ok"
    assert env["TWITTER_AUTH_TOKEN"] == "aaa"
    assert env["TWITTER_CT0"] == "bbb"


def test_parse_twitter_cli_payload_wraps_photo_urls():
    payload = _load_fixture("toppingtest.json")

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text=payload["data"][0]["text"],
        media=[
            "https://wsrv.nl/?url=https://pbs.twimg.com/media/HEsTPr6akAAiitk.jpg",
            "https://wsrv.nl/?url=https://pbs.twimg.com/media/HEsTa9FbUAA_sck.jpg",
        ],
        real_user="toppingtest",
    )


def test_parse_twitter_cli_payload_uses_notebooklm_fixture():
    payload = _load_fixture("notebooklm.json")

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text=payload["data"][0]["text"],
        media=[],
        real_user="NotebookLM",
    )


def test_parse_twitter_cli_payload_keeps_only_focal_tweet_and_raw_video_url():
    payload = _load_fixture("aakashgupta.json")

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text=payload["data"][0]["text"],
        media=[
            "https://video.twimg.com/amplify_video/2038710244122251264/vid/avc1/1280x720/ODmFcZfpQj1AO5g8.mp4?tag=21",
        ],
        real_user="aakashgupta",
    )
    assert "@carlvellotti" not in detail.full_text


def test_parse_twitter_cli_payload_uses_first_item_as_focal_tweet():
    payload = {
        "ok": True,
        "data": [
            {
                "text": "first tweet",
                "author": {"screenName": "first_user"},
                "media": [],
            },
            {
                "text": "second tweet",
                "author": {"screenName": "second_user"},
                "media": [
                    {"type": "photo", "url": "https://pbs.twimg.com/media/should-not-be-used.jpg"}
                ],
            },
        ],
    }

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user")

    assert detail == TwitterCliDetail(
        full_text="first tweet",
        media=[],
        real_user="first_user",
    )


def test_fetch_tweet_detail_success_passes_args_env_and_parses_result():
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))

        class Result:
            returncode = 0
            stdout = json.dumps(
                {
                    "ok": True,
                    "data": [
                        {
                            "id": "1",
                            "text": "hello",
                            "author": {"screenName": "target_user"},
                            "media": [
                                {"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"}
                            ],
                        }
                    ],
                }
            )

        return Result()

    env = {"PATH": "ok"}
    detail = fetch_tweet_detail(
        "https://x.com/i/status/1",
        target_user="fallback_user",
        env=env,
        timeout=9,
        runner=runner,
    )

    assert calls == [
        (
            [
                sys.executable,
                "-m",
                "twitter_cli.cli",
                "tweet",
                "https://x.com/i/status/1",
                "--json",
            ],
            {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "env": env,
                "timeout": 9,
            },
        )
    ]
    assert detail == TwitterCliDetail(
        full_text="hello",
        media=["https://wsrv.nl/?url=https://pbs.twimg.com/media/a.jpg"],
        real_user="target_user",
    )


def test_fetch_tweet_detail_returns_none_on_nonzero_exit_or_invalid_json():
    def nonzero_runner(*args, **kwargs):
        class Result:
            returncode = 1
            stdout = "{}"

        return Result()

    def invalid_json_runner(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = "not-json"

        return Result()

    assert (
        fetch_tweet_detail(
            "https://x.com/i/status/1",
            target_user="fallback_user",
            env={},
            runner=nonzero_runner,
        )
        is None
    )
    assert (
        fetch_tweet_detail(
            "https://x.com/i/status/1",
            target_user="fallback_user",
            env={},
            runner=invalid_json_runner,
        )
        is None
    )


def test_fetch_tweet_detail_returns_none_when_runner_times_out():
    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    assert (
        fetch_tweet_detail(
            "https://x.com/i/status/1",
            target_user="fallback_user",
            env={},
            runner=timeout_runner,
        )
        is None
    )


def test_fetch_tweet_detail_returns_none_when_runner_raises_oserror():
    def oserror_runner(*args, **kwargs):
        raise OSError("boom")

    assert (
        fetch_tweet_detail(
            "https://x.com/i/status/1",
            target_user="fallback_user",
            env={},
            runner=oserror_runner,
        )
        is None
    )


def test_extract_tweet_id_reads_url_and_bare_id():
    assert extract_tweet_id("https://x.com/i/status/2024990776531587145") == "2024990776531587145"
    assert extract_tweet_id("https://x.com/kana_option/status/123?s=20") == "123"
    assert extract_tweet_id("2038713289254064321") == "2038713289254064321"
    assert extract_tweet_id("https://x.com/kana_option") is None
    assert extract_tweet_id(None) is None


def test_select_focal_tweet_picks_requested_id_not_first_item():
    items = [
        {"id": "111", "text": "parent tweet"},
        {"id": "222", "text": "requested tweet"},
    ]

    assert select_focal_tweet(items, "222")["text"] == "requested tweet"


def test_select_focal_tweet_returns_none_when_requested_id_absent():
    items = [
        {"id": "111", "text": "someone else's tweet"},
        {"id": "333", "text": "another tweet"},
    ]

    assert select_focal_tweet(items, "222") is None


def test_select_focal_tweet_refuses_payload_without_ids_when_id_expected():
    """A payload with no ids cannot prove which tweet it holds, so it is refused.

    Taking items[0] on faith here is exactly how the pre-ee9fb37 collector wrote
    one account's body onto 36 other records.
    """
    items = [{"text": "id-less payload"}, {"text": "second"}]

    assert select_focal_tweet(items, "222") is None
    assert select_focal_tweet(items, None)["text"] == "id-less payload"


def test_parse_twitter_cli_payload_rejects_mismatched_focal_tweet():
    payload = {
        "ok": True,
        "data": [
            {
                "id": "111",
                "text": "1인개발자 필수 사이트 모음",
                "author": {"screenName": "lucas_flatwhite"},
                "media": [],
            }
        ],
    }

    assert parse_twitter_cli_payload(payload, fallback_user="kana_option", expected_id="222") is None


def test_parse_twitter_cli_payload_uses_expected_id_over_order():
    payload = {
        "ok": True,
        "data": [
            {
                "id": "111",
                "text": "parent tweet",
                "author": {"screenName": "other_user"},
                "media": [],
            },
            {
                "id": "222",
                "text": "requested tweet",
                "author": {"screenName": "target_user"},
                "media": [],
            },
        ],
    }

    detail = parse_twitter_cli_payload(payload, fallback_user="fallback_user", expected_id="222")

    assert detail == TwitterCliDetail(
        full_text="requested tweet",
        media=[],
        real_user="target_user",
    )
