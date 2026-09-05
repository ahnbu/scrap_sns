from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from auth_paths import read_x_cookie_tokens, x_cookie_link, x_user_data
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from utils.auth_paths import read_x_cookie_tokens, x_cookie_link, x_user_data


def classify_producer_probe(
    *,
    current_url: str,
    bookmark_response_seen: bool,
    parsed_bookmark_count: int,
    article_count: int,
) -> tuple[bool, str]:
    lowered = current_url.lower()
    if "login" in lowered or "signup" in lowered or "challenge" in lowered:
        return False, "login_required"
    if parsed_bookmark_count > 0:
        return True, "bookmark_response"
    if bookmark_response_seen or article_count > 0:
        return True, "bookmarks_loaded"
    return False, "no_bookmark_signal"


def build_probe_report(*, producer_ok: bool, consumer_ok: bool) -> dict[str, bool]:
    return {"producer_ok": producer_ok, "consumer_ok": consumer_ok}


def is_transient_browser_launch_error(error: Exception) -> bool:
    message = str(error)
    transient_patterns = (
        "Browser window not found",
        "Target page, context or browser has been closed",
    )
    return any(pattern in message for pattern in transient_patterns)


def x_probe_launch_configs() -> list[dict]:
    base = {
        "user_data_dir": str(x_user_data()),
        "headless": True,
    }
    return [
        {**base, "channel": "chrome"},
        base,
    ]


def launch_x_persistent_context(playwright, *, attempts: int = 3, wait_seconds: float = 1.0):
    last_error = None
    configs = x_probe_launch_configs()
    for config_index, config in enumerate(configs):
        for attempt in range(attempts):
            try:
                return playwright.chromium.launch_persistent_context(**config)
            except Exception as error:
                last_error = error
                is_last_attempt = attempt == attempts - 1
                is_last_config = config_index == len(configs) - 1
                if not is_transient_browser_launch_error(error) or (
                    is_last_attempt and is_last_config
                ):
                    raise
                if is_last_attempt:
                    break
                time.sleep(wait_seconds)
    raise last_error


def probe_consumer() -> bool:
    tokens = read_x_cookie_tokens(x_cookie_link())
    return bool(tokens and tokens.get("auth_token") and tokens.get("ct0"))


def probe_producer(playwright=None) -> tuple[bool, str]:
    """X producer 세션이 살아 있는지 확인한다.

    `playwright` 를 주면 그 인스턴스를 쓰고, 없으면 직접 연다.

    주입 경로가 필요한 이유: `sync_playwright()` 는 **이미 실행 중인 이벤트 루프**
    안에서 부르면 거부한다. pytest-playwright 의 `playwright` fixture 는 session
    스코프라 한 번 쓰이면 세션 끝까지 루프를 잡고 있고, 그 뒤에 이 함수가 자기
    `sync_playwright()` 를 열면 중첩이 되어 끊긴다. 그래서 테스트는 fixture 가 만든
    인스턴스를 그대로 넘긴다. 단독 실행(`main()`)은 종전대로 직접 연다.
    """
    if playwright is not None:
        return _probe_producer_with(playwright)
    with sync_playwright() as owned_playwright:
        return _probe_producer_with(owned_playwright)


def _probe_producer_with(playwright) -> tuple[bool, str]:
    state = {"bookmark_response_seen": False, "parsed_bookmark_count": 0}
    context = launch_x_persistent_context(playwright)
    try:
        page = context.pages[0] if context.pages else context.new_page()

        def handle_response(response):
            if "Bookmarks?variables=" not in response.url:
                return
            state["bookmark_response_seen"] = True
            if response.status != 200:
                return
            try:
                response.json()
            except Exception:
                return
            state["parsed_bookmark_count"] += 1

        page.on("response", handle_response)
        # expect_response 는 컨텍스트매니저라 응답을 유발하는 goto 를 감싸야 한다.
        # 동기 API 에 wait_for_response 가 없어 기존 코드는 항상 5초 blind wait 로 떨어졌다.
        try:
            with page.expect_response(
                lambda item: "Bookmarks?variables=" in item.url,
                timeout=10000,
            ) as response_info:
                page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
            handle_response(response_info.value)
        except Exception:
            page.wait_for_timeout(5000)
        article_count = page.locator('article[data-testid="tweet"]').count()
        return classify_producer_probe(
            current_url=page.url,
            bookmark_response_seen=state["bookmark_response_seen"],
            parsed_bookmark_count=state["parsed_bookmark_count"],
            article_count=article_count,
        )
    finally:
        context.close()


def main() -> int:
    producer_ok, _reason = probe_producer()
    consumer_ok = probe_consumer()
    print(
        json.dumps(
            build_probe_report(producer_ok=producer_ok, consumer_ok=consumer_ok),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if producer_ok and consumer_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
