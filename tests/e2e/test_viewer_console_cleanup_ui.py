"""뷰어 콘솔 정리(W1) E2E 검증.

업데이트 클릭 순간 브라우저 4개가 동시에 뜨면서 Chrome 이 진행 중인 로컬 요청을
전부 끊어(ERR_NETWORK_CHANGED) 콘솔이 빨간 글씨로 덮이던 문제를 다룬다.

판정은 전부 assertion 으로 한다. 사람이 콘솔을 눈으로 읽는 방식을 쓰지 않는다.
브라우저는 headless 로 고정한다 (창이 뜨면 사용자 포커스를 뺏는다).

V3 는 캐시버스터가 갱신된 값으로 서빙되는지를 HTML 문자열로 확인한다.
V4 는 스크랩 진행 중 프리페치가 멈추는지를 확인하되, `/api/run-scrap` 을
page.route 로 가로채 실제 수집이 돌지 않게 한다 — 실제 수집을 검증에 끼우면
output_* 와 병행 세션에 영향을 준다.

계획: _docs/20260826_02_뷰어정리-유튜브확대-지표갱신-웨이브계획.md (W1 V3·V4)
"""

import os
import re

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"

# 자체 서버를 띄우지 않는 이유는 test_metric_layout_ui.py 와 같다.
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

# index.html 이 서빙해야 하는 캐시버스터 값. W1 종료 시점 값이다.
EXPECTED_CACHE_BUSTER = "20260826-w1t"


@pytest.fixture(scope="module")
def server_url():
    try:
        response = requests.get(f"{VIEWER_URL}/api/status", timeout=3)
        if response.status_code != 200:
            pytest.fail(
                f"뷰어 서버가 비정상 응답: {VIEWER_URL} -> {response.status_code}. "
                f"`wscript sns_hub.vbs` 또는 `npm run view` 로 서버를 먼저 띄우세요."
            )
    except requests.exceptions.RequestException as exc:
        pytest.fail(
            f"뷰어 서버에 접속할 수 없습니다: {VIEWER_URL} ({exc}). "
            f"`wscript sns_hub.vbs` 또는 `npm run view` 로 서버를 먼저 띄우세요."
        )
    return VIEWER_URL


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.mark.e2e
def test_v3_cache_buster_is_current(server_url):
    """V3: index.html 이 갱신된 캐시버스터로 정적 자산을 참조한다.

    DevTools 를 사람이 여는 대신 서빙된 HTML 을 직접 읽어 판정한다.
    이 값이 낡으면 코드를 고쳐도 브라우저가 이전 파일을 계속 쓴다.
    """
    html = requests.get(f"{server_url}/", timeout=10).text

    for asset in ("style.css", "script.js"):
        pattern = rf"{re.escape(asset)}\?v=([0-9A-Za-z._-]+)"
        found = re.search(pattern, html)
        assert found, f"{asset} 에 캐시버스터 쿼리가 없다"
        assert found.group(1) == EXPECTED_CACHE_BUSTER, (
            f"{asset} 캐시버스터가 낡았다: {found.group(1)!r} "
            f"(기대값 {EXPECTED_CACHE_BUSTER!r})"
        )


@pytest.mark.e2e
def test_v2_metrics_only_button_absent(browser, server_url):
    """V2: '지표 보유만' 버튼이 DOM 에 없다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        assert page.query_selector("#metricsOnlyBtn") is None, \
            "'지표 보유만' 버튼이 아직 DOM 에 남아 있다"
    finally:
        context.close()


@pytest.mark.e2e
def test_v4_no_prefetch_while_scrap_running(browser, server_url):
    """V4: 스크랩 진행 중에는 hover 프리페치 요청이 나가지 않는다.

    scrapRunInProgress 는 DOMContentLoaded 스코프에 있어 밖에서 세울 수 없다.
    그래서 실제 버튼을 누르되 `/api/run-scrap` 을 가로채 붙잡아 둔다 —
    플래그만 참이 되고 total_scrap.py 는 실행되지 않는다.
    """
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1200)

        # 진행 중인 초기 프리페치가 끝나도록 잠시 둔다.
        detail_requests = []
        page.on("request", lambda req: (
            detail_requests.append(req.url) if "/api/post/" in req.url else None
        ))

        # run-scrap 은 서버로 보내지 않고 붙잡아 둔다. 응답하지 않으므로
        # 버튼 핸들러는 await 에서 멈추고 scrapRunInProgress 가 참으로 유지된다.
        page.route("**/api/run-scrap", lambda route: None)
        page.on("dialog", lambda dialog: dialog.accept())

        trigger = page.query_selector("#runScrapBtn") or page.query_selector("#scrapBtn")
        if trigger is None:
            pytest.skip("업데이트 트리거 버튼을 찾지 못해 V4 를 판정할 수 없다")

        trigger.click()
        page.wait_for_timeout(1500)

        detail_requests.clear()

        cards = page.locator(CARD)
        for i in range(min(cards.count(), 5)):
            cards.nth(i).hover()
            page.wait_for_timeout(200)
        page.wait_for_timeout(800)

        assert detail_requests == [], (
            f"스크랩 진행 중인데 프리페치 요청이 나갔다: {detail_requests}"
        )
    finally:
        context.close()
