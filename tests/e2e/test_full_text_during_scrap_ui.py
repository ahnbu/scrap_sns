"""수집이 도는 동안에도 본문 전체가 보이고 복사되는지 본다.

종전 결함: `prefetchDetail()` 안에 있던 `scrapRunInProgress` 가드가
`ensurePostDetail()` 까지 막아, 수집 중에는 Read more·복사·벌크 복사·이미지 캡션이
전부 200자(`full_text_preview`)로 떨어졌다. 사용자가 긴 글을 복사했다가 뒷부분이
사라진 채 붙는 것을 발견해 드러났다.

판정은 전부 assertion 으로 한다. 브라우저는 headless 로 고정한다.
실제 수집은 돌리지 않는다 - `/api/run-scrap` 을 page.route 로 붙잡아
`scrapRunInProgress` 만 참으로 만든다(기존 test_viewer_console_cleanup_ui.py 와 같은 기법).

계획: _docs/20260909_01 (W1 · T1~T4)
"""

import os

import pytest
import requests

CARD = "#masonryGrid article.glass-card"
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

#: 이 길이를 넘는 글이라야 200자 절단이 드러난다.
MIN_LONG_TEXT = 300

#: Windows 클립보드가 줄바꿈을 CRLF 로 바꿔 돌려준다.
CRLF = chr(13) + chr(10)
LF = chr(10)


@pytest.fixture(scope="module")
def server_url():
    try:
        response = requests.get(f"{VIEWER_URL}/api/status", timeout=3)
        if response.status_code != 200:
            pytest.fail(
                f"뷰어 서버가 비정상 응답: {VIEWER_URL} -> {response.status_code}. "
                f"`npm run restart` 로 서버를 먼저 띄우세요."
            )
    except requests.exceptions.RequestException as exc:
        pytest.fail(
            f"뷰어 서버에 접속할 수 없습니다: {VIEWER_URL} ({exc}). "
            f"`npm run restart` 로 서버를 먼저 띄우세요."
        )
    return VIEWER_URL


@pytest.fixture(scope="module")
def browser(playwright):
    instance = playwright.chromium.launch(headless=True)
    yield instance
    instance.close()


@pytest.fixture(scope="module")
def long_post(server_url):
    """긴 본문을 가진 게시글 하나를 API 에서 고른다."""
    payload = requests.get(f"{server_url}/api/posts", timeout=30).json()
    posts = payload.get("posts") if isinstance(payload, dict) else payload
    for post in posts or []:
        if int(post.get("full_text_length") or 0) >= MIN_LONG_TEXT:
            detail = requests.get(
                f"{server_url}/api/post/{post['sequence_id']}", timeout=30
            ).json()
            if detail.get("full_text"):
                return {**post, "full_text": detail["full_text"]}
    pytest.skip(f"{MIN_LONG_TEXT}자 이상인 게시글이 없어 절단을 판정할 수 없다")


def normalize_newlines(value):
    """클립보드 줄바꿈 표기 차이만 걷어낸다."""
    return str(value).replace(CRLF, LF)


def strip_newlines(value):
    """화면 텍스트 비교용.

    본문의 줄바꿈은 `<br>` 로 렌더되므로 textContent 에 남지 않는다
    (linkifyText 의 마지막 줄이 개행을 `<br>` 로 바꾼다).
    """
    return str(value).replace(LF, "")


def _enter_scrap_running_state(page, server_url):
    """실제 수집 없이 `scrapRunInProgress` 만 참으로 만든다."""
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(1200)

    # 응답하지 않는 라우트라 버튼 핸들러가 await 에서 멈추고 플래그가 유지된다.
    page.route("**/api/run-scrap", lambda route: None)
    page.on("dialog", lambda dialog: dialog.accept())

    trigger = page.query_selector("#runScrapBtn") or page.query_selector("#scrapBtn")
    if trigger is None:
        pytest.skip("업데이트 트리거 버튼을 찾지 못해 수집 중 상태를 만들 수 없다")
    trigger.click()
    page.wait_for_timeout(1500)


def _find_card(page, post):
    """대상 게시글의 카드를 검색으로 좁혀 첫 카드로 만든다."""
    search = page.query_selector("#searchInput") or page.query_selector("input[type='search']")
    if search is None:
        pytest.skip("검색 입력을 찾지 못해 대상 카드를 특정할 수 없다")

    # 본문 앞머리에서 검색어를 만든다. 특수문자·줄바꿈은 뺀다.
    seed = " ".join(str(post["full_text"])[:60].split())[:20]
    search.fill(seed)
    page.wait_for_timeout(1800)
    page.wait_for_selector(CARD, timeout=20000)
    return page.locator(CARD).first


@pytest.mark.e2e
def test_t1_read_more_shows_full_text_during_scrap(browser, server_url, long_post):
    """T1: 수집 중 Read more → 화면 글자 수가 full_text 길이와 같다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        _enter_scrap_running_state(page, server_url)
        card = _find_card(page, long_post)

        indicator = card.locator(".read-more-indicator")
        if indicator.count() == 0:
            pytest.skip("대상 카드에 Read more 가 없다")

        indicator.first.click()
        page.wait_for_timeout(1500)

        shown = card.locator("p[data-clamp-class]").first.text_content() or ""
        expected_text = strip_newlines(long_post["full_text"])

        assert len(shown) > 200, f"Read more 를 눌러도 200자에서 잘렸다: {len(shown)}자"
        assert len(shown) == len(expected_text), (
            f"표시 글자 수가 full_text 길이와 다르다: "
            f"표시 {len(shown)} / 원본 {len(expected_text)}"
        )
        assert shown == expected_text, "표시된 본문이 원본과 다르다"
    finally:
        context.close()


@pytest.mark.e2e
def test_t2_copy_gives_full_text_during_scrap(browser, server_url, long_post):
    """T2: 수집 중 복사 → 클립보드에 본문 전체가 담긴다."""
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    try:
        _enter_scrap_running_state(page, server_url)
        card = _find_card(page, long_post)

        card.locator(".copy-btn").first.click()
        page.wait_for_timeout(1500)

        copied = normalize_newlines(page.evaluate("navigator.clipboard.readText()"))
        expected = str(long_post["full_text"])

        assert len(copied) > 200, f"복사본이 200자에서 잘렸다: {len(copied)}자"
        assert expected in copied, "복사본에 본문 전체가 들어 있지 않다"
    finally:
        context.close()


@pytest.mark.e2e
def test_t3_hover_prefetch_still_blocked_during_scrap(browser, server_url):
    """T3: hover 프리페치는 여전히 막힌다.

    T1·T2 만 고치고 가드를 통째로 열면 원래 막으려던 ERR_NETWORK_CHANGED 가
    되살아난다. 기존 test_viewer_console_cleanup_ui.py 의 V4 와 짝을 이룬다.
    """
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        _enter_scrap_running_state(page, server_url)

        detail_requests = []
        page.on("request", lambda req: (
            detail_requests.append(req.url) if "/api/post/" in req.url else None
        ))

        cards = page.locator(CARD)
        for i in range(min(cards.count(), 5)):
            cards.nth(i).hover()
            page.wait_for_timeout(200)
        page.wait_for_timeout(800)

        assert detail_requests == [], (
            f"수집 중인데 hover 프리페치가 나갔다: {detail_requests}"
        )
    finally:
        context.close()


@pytest.mark.e2e
def test_t4_bulk_copy_gives_full_text_during_scrap(browser, server_url, long_post):
    """T4: 수집 중 벌크 복사도 전문을 준다.

    SPEC 은 막히는 경로를 Read more·복사 둘로 봤으나 실제로는 넷이다 -
    벌크 복사와 이미지 캡션도 같은 함수를 지난다.
    """
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    try:
        _enter_scrap_running_state(page, server_url)
        card = _find_card(page, long_post)

        select_btn = card.locator(".select-btn")
        if select_btn.count() == 0:
            pytest.skip("선택 버튼이 없어 벌크 복사를 판정할 수 없다")
        select_btn.first.click()
        page.wait_for_timeout(600)

        bulk_copy = page.query_selector("#bulkCopyBtn")
        if bulk_copy is None:
            pytest.skip("벌크 복사 버튼을 찾지 못했다")
        bulk_copy.click()
        page.wait_for_timeout(1500)

        copied = normalize_newlines(page.evaluate("navigator.clipboard.readText()"))
        assert str(long_post["full_text"]) in copied, (
            "벌크 복사본에 본문 전체가 들어 있지 않다"
        )
    finally:
        context.close()
