"""MY 필터(내 게시물만 보기) UI E2E 테스트.

계획: _docs/20260826_03_내-게시물-성과지표-통합-수집-계획.md (5절 V6b·V9~V11)

육안 판정에 의존하지 않는다. 모든 시나리오가 DOM 상태·API 대조로 판정되고,
증거 캡처는 _docs/evidence/20260826_03/ 에 남는다.
브라우저는 headless 로 고정한다 - 창이 뜨면 사용자 포커스를 뺏는다.
"""

import os
import re
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
MY_BTN = "#myPostsBtn"
TOTAL_LABEL = "#totalPostsCount"

VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260826_03"
EVIDENCE_DIR_05 = Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260827_05"

# 상단 라벨은 두 형태뿐이다(계획 _docs/20260827_05 T5·T6).
#   `2487 건`        - 분모를 붙이지 않는다
#   `45편 · 68건`    - MY 가 켜졌을 때. 편은 교차 게시를 한 편으로 친 수
LABEL_PLAIN = re.compile(r"^(\d+)\s*건$")
LABEL_UNIQUE = re.compile(r"^(\d+)\s*편\s*·\s*(\d+)\s*건$")


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


def _capture_05(page, name):
    """계획 20260827_05 의 증거 캡처. 부모 폴더가 없으면 만든다."""
    EVIDENCE_DIR_05.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR_05 / f"{name}.png"), full_page=False)


def _toggle_my(page):
    page.click(MY_BTN)
    page.wait_for_timeout(900)


def _click_filter(page, name):
    page.click(f'button[data-filter="{name}"]')
    page.wait_for_timeout(900)


def _label_text(page):
    return page.locator(TOTAL_LABEL).inner_text().strip()


def _visible_from_label(page):
    """상단 라벨의 보이는 건수. `N 건` 과 `N편 · M건` 을 모두 받는다.

    ⚠️ 카드 개수로 총량을 재지 않는다. 마소너리가 60장씩 지연 로딩하므로
       60을 넘는 결과는 전부 60으로 보인다.
    """
    text = _label_text(page)
    matched = LABEL_UNIQUE.fullmatch(text)
    if matched:
        return int(matched.group(2))
    matched = LABEL_PLAIN.fullmatch(text)
    assert matched, f"상단 라벨 형식을 알 수 없습니다: {text!r}"
    return int(matched.group(1))


def _unique_from_label(page):
    """`N편 · M건` 의 편 수. 그 형태가 아니면 None."""
    matched = LABEL_UNIQUE.fullmatch(_label_text(page))
    return int(matched.group(1)) if matched else None


def _pin_sort_saved(page):
    """정렬을 「로컬수집순」으로 못박는다. 최신순 단언이 이 정렬에서만 성립한다."""
    page.evaluate("() => localStorage.setItem('sns_sort_order', 'saved')")
    page.reload()
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(1200)


def _own_posts(api_posts):
    return [p for p in api_posts if p.get("is_own_post") is True]


def _unique_own_count(api_posts):
    """교차 게시를 한 편으로 친 내 글 수. 뷰어의 countUniqueOwnPosts 와 같은 규칙."""
    groups = {}
    for post in _own_posts(api_posts):
        day = str(post.get("created_at") or "")[:10]
        body = str(post.get("full_text") or post.get("full_text_preview") or "")
        head = re.sub(r"[^가-힣A-Za-z0-9]", "", body)[:40]
        platform = str(post.get("sns_platform") or "").lower()
        by_platform = groups.setdefault(f"{day}|{head}", {})
        by_platform[platform] = by_platform.get(platform, 0) + 1
    return sum(max(by_platform.values()) for by_platform in groups.values())


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
    """
    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"

    own_total = len(_own_posts(api_posts))
    visible = _visible_from_label(viewer)

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


def test_platform_chip_releases_my_filter(viewer, api_posts):
    """플랫폼 칩을 누르면 MY 가 저절로 풀린다.

    이걸 안 하면 MY 가 켜진 채로 X·YouTube 를 눌러 0건이 뜬다 - 그것도 MY 가 켜졌다는
    표시 없이. 세 가지 이상 현상이 전부 여기서 나왔다.
    계획: _docs/20260827_05 (T2)
    """
    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"

    _click_filter(viewer, "threads")
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false", (
        "Threads 를 눌렀는데 MY 가 켜진 채로 남았습니다."
    )

    threads_total = len([
        p for p in api_posts if str(p.get("sns_platform") or "").lower() == "threads"
    ])
    own_threads = len([p for p in _own_posts(api_posts) if p.get("sns_platform") == "threads"])
    visible = _visible_from_label(viewer)
    assert visible > own_threads, (
        f"Threads 탭이 {visible}건뿐입니다. 내 글 {own_threads}건만 남은 것으로 보입니다."
    )
    assert visible <= threads_total

    _capture_05(viewer, "platform_chip_releases_my")


# --- V10: 상태 영속 --------------------------------------------------------


def test_my_filter_resets_on_reload(viewer):
    """새로고침하면 MY 가 꺼져 있어야 한다.

    저장하던 시절에는 한 번 켜면 브라우저를 껐다 켜도 켜진 채로 남았고, 켜졌다는
    표시가 화면에 없어 사용자가 빠져나올 방법이 없었다. 저장을 없앤 것이 이 그물이다.
    계획: _docs/20260827_05 (T3)
    """
    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"

    viewer.reload()
    viewer.wait_for_selector(CARD, timeout=20000)
    viewer.wait_for_timeout(1200)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false", (
        "새로고침 후에도 MY 가 켜져 있습니다. 상태가 아직 저장되고 있습니다."
    )
    assert viewer.evaluate("() => localStorage.getItem('sns_own_posts_only')") is None, (
        "sns_own_posts_only 가 localStorage 에 남아 있습니다."
    )
    _capture_05(viewer, "my_resets_on_reload")


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


def test_my_filter_includes_threads_own_posts(viewer, api_posts):
    """MY 화면에 내 Threads 글이 실제로 담긴다.

    ⚠️ 플랫폼 칩을 함께 누르지 않는다. 칩을 누르면 MY 가 풀리기 때문이다(T2).
       MY 는 두 플랫폼을 함께 보여주므로 화면에 Threads 카드가 섞여 있는지로 판정한다.
    """
    _toggle_my(viewer)

    own_threads = len([
        p for p in _own_posts(api_posts) if p.get("sns_platform") == "threads"
    ])
    assert own_threads > 0, "내 Threads 글이 API 응답에 없습니다."

    platforms = viewer.evaluate(
        """() => [...document.querySelectorAll('#masonryGrid article.glass-card')]
                 .map(a => a.getAttribute('data-platform'))"""
    )
    assert "threads" in platforms, "MY 화면에 Threads 카드가 하나도 없습니다."
    assert set(platforms) <= {"threads", "linkedin"}, (
        f"MY 화면에 내 글이 없는 플랫폼이 섞였습니다: {sorted(set(platforms))}"
    )
    _capture_threads_own(viewer, "v10_my_filter_threads")


def test_saved_threads_posts_excluded_from_my_filter(viewer, api_posts):
    """저장글(남의 글)은 MY 필터에 절대 나오면 안 된다.

    ⚠️ 플랫폼 칩을 함께 누르지 않는다 - 누르면 MY 가 풀린다(T2). 상단 라벨의
       건수가 내 글 총수와 정확히 같은지로 판정한다.
    """
    own_total = len(_own_posts(api_posts))
    total_threads = len([
        p for p in api_posts if str(p.get("sns_platform") or "").lower() == "threads"
    ])
    own_threads = len([p for p in _own_posts(api_posts) if p.get("sns_platform") == "threads"])
    assert total_threads > own_threads, "저장글이 없으면 이 테스트가 무의미합니다."

    _toggle_my(viewer)
    assert _visible_from_label(viewer) == own_total, (
        "MY 화면 건수가 내 글 총수와 다릅니다. 저장글이 섞였을 수 있습니다."
    )
    _capture_threads_own(viewer, "v10_saved_posts_excluded")


# --- 내 글 숨기기 토글 · MY 버튼 정리 (계획 _docs/20260827_03 V7~V12) --------

EVIDENCE_DIR_HIDE_OWN = (
    Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260827_03"
)

HIDE_OWN_TOGGLE = "#hideOwnPostsToggle"


def _capture_hide_own(page, name):
    EVIDENCE_DIR_HIDE_OWN.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR_HIDE_OWN / f"{name}.png"), full_page=False)


def _open_display_tab(page):
    """설정 모달의 「표시」 탭을 연다. 셀렉터는 아이디로 고정한다."""
    page.click("#settingsBtn")
    page.wait_for_timeout(500)
    page.click('.tab-btn[data-target="tabDisplay"]')
    page.wait_for_timeout(300)


def _close_settings(page):
    page.click("#closeManagementModal")
    page.wait_for_timeout(500)


# V7 - MY 버튼에서 아이콘을 뺀다
def test_my_button_has_no_icon(viewer):
    button = viewer.locator(MY_BTN)
    assert button.count() == 1
    assert button.locator(".material-symbols-outlined").count() == 0, (
        "MY 버튼에 아이콘 span 이 남아 있습니다."
    )
    assert button.inner_text().strip() == "MY"
    _capture_hide_own(viewer, "v7_my_button_text_only")


# V8 - 숨김 토글 기본 켜짐. 목록에서 내 글이 빠진다
def test_hide_own_toggle_removes_own_posts(viewer, api_posts):
    """기본 상태(All)의 건수에 내 글이 섞이지 않는다.

    ⚠️ 분모로 판정하지 않는다. 상단 라벨에서 분모를 뺐다(계획 20260827_05 T5).
       사용자가 숨긴 글이 있으면 보이는 수가 타인 글 총수보다 작으므로 `<=` 로 본다.
    """
    not_own = len([p for p in api_posts if p.get("is_own_post") is not True])

    visible = _visible_from_label(viewer)
    assert 0 < visible <= not_own, (
        f"기본 상태 건수 {visible}이 타인 글 총수 {not_own}을 넘습니다. 내 글이 섞였습니다."
    )
    assert _unique_from_label(viewer) is None, (
        "MY 가 꺼진 상태인데 라벨이 `N편 · M건` 형태입니다."
    )

    _open_display_tab(viewer)
    assert viewer.locator(HIDE_OWN_TOGGLE).is_checked(), "숨김 토글 기본값이 꺼져 있습니다."
    _capture_hide_own(viewer, "v8_display_tab_default_on")
    _close_settings(viewer)


# V8b - 토글을 끄면 내 글이 다시 들어온다
def test_hide_own_toggle_off_restores_own_posts(viewer, api_posts):
    """토글을 끄면 보이는 건수가 정확히 내 글 수만큼 늘어난다.

    숨겨진 내 글은 실측 0건이므로 증가분이 내 글 총수와 정확히 같아야 한다.
    """
    own_total = len(_own_posts(api_posts))
    before = _visible_from_label(viewer)

    _open_display_tab(viewer)
    viewer.uncheck(HIDE_OWN_TOGGLE)
    viewer.wait_for_timeout(900)
    _close_settings(viewer)

    after = _visible_from_label(viewer)
    assert after - before == own_total, (
        f"토글을 껐는데 건수가 {before} → {after} 로 {after - before}건만 늘었습니다. "
        f"내 글은 {own_total}건입니다."
    )


# V9 - MY 버튼이 숨김 토글보다 우선한다
def test_hide_own_toggle_yields_to_my_button(viewer, api_posts):
    own_total = len(_own_posts(api_posts))

    _toggle_my(viewer)
    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"
    assert _visible_from_label(viewer) == own_total, (
        "숨김 토글이 켜진 상태에서 MY 를 눌렀는데 내 글이 다 나오지 않습니다."
    )
    _capture_hide_own(viewer, "v9_my_button_wins")


# V10 - 토글 상태가 새로고침을 넘어간다
def test_hide_own_toggle_persists_across_reload(viewer):
    _open_display_tab(viewer)
    viewer.uncheck(HIDE_OWN_TOGGLE)
    viewer.wait_for_timeout(600)
    _close_settings(viewer)

    viewer.reload()
    viewer.wait_for_selector(CARD, timeout=20000)
    viewer.wait_for_timeout(1200)

    _open_display_tab(viewer)
    assert not viewer.locator(HIDE_OWN_TOGGLE).is_checked(), (
        "새로고침 후 숨김 토글이 되살아났습니다. localStorage 저장이 동작하지 않습니다."
    )
    _capture_hide_own(viewer, "v10_toggle_persisted_off")


# V11 - 라벨에 분모를 붙이지 않는다 (계획 20260827_05 T5)
def test_total_label_has_no_denominator(viewer):
    """분모를 뺐다. 플랫폼별 수집 건수를 단순 합산한 값이라 정확하지 않았다."""
    plain = _label_text(viewer)
    assert "/" not in plain, f"라벨에 분모가 남아 있습니다: {plain!r}"
    assert LABEL_PLAIN.fullmatch(plain), f"라벨이 `N 건` 형태가 아닙니다: {plain!r}"

    _toggle_my(viewer)
    my_label = _label_text(viewer)
    assert "/" not in my_label, f"MY 라벨에 분모가 남아 있습니다: {my_label!r}"
    assert LABEL_PLAIN.fullmatch(my_label) or LABEL_UNIQUE.fullmatch(my_label), (
        f"MY 라벨이 `N 건` 도 `N편 · M건` 도 아닙니다: {my_label!r}"
    )


# V12 - 내 글이 최신순으로 보인다 (계획 20260827_03·04 의 화면 반영 확인)
def test_my_tab_newest_first(viewer, api_posts):
    """「로컬수집순」에서 MY 화면 첫 카드가 내 글 전체의 최신 글이어야 한다.

    수집기가 최신 글부터 훑어 crawled_at 과 sequence_id 양쪽에 역순을 새기는 문제를
    total_scrap 의 정렬 키가 바로잡았는지, 그리고 계획 04 의 두 플랫폼 병합이
    화면에 실제로 반영됐는지 판정한다. 이 그물이 사라지면 정렬이 틀어져도 모른다.

    ⚠️ 플랫폼 칩을 함께 누르지 않는다 - 누르면 MY 가 풀린다(계획 05 T2).
       계획 04 가 두 플랫폼을 날짜순으로 섞어 놓아 플랫폼 고정 없이도 성립한다.
    ⚠️ 본문만으로 단언하지 않는다. 내 글 최신 2건은 같은 글을 두 플랫폼에 올린 것이라
       본문이 사실상 같다. 잘못된 카드가 위에 있어도 본문 대조는 통과해 버린다.
       카드의 data-platform 을 함께 본다.
    계획: _docs/20260827_05 (4.2)
    """
    own = _own_posts(api_posts)
    assert own, "내 글이 API 응답에 없습니다."
    newest = max(own, key=lambda p: str(p.get("created_at") or ""))

    _pin_sort_saved(viewer)
    _toggle_my(viewer)

    first = viewer.locator(CARD).first
    assert first.get_attribute("data-platform") == newest.get("sns_platform"), (
        f"MY 맨 위 카드의 플랫폼이 {first.get_attribute('data-platform')!r} 인데 "
        f"최신 내 글은 {newest.get('sns_platform')!r} 입니다. 정렬이 뒤집혔습니다."
    )

    head = str(newest.get("full_text_preview") or newest.get("full_text") or "").strip()[:20]
    assert head, "최신 내 글의 본문이 비어 있습니다."
    assert head in first.inner_text(), (
        f"MY 맨 위 카드가 최신 글이 아닙니다. 기대 본문 앞부분: {head!r}"
    )
    _capture_05(viewer, "my_newest_first")


# --- 계획 20260827_05 신설 -------------------------------------------------


def test_my_button_shows_active_state(viewer):
    """MY 가 켜지면 화면에서 보여야 한다.

    이게 이번 결함의 근본 원인이었다. `.active` 를 스타일링하는 규칙이
    `.filter-chip.active` 뿐인데 MY 버튼에 그 클래스가 없어서, 켠 상태와 끈 상태가
    픽셀 단위로 같았다. 그래서 X 를 눌러 0건이 떠도 이유를 알 수 없었다.
    계획: _docs/20260827_05 (T1)
    """
    def background():
        return viewer.evaluate(
            "() => getComputedStyle(document.getElementById('myPostsBtn')).backgroundColor"
        )

    off = background()
    _capture_05(viewer, "my_off")

    _toggle_my(viewer)
    on = background()
    _capture_05(viewer, "my_on")

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true"
    assert on != off, (
        f"MY 를 켰는데 배경색이 그대로입니다({off}). 켜진 것을 화면에서 알 수 없습니다."
    )
    assert viewer.locator(f"{MY_BTN}.active").count() == 1, "MY 버튼에 active 가 안 붙었습니다."


def test_my_label_counts_unique_posts(viewer, api_posts):
    """MY 라벨이 교차 게시를 한 편으로 쳐서 보여준다.

    같은 글을 LinkedIn·Threads 양쪽에 올리면 2건으로 세어져 "내가 몇 편 썼나"를
    알 수 없었다. 카드는 합치지 않는다 - 플랫폼별 조회수·좋아요가 달라서다.
    계획: _docs/20260827_05 (T6)
    """
    own_total = len(_own_posts(api_posts))
    unique_total = _unique_own_count(api_posts)
    assert unique_total < own_total, (
        "교차 게시가 하나도 없으면 이 테스트가 무의미합니다."
    )

    _toggle_my(viewer)

    assert _visible_from_label(viewer) == own_total
    assert _unique_from_label(viewer) == unique_total, (
        f"MY 라벨의 편 수가 {_unique_from_label(viewer)} 인데 "
        f"API 기준 중복 제외 수는 {unique_total} 입니다. 라벨: {_label_text(viewer)!r}"
    )
    _capture_05(viewer, "my_label_unique_count")


def test_viewer_scenario_after_fix(viewer, api_posts):
    """사용자가 보고한 조작 순서를 그대로 재현해 전부 정상인지 판정한다.

    수정 전 실측(계획 20260827_05 2.3 절):
      MY 켬 → X 클릭 = 0건 / YouTube 클릭 = 0건 / Threads 클릭 = 내 글 32건만 /
      All 클릭 = 내 글 68건만. 게다가 그 상태가 영구 저장됐다.
    수정 후에는 MY 가 플랫폼 클릭 시 풀리므로 모든 단계가 정상이어야 한다.
    계획: _docs/20260827_05 (4.4 완료 기준 2)
    """
    def platform_total(name):
        keys = {"x", "twitter"} if name == "x" else {name}
        return len([
            p for p in api_posts if str(p.get("sns_platform") or "").lower() in keys
        ])

    _toggle_my(viewer)
    assert _visible_from_label(viewer) == len(_own_posts(api_posts))
    _capture_05(viewer, "scenario_1_my_on")

    for step, name in enumerate(["x", "youtube", "threads", "all"], start=2):
        _click_filter(viewer, name)
        visible = _visible_from_label(viewer)

        assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false", (
            f"{name} 을 눌렀는데 MY 가 켜진 채로 남았습니다."
        )
        assert visible > 0, f"{name} 탭이 0건입니다. 수정 전 증상이 그대로입니다."
        if name != "all":
            assert visible <= platform_total(name), (
                f"{name} 탭 건수 {visible}이 그 플랫폼 총수를 넘습니다."
            )
        _capture_05(viewer, f"scenario_{step}_{name}")


# --- 20260828_01: MY 를 켤 때 조건별 단계 완화 --------------------------------
#
# 선행 계획 20260827_05 는 「플랫폼 칩 → MY 해제」한 방향만 넣었다. 반대 방향
# (플랫폼을 고른 뒤 MY 를 켜는 것)은 그대로 두어, 내 글이 0건인 플랫폼·태그·작성자에서
# 조용히 빈 화면이 됐다. 사용자 보고: 「유튜브 선택 상태에서 MY 를 누르면 하나도 안 나온다」.
#
# 이제 MY 를 켤 때 내 글이 나올 때까지 조건을 하나씩 푼다(작성자 → 태그 → 플랫폼).
# 계획: _docs/20260828_01_뷰어-MY필터-조건별-단계완화-계획.md

EVIDENCE_DIR_20260828_01 = (
    Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260828_01"
)

PLATFORM_CHIPS = ["all", "favorites", "linkedin", "threads", "x", "youtube"]


def _capture_20260828_01(page, name):
    """계획 20260828_01 의 증거 캡처. headless 브라우저가 직접 찍는다."""
    EVIDENCE_DIR_20260828_01.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR_20260828_01 / f"{name}.png"), full_page=False)


def _active_platform(page):
    """켜져 있는 플랫폼 칩의 data-filter. MY 는 플랫폼이 아니므로 제외한다."""
    return page.evaluate(
        """() => {
            const chip = [...document.querySelectorAll('.filter-chip.active')]
                .find((b) => b.id !== 'myPostsBtn');
            return chip ? chip.dataset.filter : null;
        }"""
    )


def _click_tag(page, name):
    page.evaluate(
        """(name) => {
            const chip = [...document.querySelectorAll('.global-tag-chip')]
                .find((t) => t.textContent.trim() === name);
            if (!chip) throw new Error(`태그 칩을 찾을 수 없습니다: ${name}`);
            chip.click();
        }""",
        name,
    )
    page.wait_for_timeout(900)


def _active_tag(page):
    return page.evaluate(
        """() => {
            const chip = document.querySelector('.global-tag-chip.active');
            return chip ? chip.textContent.trim() : null;
        }"""
    )


def _own_count_for_platform(api_posts, platform):
    keys = {"x", "twitter"} if platform == "x" else {platform}
    return len([
        p for p in _own_posts(api_posts)
        if str(p.get("sns_platform") or "").lower() in keys
    ])


def _tag_with_own_posts(page):
    """내 글이 1건 이상 붙은 태그 이름. 없으면 테스트를 건너뛴다."""
    return page.evaluate(
        """() => {
            const names = [...document.querySelectorAll('.global-tag-chip')]
                .map((t) => t.textContent.trim());
            return names;
        }"""
    )


# N1: 내 글이 있는 플랫폼은 유지된다
def test_my_keeps_platform_with_own_posts(viewer, api_posts):
    """LinkedIn 은 내 글이 있으므로 MY 를 켜도 칩이 살아남는다.

    이게 이번 변경으로 얻는 것이다. 예전에는 `LinkedIn → MY` 는 되고
    `MY → LinkedIn` 은 MY 가 풀려, 같은 두 버튼이 순서로 갈렸다.
    """
    own_linkedin = _own_count_for_platform(api_posts, "linkedin")
    assert own_linkedin > 0, "LinkedIn 내 글이 없어 이 테스트가 성립하지 않습니다."

    _click_filter(viewer, "linkedin")
    _toggle_my(viewer)

    assert _active_platform(viewer) == "linkedin", (
        "LinkedIn 은 내 글이 있으므로 MY 를 켜도 유지돼야 합니다."
    )
    assert _visible_from_label(viewer) == own_linkedin
    _capture_20260828_01(viewer, "n1_linkedin_kept")


# N2: 내 글이 없는 플랫폼은 풀린다 (사용자 보고 건)
def test_my_releases_platform_without_own_posts(viewer, api_posts):
    """YouTube 는 내 글이 0건이므로 MY 를 켜면 All 로 풀린다.

    사용자가 보고한 「유튜브 선택 상태에서 MY 를 누르면 하나도 안 나온다」가 이것이다.
    """
    assert _own_count_for_platform(api_posts, "youtube") == 0, (
        "YouTube 내 글이 생겼습니다. 이 테스트의 전제가 바뀌었습니다."
    )

    _click_filter(viewer, "youtube")
    _toggle_my(viewer)

    assert _active_platform(viewer) == "all", (
        "YouTube 는 내 글이 0건이므로 MY 를 켜면 All 로 풀려야 합니다."
    )
    visible = _visible_from_label(viewer)
    assert visible > 0, "수정 전 증상(0건)이 그대로입니다."
    assert visible == len(_own_posts(api_posts))
    _capture_20260828_01(viewer, "n2_youtube_released")


# N3: 내 글이 있는 태그는 유지된다
def test_my_keeps_tag_with_own_posts(viewer):
    _click_tag(viewer, "클로드")
    before = _visible_from_label(viewer)
    _toggle_my(viewer)

    assert _active_tag(viewer) == "클로드", (
        "내 글이 있는 태그는 MY 를 켜도 유지돼야 합니다."
    )
    visible = _visible_from_label(viewer)
    assert 0 < visible < before
    _capture_20260828_01(viewer, "n3_tag_kept")


# N4: 내 글이 없는 태그는 풀린다
def test_my_releases_tag_without_own_posts(viewer, api_posts):
    _click_tag(viewer, "하네스")
    _toggle_my(viewer)

    assert _active_tag(viewer) is None, (
        "내 글이 0건인 태그는 MY 를 켜면 풀려야 합니다."
    )
    assert _visible_from_label(viewer) == len(_own_posts(api_posts))
    _capture_20260828_01(viewer, "n4_tag_released")


# N6: 빈 화면 안내판이 걸린 조건을 이름으로 말한다
def test_empty_state_names_active_filters(viewer):
    """검색어는 자동 해제 대상이 아니므로 0건이 남을 수 있다. 그때 이유를 말해야 한다.

    ⚠️ 플랫폼은 반드시 LinkedIn 이어야 한다. YouTube 는 내 글이 0건이라 완화가
       플랫폼까지 풀어버려 안내판에 이름이 남지 않는다(계획 게이트 2차 검수 지적).
    """
    _click_filter(viewer, "linkedin")
    viewer.fill("#searchInput", "카드뉴스")
    viewer.wait_for_timeout(2500)
    _toggle_my(viewer)
    viewer.wait_for_timeout(1500)

    assert _visible_from_label(viewer) == 0, "이 조합은 0건이어야 테스트가 성립합니다."
    text = viewer.locator("#noResultsText").inner_text()
    assert "LinkedIn" in text, f"안내판에 플랫폼 이름이 없습니다: {text!r}"
    assert "MY" in text, f"안내판에 MY 가 없습니다: {text!r}"
    assert "카드뉴스" in text, f"안내판에 검색어가 없습니다: {text!r}"
    _capture_20260828_01(viewer, "n6_empty_state_names_filters")


# S1: 어떤 플랫폼 칩에서 MY 를 켜도 0건이 되지 않는다
def test_my_never_yields_empty_from_platform_chip(viewer, api_posts):
    """2.2 표의 6개 칩을 전부 순회한다. 이게 사용자 보고를 막는 그물이다."""
    own_total = len(_own_posts(api_posts))

    for chip in PLATFORM_CHIPS:
        if viewer.locator(MY_BTN).get_attribute("aria-pressed") == "true":
            _toggle_my(viewer)
        _click_filter(viewer, chip)
        _toggle_my(viewer)

        visible = _visible_from_label(viewer)
        assert visible > 0, f"{chip} 칩에서 MY 를 켰더니 0건입니다."
        assert visible <= own_total, (
            f"{chip} + MY 가 {visible}건으로 내 글 전체({own_total})를 넘습니다."
        )
        _capture_20260828_01(viewer, f"s1_{chip}")


# S2: MY 를 끄면 아무 조건도 바뀌지 않는다
def test_my_off_changes_nothing(viewer, api_posts):
    """완화는 켤 때만 일어난다. 끌 때 조건을 건드리면 사용자가 자리를 잃는다."""
    _click_filter(viewer, "linkedin")
    _toggle_my(viewer)
    assert _active_platform(viewer) == "linkedin"

    _toggle_my(viewer)

    assert viewer.locator(MY_BTN).get_attribute("aria-pressed") == "false"
    assert _active_platform(viewer) == "linkedin", (
        "MY 를 껐더니 플랫폼 선택까지 바뀌었습니다."
    )
    linkedin_total = len([
        p for p in api_posts if str(p.get("sns_platform") or "").lower() == "linkedin"
    ])
    assert _visible_from_label(viewer) <= linkedin_total
    _capture_20260828_01(viewer, "s2_my_off_keeps_platform")
