"""내 글 두 플랫폼 교차 정렬의 화면 반영 E2E.

「로컬수집순」에서 내 글이 플랫폼별 두 덩어리로 갈리던 것을 하나로 합치고,
같은 날이면 링크드인을 위에 고정했다. 그 결과가 **화면에** 나오는지 본다.
저장된 순번(API/JSON)만 보면 뷰어 렌더가 다른 기준으로 서 있어도 통과한다.

⚠️ 뷰어는 masonry 다. 카드를 「가장 짧은 열」에 넣으므로(`web_viewer/script.js`
   `buildMasonryColumns`) **DOM 순서가 읽기 순서가 아니다** — 4열이면 DOM 은
   1열 15장 전부, 그다음 2열 15장 순이다. 화면 순서는 좌표로 판정해야 한다.
   실측: 4열, 열마다 15장. 1열에 1·5·9번째 글이 들어간다.

육안 판정에 의존하지 않는다. 브라우저는 headless 로 고정하고, 종료코드와
캡처 파일로 판정한다 - 창이 뜨면 사용자 포커스를 뺏는다.

계획: _docs/20260827_04 (5절 V9)
"""

import os
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
MY_BTN = "#myPostsBtn"

VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "_docs" / "evidence" / "20260827_04"

#: 같은 행으로 볼 y 오차(px). 열마다 카드 높이가 달라 1px 단위로는 갈린다.
ROW_TOLERANCE = 8


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
        pytest.fail(f"뷰어 서버에 접속할 수 없습니다: {VIEWER_URL} ({exc}).")
    return VIEWER_URL


@pytest.fixture(scope="module")
def own_posts(server_url):
    posts = requests.get(f"{server_url}/api/posts", timeout=60).json().get("posts", [])
    own = [p for p in posts if p.get("is_own_post") is True]
    assert own, "API 응답에 내 글이 없습니다."
    return sorted(own, key=lambda q: -int(q.get("sequence_id") or 0))


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
    page.click(MY_BTN)
    page.wait_for_timeout(1500)
    yield page
    context.close()


def _capture(page, name):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE_DIR / f"{name}.png"), full_page=False)


def _layout(page):
    """카드의 플랫폼과 화면 좌표를 읽는다. 열 구조도 함께 본다."""
    return page.evaluate(
        """() => {
          const cols = [...document.querySelectorAll('#masonryGrid .masonry-col')];
          return {
            columns: cols.map(col => [...col.querySelectorAll('article.glass-card')]
              .map(a => a.getAttribute('data-platform'))),
            cards: [...document.querySelectorAll('#masonryGrid article.glass-card')].map(a => {
              const r = a.getBoundingClientRect();
              return {
                platform: a.getAttribute('data-platform'),
                x: Math.round(r.x),
                y: Math.round(r.y + window.scrollY),
              };
            }),
          };
        }"""
    )


def _first_row(cards):
    """가장 위 행의 카드들을 왼쪽부터."""
    top = min(card["y"] for card in cards)
    row = [card for card in cards if abs(card["y"] - top) <= ROW_TOLERANCE]
    return sorted(row, key=lambda c: c["x"])


# V9 - 화면 첫 행이 링크드인/쓰레드로 교차한다
def test_first_row_alternates_platforms(viewer, own_posts):
    """이 계획 이전에는 쓰레드 32장이 통째로 앞을 점거해 첫 행이 전부 threads 였다."""
    expected = [post["sns_platform"] for post in own_posts]
    assert expected[:4] == ["linkedin", "threads", "linkedin", "threads"], (
        f"API 순번부터 교차하지 않는다: {expected[:4]}"
    )

    layout = _layout(viewer)
    _capture(viewer, "v9_my_filter_first_row")

    row = _first_row(layout["cards"])
    assert len(row) >= 2, f"첫 행 카드가 2장 미만: {len(row)}"

    observed = [card["platform"] for card in row]
    assert observed == expected[: len(row)], (
        f"화면 첫 행 플랫폼이 순번과 다르다. 기대={expected[:len(row)]} 실제={observed}"
    )
    assert len(set(observed)) == 2, (
        f"첫 행이 한 플랫폼으로만 채워졌다(블록이 갈린 상태): {observed}"
    )


# V9 - 같은 날 짝에서 링크드인이 쓰레드보다 먼저 읽힌다
def test_same_day_linkedin_is_read_before_threads(viewer, own_posts):
    """masonry 라 '위'는 y 만으로 정해지지 않는다. 읽기 순서 (y, x) 로 판정한다."""
    newest = own_posts[:2]
    assert {p["sns_platform"] for p in newest} == {"linkedin", "threads"}, (
        f"상위 2건이 같은 날 짝이 아니다: {[p['sns_platform'] for p in newest]}"
    )
    assert newest[0]["created_at"][:10] == newest[1]["created_at"][:10], (
        "상위 2건의 작성 날짜가 다르다"
    )

    layout = _layout(viewer)
    _capture(viewer, "v9_same_day_linkedin_first")

    by_reading_order = sorted(layout["cards"], key=lambda c: (c["y"], c["x"]))
    first_two = [card["platform"] for card in by_reading_order[:2]]

    assert first_two == ["linkedin", "threads"], (
        f"같은 날 짝에서 링크드인이 먼저 읽혀야 한다. 실제={first_two}"
    )


# 열 안에서는 순번이 계속 내려간다 (렌더가 순서를 흐트러뜨리지 않았다)
def test_each_column_keeps_platform_pattern(viewer, own_posts):
    """4열이면 1열은 1·5·9…번째 글을 받는다. 그 규칙이 유지되는지 본다."""
    layout = _layout(viewer)
    columns = layout["columns"]
    assert columns, "masonry 열을 못 찾았다"

    expected = [post["sns_platform"] for post in own_posts]
    ncols = len(columns)
    for index, column in enumerate(columns):
        want = expected[index :: ncols][: len(column)]
        assert column == want, (
            f"{index + 1}번 열의 플랫폼 순서가 순번과 다르다.\n기대={want}\n실제={column}"
        )


# 내 글이 한 덩어리로 붙어 있다 (블록이 갈리지 않았다)
def test_own_posts_form_one_contiguous_block(own_posts):
    seq = sorted(int(p.get("sequence_id") or 0) for p in own_posts)
    assert seq[-1] - seq[0] + 1 == len(seq), (
        f"내 글 {len(seq)}건이 연속 블록이 아니다: {seq[0]}~{seq[-1]}"
    )
