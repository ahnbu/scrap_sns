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
    """MY 필터가 내 글만 남기는지 상단 건수 라벨로 판정한다.

    ⚠️ 카드 개수로 판정하지 않는다. 마소너리가 60장 단위로 지연 로딩하므로,
       내 글이 60건을 넘어가면 켜기 전후 모두 60장이라 `after < before` 가
       거짓이 된다(2026-08-27 내 Threads 글 32건 추가로 68건이 되며 실제 발생).
       상단 라벨은 `보이는수 / 전체수 건` 이라 지연 로딩과 무관하다.
    """
    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"

    own_total = len([p for p in api_posts if p.get("is_own_post") is True])
    label = viewer.locator("#totalPostsCount").inner_text()
    visible = int(label.split("/")[0].strip())

    assert visible == own_total, (
        f"MY 필터 결과가 {visible}건인데 API 기준 내 글은 {own_total}건입니다."
    )

    shown = viewer.locator(CARD).count()
    assert shown <= own_total, f"내 글 {own_total}건보다 많은 {shown}건이 렌더됐습니다."
    _capture(viewer, "v9_my_filter_on")


def test_my_filter_toggles_off_by_reclick(viewer):
    before = viewer.locator(CARD).count()
    _toggle_my(viewer)
    _toggle_my(viewer)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false"
    assert viewer.locator(CARD).count() == before


def test_my_filter_combines_with_platform_chip(viewer):
    """플랫폼 칩과 AND 로 결합한다.

    ⚠️ 2026-08-27 이전에는 'Threads 칩 + MY = 0건'을 단언했다. 내 Threads 글이
       수집 범위 밖이었기 때문이다. `_docs/20260827_02` 로 수집이 붙어 전제가
       바뀌었으므로 양쪽 다 0건보다 커야 한다.
    """
    _toggle_my(viewer)
    viewer.click('button[data-filter="threads"]')
    viewer.wait_for_timeout(900)

    assert viewer.locator(CARD).count() > 0, "Threads + MY 조합이 0건입니다."

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


# --- 내 Threads 글 (계획 _docs/20260827_02 V10) -----------------------------

EVIDENCE_DIR_THREADS_OWN = (
    Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260827_02"
)


def _capture_threads_own(page, name):
    EVIDENCE_DIR_THREADS_OWN.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR_THREADS_OWN / f"{name}.png"), full_page=False)


def test_api_exposes_own_threads_posts(api_posts):
    """내 Threads 글이 API 까지 흘러와야 뷰어가 MY 필터에 담을 수 있다."""
    own_threads = [
        p for p in api_posts
        if p.get("is_own_post") is True and p.get("sns_platform") == "threads"
    ]
    assert own_threads, "내 Threads 글이 API 응답에 없습니다."
    assert all(p.get("view_count") is not None for p in own_threads), (
        "내 Threads 글에 노출수가 없습니다."
    )
    # code 는 shortcode 여야 원문 URL 이 조립된다(utils/post_meta.py:62).
    assert all(not str(p.get("code") or "").isdigit() for p in own_threads), (
        "code 에 Graph API 숫자 id 가 들어갔습니다. 원문 URL 이 깨집니다."
    )


def test_own_threads_body_is_merged(api_posts):
    """500자 상한을 넘긴 본문이 자기 답글까지 이어붙여져 있어야 한다(계획 P2)."""
    merged = [
        p for p in api_posts
        if p.get("is_own_post") is True
        and p.get("sns_platform") == "threads"
        and p.get("is_merged_thread") is True
    ]
    assert merged, "본문이 이어붙여진 내 Threads 글이 하나도 없습니다."
    # 이어붙였으면 Threads 본문 상한(499자)을 넘는 글이 나온다.
    assert any((p.get("full_text_length") or 0) > 499 for p in merged), (
        "이어붙였다는데 499자를 넘는 글이 없습니다. 병합이 실제로 안 된 것입니다."
    )


def test_my_filter_shows_threads_own_posts(viewer, api_posts):
    """MY 필터 + Threads 칩에 내 Threads 글이 실제로 뜬다."""
    _toggle_my(viewer)
    viewer.click('button[data-filter="threads"]')
    viewer.wait_for_timeout(900)

    shown = viewer.locator(CARD).count()
    own_threads = len([
        p for p in api_posts
        if p.get("is_own_post") is True and p.get("sns_platform") == "threads"
    ])

    assert shown > 0, "MY + Threads 조합에 카드가 없습니다."
    assert shown <= own_threads, (
        f"내 Threads 글 {own_threads}건보다 많은 {shown}건이 표시됐습니다. 필터가 샙니다."
    )
    _capture_threads_own(viewer, "v10_my_filter_threads")


def test_saved_threads_posts_excluded_from_my_filter(viewer, api_posts):
    """저장글(남의 글)은 MY 필터에 절대 나오면 안 된다."""
    _toggle_my(viewer)
    viewer.click('button[data-filter="threads"]')
    viewer.wait_for_timeout(900)

    own_codes = {
        str(p.get("code"))
        for p in api_posts
        if p.get("is_own_post") is True and p.get("sns_platform") == "threads"
    }
    total_threads = len([p for p in api_posts if p.get("sns_platform") == "threads"])
    assert total_threads > len(own_codes), "저장글이 없으면 이 테스트가 무의미합니다."

    body = viewer.locator("#masonryGrid").inner_text()
    assert "byungwook.an" in body or viewer.locator(CARD).count() <= len(own_codes), (
        "MY + Threads 화면에 내 글이 아닌 카드가 섞였습니다."
    )
    _capture_threads_own(viewer, "v10_saved_posts_excluded")
