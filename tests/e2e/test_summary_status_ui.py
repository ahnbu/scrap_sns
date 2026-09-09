"""유튜브 요약이 없을 때 그 사유가 카드에 한 줄로 뜨는지 본다.

종전에는 요약이 비면 `build_full_text()` 가 그 블록을 통째로 건너뛰어 카드가
제목에서 [설명] 로 바로 넘어갔다. 사용자가 "뭔가 오류가 있나 싶다"고 한 이유다.

표시 문자열을 수집 데이터에 넣지 않고 뷰어가 그린다 - 자막이 나중에 붙어도
옛 문구가 통합본에 남지 않는다(A3 결정). 그래서 근거는 목록 응답의
`summary_status`·`transcript_status` 두 값뿐이고, 그 둘이 실려 오는지는
tests/unit/test_summary_status_meta.py 가 따로 지킨다.

계획: _docs/20260909_01 (W2 · T6)
"""

import os

import pytest
import requests

CARD = "#masonryGrid article.glass-card"
NOTICE = ".summary-status-line"
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

EXPECTED_TEXT = {
    "blocked": "자막을 못 받았습니다",
    "no_subtitle": "이 영상에 자막이 없습니다",
    "members_only": "멤버십 전용 영상입니다",
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


@pytest.fixture(scope="module")
def api_posts(server_url):
    payload = requests.get(f"{server_url}/api/posts", timeout=60).json()
    return payload.get("posts") if isinstance(payload, dict) else payload


@pytest.fixture(scope="module")
def no_transcript_post(api_posts):
    for post in api_posts or []:
        if post.get("summary_status") == "no_transcript" and post.get("transcript_status"):
            return post
    pytest.skip("요약 없음 상태인 유튜브 글이 없어 판정할 수 없다")


def _open_card_for(page, server_url, post):
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)

    search = page.query_selector("#searchInput") or page.query_selector("input[type='search']")
    if search is None:
        pytest.skip("검색 입력을 찾지 못해 대상 카드를 특정할 수 없다")

    seed = " ".join(str(post.get("full_text_preview") or "")[:60].split())[:20]
    search.fill(seed)
    page.wait_for_timeout(1800)
    page.wait_for_selector(CARD, timeout=20000)
    return page.locator(CARD).first


@pytest.mark.e2e
def test_no_transcript_card_shows_reason_line(browser, server_url, no_transcript_post):
    """요약이 없는 카드에 사유 줄이 렌더된다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        card = _open_card_for(page, server_url, no_transcript_post)
        notice = card.locator(NOTICE)

        assert notice.count() > 0, "요약 없음 사유 줄이 카드에 없다"

        text = notice.first.text_content() or ""
        assert "[요약없음]" in text, f"사유 줄 문구가 예상과 다르다: {text}"

        expected_tail = EXPECTED_TEXT.get(no_transcript_post["transcript_status"])
        if expected_tail:
            assert expected_tail in text, (
                f"{no_transcript_post['transcript_status']} 인데 문구가 다르다: {text}"
            )
    finally:
        context.close()


@pytest.mark.e2e
def test_summarized_card_has_no_reason_line(browser, server_url, api_posts):
    """요약이 붙은 카드에는 사유 줄이 없다 - 소음이 되면 안 된다."""
    target = next(
        (p for p in api_posts or [] if p.get("summary_status") == "ok"),
        None,
    )
    if target is None:
        pytest.skip("요약이 붙은 유튜브 글이 없어 판정할 수 없다")

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        card = _open_card_for(page, server_url, target)
        assert card.locator(NOTICE).count() == 0, "요약이 있는데 사유 줄이 떴다"
    finally:
        context.close()


@pytest.mark.e2e
def test_non_youtube_card_never_shows_reason_line(browser, server_url, api_posts):
    """유튜브가 아닌 글에는 이 줄이 붙지 않는다."""
    target = next(
        (p for p in api_posts or [] if str(p.get("sns_platform")) == "linkedin"),
        None,
    )
    if target is None:
        pytest.skip("LinkedIn 글이 없어 판정할 수 없다")

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        card = _open_card_for(page, server_url, target)
        assert card.locator(NOTICE).count() == 0, "유튜브가 아닌 카드에 사유 줄이 떴다"
    finally:
        context.close()
