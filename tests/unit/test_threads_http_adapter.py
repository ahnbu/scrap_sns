import json

import pytest
import requests

from utils.threads_http_adapter import (
    ThreadsFetchResult,
    build_threads_headers,
    fetch_thread_html,
    load_threads_cookies,
)


def _write_storage_state(path, cookies):
    path.write_text(
        json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_load_threads_cookies_reads_storage_state(tmp_path):
    auth_file = tmp_path / "auth_threads.json"
    _write_storage_state(
        auth_file,
        [
            {"name": "sessionid", "value": "session", "domain": ".threads.com"},
            {"name": "csrftoken", "value": "csrf", "domain": ".threads.com"},
            {"name": "ds_user_id", "value": "123", "domain": ".threads.com"},
            {"name": "mid", "value": "mid", "domain": ".threads.com"},
            {"name": "ig_did", "value": "igid", "domain": ".threads.com"},
            {"name": "rur", "value": "rur", "domain": ".threads.com"},
        ],
    )

    assert load_threads_cookies(str(auth_file)) == {
        "sessionid": "session",
        "csrftoken": "csrf",
        "ds_user_id": "123",
        "mid": "mid",
        "ig_did": "igid",
        "rur": "rur",
    }


def test_load_threads_cookies_returns_none_when_sessionid_missing(tmp_path):
    auth_file = tmp_path / "auth_threads.json"
    _write_storage_state(
        auth_file,
        [
            {"name": "csrftoken", "value": "csrf", "domain": ".threads.com"},
            {"name": "ds_user_id", "value": "123", "domain": ".threads.com"},
        ],
    )

    assert load_threads_cookies(str(auth_file)) is None


def test_load_threads_cookies_filters_non_threads_domains(tmp_path):
    auth_file = tmp_path / "auth_threads.json"
    _write_storage_state(
        auth_file,
        [
            {"name": "sessionid", "value": "session", "domain": ".threads.com"},
            {"name": "csrftoken", "value": "csrf", "domain": ".threads.com"},
            {"name": "ds_user_id", "value": "123", "domain": ".threads.com"},
            {"name": "mid", "value": "mid", "domain": ".threads.com"},
            {"name": "ig_did", "value": "igid", "domain": ".threads.com"},
            {"name": "rur", "value": "rur", "domain": ".threads.com"},
            {"name": "sessionid", "value": "bad", "domain": ".instagram.com"},
        ],
    )

    assert load_threads_cookies(str(auth_file))["sessionid"] == "session"


def test_build_threads_headers_preserves_override():
    headers = build_threads_headers({"User-Agent": "CustomUA/1.0"})

    assert headers["User-Agent"] == "CustomUA/1.0"
    assert headers["Accept-Language"].startswith("ko-KR")


def test_fetch_thread_html_wraps_200_response():
    class Response:
        status_code = 200
        text = "<html>ok</html>"

    def runner(url, cookies, headers, timeout, allow_redirects):
        return Response()

    result = fetch_thread_html(
        "https://www.threads.com/@user/post/CODE",
        cookies={"sessionid": "x"},
        headers={"User-Agent": "ua"},
        runner=runner,
    )

    assert result == ThreadsFetchResult(html="<html>ok</html>", status_code=200)


def test_fetch_thread_html_returns_none_on_302():
    class Response:
        status_code = 302
        text = ""

    def runner(url, cookies, headers, timeout, allow_redirects):
        return Response()

    assert (
        fetch_thread_html(
            "https://www.threads.com/@user/post/CODE",
            cookies={"sessionid": "x"},
            headers={"User-Agent": "ua"},
            runner=runner,
        )
        is None
    )


def test_fetch_thread_html_returns_none_on_timeout():
    def runner(url, cookies, headers, timeout, allow_redirects):
        raise requests.exceptions.Timeout("boom")

    assert (
        fetch_thread_html(
            "https://www.threads.com/@user/post/CODE",
            cookies={"sessionid": "x"},
            headers={"User-Agent": "ua"},
            runner=runner,
        )
        is None
    )
