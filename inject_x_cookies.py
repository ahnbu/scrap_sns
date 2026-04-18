"""저장된 X 쿠키를 persistent context(x_user_data/)에 주입하여 세션 갱신.

renew_twitter_auth.py의 비대화형 대체 스크립트.
"""

import json
import time

from playwright.sync_api import sync_playwright

from utils.auth_paths import x_cookies_latest, x_user_data


def inject_cookies():
    cookies_path = x_cookies_latest()
    if cookies_path is None:
        print("쿠키 파일 없음")
        return False

    user_data_dir = x_user_data()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    with open(cookies_path, "r", encoding="utf-8") as file:
        cookies = json.load(file)

    print(f"쿠키 파일: {cookies_path} ({len(cookies)}개)")
    print(f"프로필: {user_data_dir}")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

        context.add_cookies(cookies)
        print(f"쿠키 {len(cookies)}개 주입 완료")

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        title = page.title()
        url = page.url
        print(f"페이지: {title} ({url})")

        logged_in = "홈" in title or "Home" in title
        if logged_in:
            print("로그인 상태 확인 — 세션 갱신 성공")
        else:
            print(f"로그인 실패 — 제목: {title}")

        context.close()
        return logged_in


if __name__ == "__main__":
    success = inject_cookies()
    raise SystemExit(0 if success else 1)
