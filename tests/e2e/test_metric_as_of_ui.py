"""지표 기준일 표시(W3) E2E 검증.

지표를 "언제 읽은 값"인지 카드에 드러내는 변경이다. 갱신 주기를 아무리 짧게
잡아도 시점 차이는 남으므로, 숫자만 보여주면 서로 다른 시점의 값을 같은
기준으로 비교하게 된다.

판정은 전부 assertion 으로 한다. 브라우저는 headless 로 고정한다.

계획: _docs/20260826_02_뷰어정리-유튜브확대-지표갱신-웨이브계획.md (W3)
"""

import os

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
METRICS_ROW = ".metrics-row"
AS_OF = ".metric-as-of"

VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")


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
def posts(server_url):
    payload = requests.get(f"{server_url}/api/posts", timeout=60).json()
    return payload.get("posts", payload)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.mark.e2e
def test_api_exposes_metrics_updated_at(posts):
    """W3 전제: 목록 응답에 갱신 시각이 실려야 카드가 그릴 수 있다.

    utils/post_meta.py 의 META_FIELDS 에서 빠지면 /api/posts 가 값을 떨어뜨린다.
    """
    with_as_of = [p for p in posts if p.get("metrics_updated_at")]
    assert with_as_of, "metrics_updated_at 을 가진 게시글이 API 응답에 하나도 없다"


@pytest.mark.e2e
def test_metric_as_of_badge_renders(browser, server_url, posts):
    """갱신 시각을 가진 글의 카드에 기준일 배지가 보인다."""
    if not [p for p in posts if p.get("metrics_updated_at")]:
        pytest.skip("갱신 시각을 가진 게시글이 없어 판정할 수 없다")

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1500)
        # 지표 보유 글이 상단에 모이도록 반응순으로 정렬한다.
        page.evaluate("localStorage.setItem('sns_sort_order', 'engagement')")
        page.reload()
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1500)

        assert page.locator(AS_OF).count() > 0, "기준일 배지가 한 장도 렌더되지 않았다"
    finally:
        context.close()


@pytest.mark.e2e
def test_as_of_badge_only_inside_metrics_row(browser, server_url):
    """기준일 배지는 지표 행 안에만 존재한다 - 지표 없는 카드에 붙으면 소음이다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.evaluate("localStorage.setItem('sns_sort_order', 'engagement')")
        page.reload()
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1500)

        total = page.locator(AS_OF).count()
        inside = page.locator(f"{METRICS_ROW} {AS_OF}").count()
        assert total == inside, (
            f"지표 행 밖에 기준일 배지가 있다: 전체 {total} / 행 안 {inside}"
        )
    finally:
        context.close()
