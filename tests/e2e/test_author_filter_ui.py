"""저자 필터 UI E2E 테스트.

카드 헤더의 저자 이름 클릭 → 해당 플랫폼의 해당 저자 글만 필터링되는 동작과,
그 과정에서 함께 고친 버튼 밀림 결함을 assertion 으로 검증한다.

육안 판정에 의존하지 않도록 모든 시나리오가 DOM 상태·좌표 비교로 판정된다.
브라우저는 headless 로 뜬다 (playwright 기본값).
"""

import os

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
BADGE = "#globalTagsContainer .author-filter-badge"

# 이 테스트는 뷰어 서버가 이미 떠 있는 상태를 전제한다.
# 자체 서버를 띄우지 않는 이유: playwright 와 flask 가 서로 다른 인터프리터에 설치돼 있어
# 한 프로세스에서 둘을 함께 import 할 수 없다.
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")


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
def browser():
    """pytest-playwright 플러그인에 의존하지 않고 직접 브라우저를 띄운다.

    headless=True 로 고정한다. 창이 뜨면 사용자 포커스를 뺏는다.
    """
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def viewer(browser, server_url):
    """4열 레이아웃이 잡히도록 뷰포트를 넓힌 뒤 카드 로드를 기다린다."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(1200)
    yield page
    context.close()


def _card_count(page):
    return page.locator(CARD).count()


def _author_of(page, index=0):
    """index 번째 카드의 username / display_name 을 API 대조로 얻는다."""
    return page.evaluate(
        """async (idx) => {
            const res = await fetch('/api/posts');
            const data = await res.json();
            const posts = data.posts || data;
            const byUrl = new Map();
            posts.forEach(p => {
                if (p.canonical_url) byUrl.set(p.canonical_url, p);
                if (p.url) byUrl.set(p.url, p);
            });
            const cards = [...document.querySelectorAll('#masonryGrid article.glass-card')];
            const card = cards[idx];
            if (!card) return null;
            const url = card.querySelector('[data-url]')?.dataset.url;
            const post = byUrl.get(url);
            if (!post) return null;
            return {
                username: post.username,
                displayName: post.display_name,
                platform: post.sns_platform,
                shown: card.querySelector('h3')?.textContent?.trim(),
            };
        }""",
        index,
    )


def _find_clickable_author(page, platform=None, exclude_usernames=()):
    """클릭 대상으로 쓸 카드 인덱스를 고른다.

    kana_option(X 수집 오염 계정)처럼 결과가 왜곡되는 계정은 제외한다.
    """
    for idx in range(min(_card_count(page), 40)):
        info = _author_of(page, idx)
        if not info or not info.get("username"):
            continue
        if info["username"] in exclude_usernames:
            continue
        if platform and str(info.get("platform", "")).lower() != platform:
            continue
        return idx, info
    return None, None


# X 수집 오염 계정 - 13명의 글이 한 username 에 뭉쳐 있어 필터 검증에 부적합
EXCLUDED = ("kana_option",)


@pytest.mark.e2e
def test_author_click_filters_to_single_author(viewer):
    """1. 저자명 클릭 시 그 저자의 글만 남는다."""
    before = _card_count(viewer)
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info, "클릭 가능한 저자 카드를 찾지 못했습니다."

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)

    after = _card_count(viewer)
    assert after > 0, "필터 결과가 0건입니다."
    assert after <= before, "필터 후 카드가 늘어났습니다."

    usernames = viewer.evaluate(
        """async () => {
            const res = await fetch('/api/posts');
            const data = await res.json();
            const posts = data.posts || data;
            const byUrl = new Map();
            posts.forEach(p => {
                if (p.canonical_url) byUrl.set(p.canonical_url, p);
                if (p.url) byUrl.set(p.url, p);
            });
            return [...document.querySelectorAll('#masonryGrid article.glass-card')]
                .map(c => byUrl.get(c.querySelector('[data-url]')?.dataset.url))
                .filter(Boolean)
                .map(p => `${p.sns_platform}:${p.username}`);
        }"""
    )
    assert len(set(usernames)) == 1, f"여러 저자가 섞여 있습니다: {set(usernames)}"


@pytest.mark.e2e
def test_badge_appears_and_hides_internal_id(viewer):
    """2. 배지가 뜨고, LinkedIn 내부 ID가 노출되지 않는다."""
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)

    badge = viewer.locator(BADGE)
    assert badge.count() == 1, "저자 배지가 렌더되지 않았습니다."
    text = badge.inner_text()
    assert "ACoAAA" not in text, f"LinkedIn 내부 ID가 배지에 노출되었습니다: {text}"


@pytest.mark.e2e
def test_toggle_off_by_reclick(viewer):
    """4. 같은 이름 재클릭 시 전체 목록으로 복귀한다."""
    before = _card_count(viewer)
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    link = viewer.locator(f"{CARD} h3.author-link").nth(idx)
    link.click()
    viewer.wait_for_timeout(700)
    filtered = _card_count(viewer)
    assert filtered <= before

    viewer.locator(f"{CARD} h3.author-link").first.click()
    viewer.wait_for_timeout(700)
    assert _card_count(viewer) == before, "재클릭 후 원래 목록으로 돌아오지 않았습니다."
    assert viewer.locator(BADGE).count() == 0, "해제 후에도 배지가 남아 있습니다."


@pytest.mark.e2e
def test_badge_click_clears_filter(viewer):
    """5. 배지를 누르면 필터가 해제된다."""
    before = _card_count(viewer)
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)
    assert viewer.locator(BADGE).count() == 1

    viewer.locator(BADGE).click()
    viewer.wait_for_timeout(700)
    assert _card_count(viewer) == before
    assert viewer.locator(BADGE).count() == 0


@pytest.mark.e2e
def test_platform_chip_switch_keeps_badge(viewer):
    """7. 다른 플랫폼 칩으로 바꿔도 배지가 남아 해제할 수 있다."""
    idx, info = _find_clickable_author(viewer, platform="threads", exclude_usernames=EXCLUDED)
    if not info:
        pytest.skip("Threads 카드를 찾지 못했습니다.")

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)

    viewer.locator("#filterContainer .filter-chip[data-filter='linkedin']").click()
    viewer.wait_for_timeout(700)

    assert _card_count(viewer) == 0, "Threads 저자 필터 상태에서 LinkedIn 결과가 나왔습니다."
    assert viewer.locator(BADGE).count() == 1, "결과 0건 상태에서 배지가 사라져 해제할 수 없습니다."


@pytest.mark.e2e
def test_click_does_not_open_detail(viewer):
    """8. 이름 클릭이 카드 상세를 열지 않는다 (stopPropagation)."""
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    modal_before = viewer.locator("#imageModal:not(.hidden)").count()
    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)
    assert viewer.locator("#imageModal:not(.hidden)").count() == modal_before


@pytest.mark.e2e
def test_keyboard_enter_applies_filter(viewer):
    """11. Enter 로 필터가 적용되고, Space 가 페이지를 스크롤하지 않는다."""
    before = _card_count(viewer)
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    link = viewer.locator(f"{CARD} h3.author-link").nth(idx)
    link.focus()
    scroll_before = viewer.evaluate("() => window.scrollY")
    link.press(" ")
    viewer.wait_for_timeout(700)
    assert viewer.evaluate("() => window.scrollY") == scroll_before, \
        "Space 키가 페이지를 스크롤했습니다 (preventDefault 누락)."

    # Space 로 이미 필터가 걸렸으므로 해제 후 Enter 로 재확인
    if viewer.locator(BADGE).count():
        viewer.locator(BADGE).click()
        viewer.wait_for_timeout(500)

    viewer.locator(f"{CARD} h3.author-link").nth(idx).focus()
    viewer.locator(f"{CARD} h3.author-link").nth(idx).press("Enter")
    viewer.wait_for_timeout(700)
    assert _card_count(viewer) <= before
    assert viewer.locator(BADGE).count() == 1


@pytest.mark.e2e
def test_buttons_stay_inside_card(viewer):
    """10. 이름이 길어도 우측 버튼이 카드 밖으로 밀려나지 않는다."""
    overflows = viewer.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('#masonryGrid article.glass-card').forEach(card => {
                const h3 = card.querySelector('h3');
                if (!h3) return;
                const header = h3.closest('.justify-between');
                if (!header) return;
                const btns = header.lastElementChild;
                const cr = card.getBoundingClientRect();
                const br = btns.getBoundingClientRect();
                const overflow = br.right - (cr.right - 16);
                if (overflow > 1) {
                    out.push({ name: h3.textContent.trim().slice(0, 30), overflow: Math.round(overflow) });
                }
            });
            return out;
        }"""
    )
    assert overflows == [], f"버튼이 카드 밖으로 밀려난 카드가 있습니다: {overflows}"


@pytest.mark.e2e
def test_author_badge_renders_without_tags(viewer):
    """9. 태그 칩이 없는 상태에서도 배지가 렌더된다 (조기 반환 회귀)."""
    viewer.evaluate(
        """() => {
            const c = document.getElementById('globalTagsContainer');
            if (c) c.innerHTML = '';
        }"""
    )
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)
    assert viewer.locator(BADGE).count() == 1, \
        "태그가 없을 때 배지가 렌더되지 않았습니다 (updateGlobalTags 조기 반환)."


@pytest.mark.e2e
def test_display_name_policy_no_internal_id_anywhere(viewer):
    """저자명 표시 정책: 카드 어디에도 LinkedIn 내부 ID가 노출되지 않는다."""
    names = viewer.evaluate(
        """() => [...document.querySelectorAll('#masonryGrid article.glass-card h3')]
                  .map(h => h.textContent.trim())"""
    )
    leaked = [n for n in names if n.startswith("ACoAA")]
    assert leaked == [], f"내부 ID가 카드에 표시되었습니다: {leaked}"


def _find_username_with_multiple_display_names(page, platform="threads"):
    """같은 username인데 display_name 표기가 갈리는 저자를 API에서 찾는다.

    Threads 백필 이후에도 일부 저자는 아이디 표기 카드와 실명 표기 카드가
    섞여 있다(예: keke_appa -> 'keke' / '케케아빠'). 시나리오 3 검증용.
    """
    return page.evaluate(
        """async (platform) => {
            const res = await fetch('/api/posts');
            const data = await res.json();
            const posts = (data.posts || data).filter(
                p => (p.sns_platform || '').toLowerCase() === platform
            );
            const byUser = new Map();
            posts.forEach(p => {
                if (!p.username) return;
                if (!byUser.has(p.username)) byUser.set(p.username, new Set());
                byUser.get(p.username).add(p.display_name);
            });
            for (const [username, names] of byUser) {
                if (names.size > 1) {
                    return { username, names: [...names] };
                }
            }
            return null;
        }""",
        platform,
    )


def _card_for_username(page, username):
    """해당 저자의 카드를 data-url 로 특정한다.

    인덱스로 훑으면 초기 렌더 60건(무한스크롤) 안에 없는 저자를 못 찾는다 -
    실제로 그 이유로 이 테스트가 깨져 있었다.
    """
    urls = page.evaluate(
        """async (username) => {
            const res = await fetch('/api/posts');
            const data = await res.json();
            return (data.posts || data)
                .filter(p => p.username === username)
                .map(p => p.canonical_url || p.url)
                .filter(Boolean);
        }""",
        username,
    )
    cards = page.locator(CARD)
    for i in range(cards.count()):
        holder = cards.nth(i).locator("[data-url]")
        if holder.count() and holder.first.get_attribute("data-url") in urls:
            return i
    return None


@pytest.mark.e2e
def test_author_click_groups_across_display_name_variants(viewer):
    """3. Threads 저자 표시명이 카드마다 달라도 같은 username 이면 한 묶음이다."""
    target = _find_username_with_multiple_display_names(viewer, "threads")
    if not target:
        pytest.skip("display_name 이 갈리는 Threads 저자를 찾지 못했습니다.")

    # 대상 저자가 초기 렌더 범위 밖일 수 있으므로 검색으로 먼저 화면에 올린다.
    # username 으로 검색하면 _searchable 이 username 을 포함해 그 저자 글이 전부 나온다.
    viewer.locator("#searchInput").fill(target["username"])
    viewer.wait_for_timeout(1200)

    idx = _card_for_username(viewer, target["username"])
    assert idx is not None, f"{target['username']} 카드를 검색 후에도 찾지 못했습니다."

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)

    # 검색어를 지운다. 남겨두면 저자 필터가 무력화되는 회귀를 검색 결과가 가린다 -
    # 아래 단정이 저자 필터 단독으로 판정되도록 만든다.
    viewer.locator("#searchInput").fill("")
    viewer.wait_for_timeout(1200)

    shown_names = viewer.evaluate(
        """async (username) => {
            const res = await fetch('/api/posts');
            const data = await res.json();
            const posts = data.posts || data;
            const byUrl = new Map();
            posts.forEach(p => {
                if (p.canonical_url) byUrl.set(p.canonical_url, p);
                if (p.url) byUrl.set(p.url, p);
            });
            return [...document.querySelectorAll('#masonryGrid article.glass-card')]
                .map(c => byUrl.get(c.querySelector('[data-url]')?.dataset.url))
                .filter(p => p && p.username === username)
                .map(p => p.display_name);
        }""",
        target["username"],
    )
    assert set(shown_names) == set(target["names"]), (
        f"표시명이 갈리는 카드가 한 묶음으로 필터링되지 않았습니다. "
        f"기대: {target['names']}, 실제: {shown_names}"
    )


@pytest.mark.e2e
def test_author_filter_combines_with_tag_filter(viewer):
    """6. 저자 필터와 태그 필터가 AND 로 결합된다."""
    idx, info = _find_clickable_author(viewer, exclude_usernames=EXCLUDED)
    assert info

    viewer.locator(f"{CARD} h3.author-link").nth(idx).click()
    viewer.wait_for_timeout(700)
    after_author = _card_count(viewer)
    if after_author == 0:
        pytest.skip("저자 필터 결과가 0건이라 태그 결합을 검증할 수 없습니다.")

    tag_chip = viewer.locator("#globalTagsContainer .global-tag-chip").first
    if tag_chip.count() == 0:
        pytest.skip("사용 가능한 태그 칩이 없습니다.")

    tag_chip.click()
    viewer.wait_for_timeout(700)
    after_both = _card_count(viewer)

    assert after_both <= after_author, "태그 필터 추가 후 결과가 늘어났습니다 (AND 결합 실패)."

    # 배지가 여전히 남아 저자 필터가 유지되는지 확인
    assert viewer.locator(BADGE).count() == 1, "태그 필터 적용 후 저자 배지가 사라졌습니다."


@pytest.mark.e2e
def test_infinite_scroll_loads_more_cards(viewer):
    """12. 필터 없이도(60건 초과 목록) 스크롤 시 추가 카드가 로드된다.

    개별 저자의 게시글이 60건을 넘는 경우가 드물어 저자 필터 상태에서는
    무한스크롤을 재현하기 어렵다. 대신 필터 없는 전체 목록(2,000건 규모)으로
    페이지네이션 로직 자체의 정상 동작을 확인한다 - 저자 필터 코드는 이
    로직을 변경하지 않았으므로 회귀 검증으로 충분하다.
    """
    initial = _card_count(viewer)
    assert initial <= 60, f"첫 배치가 60건을 넘습니다: {initial} (렌더 배치 크기 가정이 깨짐)"

    viewer.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    viewer.wait_for_timeout(1200)
    viewer.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    viewer.wait_for_timeout(1200)

    after_scroll = _card_count(viewer)
    assert after_scroll > initial, (
        f"스크롤 후 카드가 늘어나지 않았습니다: {initial} -> {after_scroll}"
    )
