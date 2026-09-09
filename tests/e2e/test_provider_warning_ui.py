"""자막 도구가 죽었을 때 그 사실이 결과창까지 오는지 본다.

2026-09-06에 PO token provider 폴더가 지워졌는데 9/9까지 아무도 몰랐다.
수집은 성공(종료코드 0)으로 끝나고 자막만 0건이 됐는데, 그 사실이 로그의 사람용
경고 한 줄로만 남아 화면이 침묵했다.

실제 수집은 돌리지 않는다 - `/api/run-scrap` 응답을 page.route 로 만들어
결과창 렌더만 검증한다. 계획: _docs/20260909_01 (W5 · W5-1·W5-2)
"""

import json
import os

import pytest
import requests

CARD = "#masonryGrid article.glass-card"
WARNING_LINE = ".scrap-result-warning-line"
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

BASE_RESULT = {
    "status": "success",
    "message": "Scraping finished",
    "run_id": "test-run",
    "output": "",
    "stats": {
        "total": 0,
        "threads": 0,
        "linkedin": 0,
        "twitter": 0,
        "youtube": 0,
        "total_count": 2880,
        "threads_count": 1000,
        "linkedin_count": 1000,
        "twitter_count": 500,
        "youtube_count": 380,
    },
    "consistency_probe": {},
    "auth_required": [],
    "platform_results": {},
}

PROVIDER_WARNING = {
    "tool": "bgutil-pot-provider",
    "platform": "youtube",
    "reason": "entry_missing",
    "impact": "new_transcripts_blocked",
    "path": "C:/Users/ahnbu/bgutil-ytdlp-pot-provider/server/build/main.js",
    "slot": "youtube",
}


@pytest.fixture(scope="module")
def server_url():
    try:
        response = requests.get(f"{VIEWER_URL}/api/status", timeout=3)
        if response.status_code != 200:
            pytest.fail(f"뷰어 서버가 비정상 응답: {VIEWER_URL} -> {response.status_code}")
    except requests.exceptions.RequestException as exc:
        pytest.fail(f"뷰어 서버에 접속할 수 없습니다: {VIEWER_URL} ({exc})")
    return VIEWER_URL


@pytest.fixture(scope="module")
def browser(playwright):
    instance = playwright.chromium.launch(headless=True)
    yield instance
    instance.close()


def _run_scrap_with_result(page, server_url, result):
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(800)

    page.route(
        "**/api/run-scrap",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(result, ensure_ascii=False),
        ),
    )
    page.on("dialog", lambda dialog: dialog.accept())

    trigger = page.query_selector("#runScrapBtn")
    if trigger is None:
        pytest.skip("업데이트 버튼을 찾지 못해 결과창을 판정할 수 없다")
    trigger.click()
    page.wait_for_selector("#scrapResultModal:not(.hidden)", timeout=20000)
    page.wait_for_timeout(1200)


@pytest.mark.e2e
def test_provider_warning_reaches_result_modal(browser, server_url):
    """W5-1: 도구 부재 경고가 결과창에 한 줄로 뜬다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        _run_scrap_with_result(
            page, server_url, {**BASE_RESULT, "warnings": [PROVIDER_WARNING]}
        )

        lines = page.locator(WARNING_LINE)
        assert lines.count() == 1, f"경고 줄이 1개가 아니다: {lines.count()}개"

        text = lines.first.text_content() or ""
        assert "유튜브 자막 도구" in text, f"도구 이름이 안 보인다: {text}"
        assert "설치 폴더를 찾지 못했습니다" in text, f"사유가 안 보인다: {text}"
        assert "요약도 만들어지지 않았습니다" in text, f"영향이 안 보인다: {text}"
    finally:
        context.close()


@pytest.mark.e2e
def test_no_warning_when_tools_are_healthy(browser, server_url):
    """W5-2: 정상 실행에서는 경고가 안 뜬다 - 소음이 되면 아무도 안 읽는다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        _run_scrap_with_result(page, server_url, {**BASE_RESULT, "warnings": []})
        assert page.locator(WARNING_LINE).count() == 0, "경고가 없는데 경고 줄이 떴다"
    finally:
        context.close()


@pytest.mark.e2e
def test_missing_warnings_key_is_safe(browser, server_url):
    """옛 서버 응답에는 이 키가 없다. 없다고 결과창이 깨지면 안 된다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        _run_scrap_with_result(page, server_url, dict(BASE_RESULT))
        assert page.locator(WARNING_LINE).count() == 0
        assert page.locator("#scrapResultBody").count() == 1, "결과창 본문이 렌더되지 않았다"
    finally:
        context.close()
