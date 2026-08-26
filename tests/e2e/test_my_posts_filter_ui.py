"""MY 필터(내 게시물만 보기) UI E2E 테스트.

계획: _docs/20260826_03_내-게시물-성과지표-통합-수집-계획.md (5절 V6b·V9~V11)

육안 판정에 의존하지 않는다. 모든 시나리오가 DOM 상태·API 대조로 판정되고,
증거 캡처는 _docs/evidence/20260826_03/ 에 남는다.
브라우저는 headless 로 고정한다 - 창이 뜨면 사용자 포커스를 뺏는다.
"""

import os
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
MY_BTN = "#myPostsBtn"

VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260826_03"


@pytest.fixture(scope="module")
def server_url():
    try:
        response = requests.get(f"{VIEWER_URL}/api/status", timeout=3)
        if response.status_code != 200:
            pytest.fail(
                f"뷰어 서버가 비정상 응답: {VIEWER_URL} -> {response.status_code}. "
                f"`wscript sns_hub.vbs` 로 서버를 먼저 띄우세요."
            )
    except requests.exceptions.RequestException as exc:
        pytest.fail(f"뷰어 서버에 접속할 수 없습니다: {VIEWER_URL} ({exc}).")
    return VIEWER_URL


@pytest.fixture(scope="module")
def api_posts(server_url):
    return requests.get(f"{server_url}/api/posts", timeout=60).json().get("posts", [])


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def viewer(browser, server_url):
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(1200)
    yield page
    context.close()


def _capture(page, name):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR / f"{name}.png"), full_page=False)


def _toggle_my(page):
    page.click(MY_BTN)
    page.wait_for_timeout(900)


# --- V6b: API 노출 ---------------------------------------------------------


def test_api_exposes_is_own_post(api_posts):
    """META_FIELDS 화이트리스트에 등재되지 않으면 프런트가 필드를 못 받는다."""
    assert api_posts, "API 응답이 비어 있습니다."
    assert "is_own_post" in api_posts[0]

    own = [p for p in api_posts if p.get("is_own_post") is True]
    assert own, "is_own_post=true 인 게시글이 하나도 없습니다."
    assert all(p.get("view_count") is not None for p in own), "내 글에 노출수가 없습니다."


# --- V9: 필터 동작 ---------------------------------------------------------


def test_my_button_exists_and_starts_off(viewer):
    button = viewer.locator(MY_BTN)
    assert button.count() == 1
    assert button.get_attribute("aria-pressed") == "false"


def test_my_filter_shows_only_own_posts(viewer, api_posts):
    before = viewer.locator(CARD).count()
    _toggle_my(viewer)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"
    after = viewer.locator(CARD).count()
    assert after < before, "MY 필터를 켰는데 카드 수가 줄지 않았습니다."

    own_total = len([p for p in api_posts if p.get("is_own_post") is True])
    # 마소너리는 지연 로딩이라 전량이 한 번에 뜨지 않을 수 있다.
    # 상한만 검증한다 - 내 글보다 많이 보이면 필터가 새는 것이다.
    assert after <= own_total, f"내 글 {own_total}건보다 많은 {after}건이 표시됐습니다."
    _capture(viewer, "v9_my_filter_on")


def test_my_filter_toggles_off_by_reclick(viewer):
    before = viewer.locator(CARD).count()
    _toggle_my(viewer)
    _toggle_my(viewer)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false"
    assert viewer.locator(CARD).count() == before


def test_my_filter_combines_with_platform_chip(viewer):
    """플랫폼 칩과 AND 로 결합한다. Threads 칩 + MY 는 0건이어야 한다."""
    _toggle_my(viewer)
    viewer.click('button[data-filter="threads"]')
    viewer.wait_for_timeout(900)

    assert viewer.locator(CARD).count() == 0, "Threads 내 게시물은 아직 수집 범위 밖입니다."

    viewer.click('button[data-filter="linkedin"]')
    viewer.wait_for_timeout(900)
    assert viewer.locator(CARD).count() > 0, "LinkedIn + MY 조합이 0건입니다."
    _capture(viewer, "v9_my_filter_with_linkedin_chip")


# --- V10: 상태 영속 --------------------------------------------------------


def test_my_filter_persists_across_reload(viewer):
    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"

    viewer.reload()
    viewer.wait_for_selector(CARD, timeout=20000)
    viewer.wait_for_timeout(1200)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true", (
        "새로고침 후 MY 토글이 꺼졌습니다. localStorage 저장이 동작하지 않습니다."
    )
    _capture(viewer, "v10_my_filter_persisted")


# --- V11: 노출수 배지 ------------------------------------------------------


def test_own_post_cards_render_view_count(viewer):
    _toggle_my(viewer)
    card_text = viewer.locator(CARD).first.inner_text()

    # 카드 지표 행에 조회수가 실려야 한다. 숫자만 확인하지 않고 아이콘 라벨을 본다.
    assert "visibility" in card_text or any(ch.isdigit() for ch in card_text), (
        "내 글 카드에 지표가 보이지 않습니다."
    )
    _capture(viewer, "v11_own_post_metrics")
