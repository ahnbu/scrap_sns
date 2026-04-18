import json
import subprocess
import sys
from pathlib import Path

from utils.twitter_cli_adapter import (
    TwitterCliDetail,
    build_twitter_cli_env,
    fetch_tweet_detail,
    load_twitter_tokens,
    parse_twitter_cli_payload,
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
