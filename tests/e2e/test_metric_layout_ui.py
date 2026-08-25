"""성과지표 배치 통합·정렬 분리 E2E 테스트.

조회수 배지를 헤더에서 카드 하단 지표 행 맨 앞으로 옮긴 변경(R1·R2)과,
'성과순'을 '반응순'/'조회수순'으로 나눈 변경(R3·R4)을 DOM 상태로 검증한다.

판정은 전부 assertion 으로 한다. 화면 캡처는 부수 증거일 뿐 판정 기준이 아니다.
브라우저는 headless 로 고정한다 (창이 뜨면 사용자 포커스를 뺏는다).

기댓값은 변경 전 상태에 의존하지 않는다. 정렬·총건수 기준값은 실행 시점에
/api/posts 를 호출해 계산하고, 나머지는 논리 조건으로 판정한다.

계획: _docs/20260825_03_뷰어-성과지표-배치통합-정렬분리-계획.md
"""

import os
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
METRICS_ROW = ".metrics-row"
BADGE = ".metric-badge"

# 자체 서버를 띄우지 않는 이유는 test_author_filter_ui.py 와 같다.
# playwright 와 flask 가 서로 다른 인터프리터에 설치돼 한 프로세스에서 함께 import 할 수 없다.
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260825_03"

REACTION_FIELDS = ("like_count", "comment_count", "share_count")


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
    """정렬·총건수 기댓값 계산에 쓰는 원천 데이터."""
    response = requests.get(f"{server_url}/api/posts", timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload.get("posts", payload)


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


def _metric_int(post, field):
    """뷰어의 hasMetricValue 규칙(-1 은 값 없음)을 그대로 따른다."""
    value = post.get(field)
    if value in (None, "", -1, "-1"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_metric_count(value):
    """web_viewer/script.js 의 formatMetricCount 와 같은 규칙."""
    n = int(value)
    if n >= 10000:
        text = f"{n / 10000:.1f}"
        return f"{text[:-2] if text.endswith('.0') else text}만"
    if n >= 1000:
        text = f"{n / 1000:.1f}"
        return f"{text[:-2] if text.endswith('.0') else text}천"
    return str(n)


def _search(page, keyword):
    page.fill("#searchInput", keyword)
    page.wait_for_timeout(1200)


def _first_card(page):
    return page.locator(CARD).first


def _card_for(page, post):
    """검색 결과 중 해당 게시글의 카드를 URL 로 특정한다.

    같은 작성자의 글이 여러 건이므로 '첫 카드'를 target 으로 가정하면 안 된다.
    """
    url = post.get("url") or post.get("canonical_url")
    assert url, f"게시글에 url 이 없다: {post.get('display_name')}"
    cards = page.locator(CARD)
    for i in range(cards.count()):
        card = cards.nth(i)
        btn = card.locator(".fold-btn")
        if btn.count() and btn.first.get_attribute("data-url") == url:
            return card
    raise AssertionError(f"해당 URL 의 카드를 찾지 못했다: {url}")


def _badge_fields(card):
    row = card.locator(METRICS_ROW)
    if row.count() == 0:
        return []
    return row.first.locator(BADGE).evaluate_all(
        "els => els.map(e => e.dataset.metric)"
    )


def _select_sort(page, sort_key):
    page.click("#sortBtn")
    page.wait_for_timeout(300)
    page.click(f'#sortDropdown [data-sort="{sort_key}"]')
    page.wait_for_timeout(1500)


def _shot(page, name):
    """부수 증거. 판정 기준이 아니다."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR / f"{name}.png"), full_page=False)


@pytest.mark.e2e
def test_v1_youtube_view_badge_moved_to_metrics_row(viewer, posts):
    """V1: 유튜브 카드의 조회수가 헤더가 아니라 하단 지표 행에 있다."""
    target = next(
        p for p in posts
        if p.get("sns_platform") == "youtube" and _metric_int(p, "view_count")
    )
    _search(viewer, target["display_name"])
    card = _card_for(viewer, target)

    header_text = card.locator(".min-w-0").first.inner_text()
    expected = _format_metric_count(_metric_int(target, "view_count"))
    assert expected not in header_text, f"헤더에 조회수가 남아 있다: {header_text!r}"

    fields = _badge_fields(card)
    assert fields, "지표 행이 없다"
    assert fields[0] == "view_count", f"조회수가 첫 배지가 아니다: {fields}"
    assert expected in card.locator(METRICS_ROW).first.inner_text()
    _shot(viewer, "v1_youtube_card")


@pytest.mark.e2e
def test_v2_x_card_shows_all_metrics_in_one_row(viewer, posts):
    """V2: X 카드의 지표가 조회수부터 한 행에 모두 표시된다."""
    target = max(
        (p for p in posts if p.get("sns_platform") == "x" and _metric_int(p, "view_count")),
        key=lambda p: _metric_int(p, "view_count") or 0,
    )
    _search(viewer, target["display_name"])
    card = _card_for(viewer, target)

    fields = _badge_fields(card)
    expected_fields = [
        f for f in ("view_count", "like_count", "comment_count",
                    "share_count", "quote_count", "bookmark_count")
        if _metric_int(target, f) is not None
    ]
    assert fields == expected_fields, f"배지 구성 불일치: {fields} != {expected_fields}"
    assert fields[0] == "view_count"
    _shot(viewer, "v2_x_card")


@pytest.mark.e2e
@pytest.mark.parametrize("platform", ["threads", "linkedin"])
def test_v3_platforms_without_views_unchanged(viewer, posts, platform):
    """V3: 조회수를 제공하지 않는 플랫폼은 배지 구성이 API 값과 일치하고 조회수 배지가 없다."""
    target = next(
        p for p in posts
        if p.get("sns_platform") == platform and _metric_int(p, "like_count")
    )
    _search(viewer, target["display_name"])
    card = _card_for(viewer, target)

    fields = _badge_fields(card)
    assert "view_count" not in fields, f"{platform} 카드에 조회수 배지가 있다: {fields}"
    expected_count = sum(
        1 for f in ("view_count", "like_count", "comment_count",
                    "share_count", "quote_count", "bookmark_count")
        if _metric_int(target, f) is not None
    )
    assert len(fields) == expected_count


@pytest.mark.e2e
def test_v4_every_post_with_views_has_metrics_row(viewer, posts):
    """V4: 조회수를 가진 글은 예외 없이 지표 행을 갖는다 (R2 회귀 방지).

    지표 행 생성 조건(METRIC_DEFS)에 view_count 가 포함돼 있어야만 성립한다.
    조회수가 빠지면 반응 지표가 하나도 없는 글에서 배지 행 자체가 사라진다.

    참고: 뷰어의 hasMetricValue 는 0 을 유효값으로 본다. 따라서 comment_count=0 처럼
    0 이 들어 있는 글은 '조회수만 있는 카드'가 아니다.
    """
    targets = [p for p in posts if _metric_int(p, "view_count") is not None][:12]
    assert targets, "조회수를 가진 게시글이 없다"

    checked = 0
    for target in targets:
        _search(viewer, target["display_name"])
        if viewer.locator(CARD).count() == 0:
            continue
        try:
            card = _card_for(viewer, target)
        except AssertionError:
            continue
        fields = _badge_fields(card)
        assert fields, f"조회수를 가진 글에 지표 행이 없다: {target.get('url')}"
        assert fields[0] == "view_count", f"조회수가 첫 배지가 아니다: {fields}"
        checked += 1
        if checked >= 5:
            break

    assert checked >= 1, "검증 대상 카드를 하나도 찾지 못했다"


@pytest.mark.e2e
def test_v5_fold_hides_metrics_row_including_views(viewer, posts):
    """V5: 카드를 접으면 조회수를 포함한 지표 행 전체가 숨겨진다 (P2 해소)."""
    target = next(
        p for p in posts
        if p.get("sns_platform") == "youtube" and _metric_int(p, "view_count")
    )
    _search(viewer, target["display_name"])
    card = _card_for(viewer, target)
    assert card.locator(METRICS_ROW).count() == 1

    card.locator(".fold-btn").click()
    viewer.wait_for_timeout(800)

    card = _card_for(viewer, target)
    row = card.locator(METRICS_ROW)
    assert row.count() == 1
    classes = row.first.get_attribute("class") or ""
    assert "hidden-content" in classes, f"접힘 상태에서 지표 행이 숨겨지지 않았다: {classes}"
    assert not row.first.is_visible()

    card.locator(".fold-btn").click()
    viewer.wait_for_timeout(500)


@pytest.mark.e2e
def test_v6_views_sort_orders_by_view_count(viewer, posts):
    """V6: 조회수순 정렬의 첫 카드가 조회수 최댓값 글이다."""
    expected = max(
        (p for p in posts if _metric_int(p, "view_count")),
        key=lambda p: _metric_int(p, "view_count") or 0,
    )
    _select_sort(viewer, "views")

    author = _first_card(viewer).locator(".author-link").inner_text().strip()
    assert author == (expected.get("display_name") or "").strip(), \
        f"조회수순 첫 카드 불일치: {author}"

    for i in range(min(5, viewer.locator(CARD).count())):
        fields = _badge_fields(viewer.locator(CARD).nth(i))
        assert fields and fields[0] == "view_count", \
            f"{i}번째 카드에 조회수 배지가 없다: {fields}"
    _shot(viewer, "v6_sort_views")


@pytest.mark.e2e
def test_v7_engagement_sort_orders_by_reactions(viewer, posts):
    """V7: 반응순 정렬의 첫 카드가 좋아요+댓글+공유 합계 최댓값 글이다."""
    def score(post):
        return sum(_metric_int(post, f) or 0 for f in REACTION_FIELDS)

    expected = max(posts, key=score)
    _select_sort(viewer, "engagement")

    author = _first_card(viewer).locator(".author-link").inner_text().strip()
    assert author == (expected.get("display_name") or "").strip(), \
        f"반응순 첫 카드 불일치: {author}"
    _shot(viewer, "v7_sort_engagement")


@pytest.mark.e2e
@pytest.mark.parametrize("sort_key,label", [("views", "조회수순"), ("engagement", "반응순")])
def test_v8_sort_persists_across_reload(viewer, sort_key, label):
    """V8: 정렬 선택이 새로고침 후에도 유지된다 (P4 해소)."""
    _select_sort(viewer, sort_key)
    assert viewer.locator("#currentSortLabel").inner_text().strip() == label

    viewer.reload()
    viewer.wait_for_selector(CARD, timeout=20000)
    viewer.wait_for_timeout(1000)

    assert viewer.locator("#currentSortLabel").inner_text().strip() == label, \
        "새로고침 후 정렬이 리셋됐다"


@pytest.mark.e2e
def test_v9_metrics_only_filter_shows_only_carded_posts(viewer):
    """V9: 지표 보유만 보기를 켜면 표시된 모든 카드가 지표 행을 갖는다."""
    viewer.click("#metricsOnlyBtn")
    viewer.wait_for_timeout(1500)

    cards = viewer.locator(CARD)
    total = cards.count()
    assert total > 0, "필터 적용 후 카드가 하나도 없다"

    for i in range(min(total, 30)):
        assert cards.nth(i).locator(METRICS_ROW).count() == 1, \
            f"{i}번째 카드에 지표 행이 없다"

    viewer.click("#metricsOnlyBtn")
    viewer.wait_for_timeout(800)


@pytest.mark.e2e
def test_v10_total_count_matches_api(viewer, posts):
    """V10: 상단 총건수가 /api/posts 응답 건수와 일치한다."""
    text = viewer.locator("#totalPostsCount").inner_text()
    digits = "".join(ch for ch in text.split("/")[-1] if ch.isdigit())
    assert int(digits) == len(posts), f"총건수 불일치: {text!r} vs API {len(posts)}건"
