from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests

from utils.auth_paths import threads_storage


THREADS_COOKIE_KEYS = ("sessionid", "csrftoken", "ds_user_id", "mid", "ig_did", "rur")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ThreadsFetchResult:
    html: str
    status_code: int


def load_threads_cookies(auth_file: str | None = None) -> dict | None:
    resolved = Path(auth_file) if auth_file else threads_storage()
    with open(resolved, "r", encoding="utf-8") as file:
        storage_state = json.load(file)

    cookies = {}
    for cookie in storage_state.get("cookies", []):
        name = cookie.get("name")
        domain = str(cookie.get("domain") or "")
        if name not in THREADS_COOKIE_KEYS:
            continue
        if not domain.endswith(".threads.com"):
            continue
        cookies[name] = cookie.get("value")

    if not cookies.get("sessionid"):
        return None
    return cookies


def build_threads_headers(base_headers: dict | None = None) -> dict:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    if base_headers:
        headers.update(base_headers)
    return headers


def fetch_thread_html(
    url: str,
    cookies: dict,
    headers: dict,
    timeout: int = 15,
    runner=requests.get,
) -> ThreadsFetchResult | None:
    try:
        response = runner(
            url,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None
    return ThreadsFetchResult(html=response.text, status_code=response.status_code)
