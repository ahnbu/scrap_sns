from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from utils.auth_paths import read_x_cookie_tokens, x_cookies_latest

WSRV_PREFIX = "https://wsrv.nl/?url="


@dataclass(frozen=True)
class TwitterCliDetail:
    full_text: str
    media: list[str]
    real_user: str


def load_twitter_tokens(auth_dir="auth"):
    cookie_path = x_cookies_latest(Path(auth_dir) if auth_dir is not None else None)
    if not cookie_path:
        return None
    return read_x_cookie_tokens(cookie_path)


def build_twitter_cli_env(base_env, tokens):
    env = dict(base_env)
    env["TWITTER_AUTH_TOKEN"] = tokens["auth_token"]
    env["TWITTER_CT0"] = tokens["ct0"]
    return env


def _normalize_media(media_items):
    normalized = []
    for item in media_items or []:
        url = item.get("url")
        if not url:
            continue
        if item.get("type") == "photo":
            normalized.append(f"{WSRV_PREFIX}{url}")
        else:
            normalized.append(url)
    return normalized


def extract_tweet_id(url):
    """Return the numeric tweet id from a tweet URL or a bare id."""
    text = str(url or "").strip()
    if text.isdigit():
        return text
    match = re.search(r"/status/(\d+)", text)
    return match.group(1) if match else None


def select_focal_tweet(items, expected_id=None):
    """Pick the requested tweet instead of trusting payload order.

    Only falls back to the first item when the caller has no expected id at all.
    Once an id is expected, the match must be explicit: a payload that carries no
    ids, or carries ids that none of which match, yields None so the caller fails
    instead of writing another tweet's content into this record.

    Taking items[0] on faith is what poisoned 36 X records under the pre-ee9fb37
    collector, so it is not offered as a fallback here even for compatibility.
    """
    if not items:
        return None
    if not expected_id:
        return items[0]

    for item in items:
        if str(item.get("id") or "") == str(expected_id):
            return item
    return None


def parse_twitter_cli_payload(payload, fallback_user, expected_id=None):
    if not payload.get("ok") or not payload.get("data"):
        return None

    main_tweet = select_focal_tweet(payload["data"], expected_id)
    if main_tweet is None:
        return None

    real_user = ((main_tweet.get("author") or {}).get("screenName")) or fallback_user
    full_text = main_tweet.get("text") or ""
    media = _normalize_media(main_tweet.get("media", []))
    if not full_text and not media:
        return None

    return TwitterCliDetail(
        full_text=full_text,
        media=media,
        real_user=real_user,
    )


def fetch_tweet_detail(url, target_user, env, timeout=30, runner=subprocess.run):
    try:
        result = runner(
            [sys.executable, "-m", "twitter_cli.cli", "tweet", url, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return parse_twitter_cli_payload(
        payload,
        fallback_user=target_user,
        expected_id=extract_tweet_id(url),
    )
