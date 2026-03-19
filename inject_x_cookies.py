"""저장된 X 쿠키를 persistent context(x_user_data/)에 주입하여 세션 갱신.

renew_twitter_auth.py의 비대화형 대체 스크립트.
Playwright MCP에서 추출한 쿠키를 channel="chrome" persistent context에 로드.
"""
import json
import os
import time
from playwright.sync_api import sync_playwright

AUTH_DIR = os.path.join(os.path.dirname(__file__), "auth")
USER_DATA_DIR = os.path.join(AUTH_DIR, "x_user_data")
COOKIES_FILE = os.path.join(AUTH_DIR, "x_cookies_20260318.json")


def inject_cookies():
    if not os.path.exists(COOKIES_FILE):
        print(f"쿠키 파일 없음: {COOKIES_FILE}")
        return False

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"쿠키 파일: {COOKIES_FILE} ({len(cookies)}개)")
    print(f"프로필: {USER_DATA_DIR}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        # 쿠키 주입
        context.add_cookies(cookies)
        print(f"쿠키 {len(cookies)}개 주입 완료")

        # x.com 접속하여 로그인 상태 확인
        page = context.pages[0]
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
    exit(0 if success else 1)
