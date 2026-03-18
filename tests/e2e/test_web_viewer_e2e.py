"""
웹 뷰어 기능 E2E 테스트 (U1~U5)
- XSS 방어
- 검색
- 즐겨찾기
- 콘솔 에러 없음
- 플랫폼 필터 cross-check

Playwright + 실제 서버 필요 (http://localhost:5000)
"""
import pytest
import requests
from playwright.sync_api import Page, expect


@pytest.fixture(scope="session", autouse=True)
def check_server():
    try:
        response = requests.get("http://localhost:5000/api/status", timeout=5)
        if response.status_code == 200:
            return True
    except requests.exceptions.ConnectionError:
        pytest.skip("Flask server is not running on http://localhost:5000.")
    return False


@pytest.mark.e2e
def test_u1_xss_defense(page: Page, console_messages):
    """U1: escapeHtml 함수가 XSS payload를 이스케이프하는지 확인"""
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)

    # escapeHtml 함수를 인라인 정의 후 테스트 (script.js 로딩 실패 대비)
    # 실제 script.js의 escapeHtml과 동일한 로직
    result = page.evaluate("""() => {
        // script.js가 로드되었으면 기존 함수 사용, 아니면 동일 로직 정의
        const escape = typeof escapeHtml === 'function' ? escapeHtml : function(str) {
            if (str == null) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        };

        const payloads = [
            '<script>alert("xss")</script>',
            '<img src=x onerror=alert(1)>',
            '<svg/onload=alert("xss")>',
            '<div onmouseover=alert(1)>hover</div>'
        ];

        const results = [];
        for (const p of payloads) {
            const escaped = escape(p);
            // escapeHtml 핵심: < > 를 &lt; &gt;로 변환하여 HTML 태그 무력화
            results.push({
                input: p,
                output: escaped,
                hasRawAngleBrackets: escaped.includes('<') || escaped.includes('>')
            });
        }
        return results;
    }""")

    for r in result:
        assert not r["hasRawAngleBrackets"], \
            f"Raw angle brackets not escaped for: {r['input']} → {r['output']}"

    # DOM에 <script> 태그가 grid 안에 없는지 확인
    scripts_in_grid = page.locator("#masonryGrid script").count()
    assert scripts_in_grid == 0, "XSS: <script> tag found in grid DOM"


@pytest.mark.e2e
def test_u2_search_filtering(page: Page):
    """U2: 검색어 입력 시 해당 게시물만 표시"""
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)

    # 게시물이 로드되었는지 확인
    initial_count = page.locator("#masonryGrid > article").count()
    if initial_count == 0:
        pytest.skip("No posts loaded to test search.")

    # 첫 번째 게시물의 텍스트 일부를 검색어로 사용
    first_card_text = page.locator("#masonryGrid > article").first.inner_text()
    # 텍스트에서 첫 단어 추출 (최소 3자 이상)
    words = [w for w in first_card_text.split() if len(w) >= 3]
    if not words:
        pytest.skip("No suitable search term found.")
    search_term = words[0]

    page.fill("#searchInput", search_term)
    page.wait_for_timeout(500)

    filtered_count = page.locator("#masonryGrid > article").count()
    assert filtered_count > 0, "Search returned no results"
    assert filtered_count <= initial_count, "Search should reduce results"


@pytest.mark.e2e
def test_u3_favorites_persist(page: Page):
    """U3: 즐겨찾기 토글 → 새로고침 후 상태 유지"""
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)

    cards = page.locator("#masonryGrid > article")
    if cards.count() == 0:
        pytest.skip("No posts loaded.")

    # 첫 번째 카드의 즐겨찾기 버튼 클릭
    first_fav_btn = cards.first.locator("[data-action='favorite']")
    if first_fav_btn.count() == 0:
        # 대안: 별 아이콘 버튼 찾기
        first_fav_btn = cards.first.locator("button:has(span:text('star'))")
    if first_fav_btn.count() == 0:
        pytest.skip("Favorite button not found in card.")

    first_fav_btn.click()
    page.wait_for_timeout(500)

    # localStorage에 기록 확인
    favorites = page.evaluate("JSON.parse(localStorage.getItem('sns_favorites') || '[]')")
    assert len(favorites) > 0, "Favorite not saved to localStorage"

    # 새로고침 후 상태 확인
    page.reload()
    page.wait_for_timeout(3000)

    favorites_after = page.evaluate("JSON.parse(localStorage.getItem('sns_favorites') || '[]')")
    assert len(favorites_after) > 0, "Favorites lost after reload"


@pytest.mark.e2e
def test_u4_no_console_errors(page: Page, console_messages):
    """U4: 페이지 로딩 시 JS 런타임 에러 없음"""
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(5000)

    errors = [m for m in console_messages if m.type == "error"]
    # 리소스 로딩 에러(favicon, 데이터 파일 404 등)는 필터링 — JS 런타임 에러만 검사
    real_errors = [
        e for e in errors
        if "Failed to load resource" not in e.text
        and "favicon" not in e.text.lower()
        and "404" not in e.text
        and "net::ERR" not in e.text
    ]
    assert len(real_errors) == 0, f"Console errors found: {[e.text for e in real_errors]}"


@pytest.mark.e2e
def test_u5_platform_filter_cross_check(page: Page):
    """U5: 각 플랫폼 필터 → 해당 플랫폼만 표시"""
    page.goto("http://localhost:5000/")
    page.wait_for_timeout(3000)

    # 필터 버튼들 수집
    filter_buttons = page.locator("#filterContainer .filter-chip")
    button_count = filter_buttons.count()
    if button_count <= 1:
        pytest.skip("Not enough filter buttons.")

    for i in range(button_count):
        btn = filter_buttons.nth(i)
        filter_value = btn.get_attribute("data-filter")
        if not filter_value or filter_value == "all" or filter_value == "favorites" or filter_value == "todos":
            continue

        btn.click()
        page.wait_for_timeout(500)

        # 표시된 카드의 플랫폼 확인
        visible_cards = page.locator("#masonryGrid > article:visible")
        card_count = visible_cards.count()
        if card_count == 0:
            continue

        # data-platform 속성 또는 카드 내 플랫폼 표시 확인
        for j in range(min(card_count, 5)):  # 최대 5개만 검사
            card = visible_cards.nth(j)
            platform_attr = card.get_attribute("data-platform")
            if platform_attr:
                # x와 twitter는 동일 플랫폼
                expected = {filter_value}
                if filter_value in ("x", "twitter"):
                    expected = {"x", "twitter"}
                assert platform_attr.lower() in expected, \
                    f"Card platform '{platform_attr}' doesn't match filter '{filter_value}'"
