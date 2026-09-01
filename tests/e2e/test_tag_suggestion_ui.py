"""태그 추천 목록(W1-T) E2E 검증.

태그 관리 화면에서 새로 만든 태그가 게시글 카드의 `+Tag` 추천 칩에 나오지 않던
버그를 다룬다. 추천 목록의 재료가 `postTags`(실제로 붙어 있는 태그)뿐이라
사용 0건 태그는 구조적으로 나올 수 없었다.

기댓값을 특정 태그명으로 하드코딩하지 않는다. 그 태그를 실제로 쓰기 시작하면
사용 0건이 아니게 되어 테스트가 죽는다. 카탈로그와 태그 파일에서 조건을
계산해 비교한다.

T3 은 실제 `sns_tags.json` 을 바꾸므로 fixture 가 원본을 반드시 되돌린다.
되돌리기 실패를 조용히 넘기지 않고 assert 로 잡는다.

브라우저는 headless 로 고정한다 (창이 뜨면 사용자 포커스를 뺏는다).

계획: _docs/20260826_02_뷰어정리-유튜브확대-지표갱신-웨이브계획.md (W1-T)
"""

import json
import os

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
ADD_TAG_BTN = ".tag-add-btn"
SUGGESTION = ".tag-suggestions .suggestion-item"

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
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


def _get_tags(server_url):
    return requests.get(f"{server_url}/api/get-tags", timeout=10).json()


def _get_catalog(server_url):
    return requests.get(f"{server_url}/api/get-tag-catalog", timeout=10).json()


def _canonical(payload):
    """서버가 sort_keys=True 로 재직렬화하므로 byte 가 아니라 구조로 비교한다."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


@pytest.fixture
def tags_restored(server_url):
    """테스트가 sns_tags.json 을 바꾸면 원본으로 되돌리고 동일성까지 확인한다."""
    original = _get_tags(server_url)
    baseline = _canonical(original)
    yield original

    requests.post(f"{server_url}/api/save-tags", json=original, timeout=10).raise_for_status()
    after = _canonical(_get_tags(server_url))
    assert after == baseline, "테스트가 바꾼 태그 상태를 원복하지 못했다"


@pytest.mark.e2e
def test_t1_unused_catalog_tag_appears_in_suggestions(browser, server_url):
    """T1: 아직 아무 글에도 안 붙은 카탈로그 태그가 추천 칩에 나온다."""
    catalog = _get_catalog(server_url)
    tags = _get_tags(server_url)

    used = set()
    for value in tags.values():
        if isinstance(value, list):
            used.update(value)

    unused = sorted(set(catalog.keys()) - used)
    if not unused:
        pytest.skip("사용 0건 카탈로그 태그가 없어 T1 을 판정할 수 없다")

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1200)

        page.locator(CARD).first.locator(ADD_TAG_BTN).first.click()
        page.wait_for_selector(SUGGESTION, timeout=10000)

        shown = set(page.locator(SUGGESTION).all_inner_texts())
        missing = [tag for tag in unused if tag not in shown]
        assert not missing, (
            f"사용 0건 카탈로그 태그가 추천에 없다: {missing} / 표시된 칩 {sorted(shown)}"
        )
    finally:
        context.close()


@pytest.mark.e2e
def test_t2_already_attached_tags_excluded(browser, server_url):
    """T2: 해당 게시글에 이미 붙은 태그는 추천에서 빠진다 (기존 동작 회귀 없음)."""
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1200)

        target = None
        attached = set()
        cards = page.locator(CARD)
        for i in range(min(cards.count(), 30)):
            chips = cards.nth(i).locator(".tag-container .tag-chip")
            if chips.count() > 0:
                target = cards.nth(i)
                attached = set(chips.all_inner_texts())
                break
        if target is None:
            pytest.skip("태그가 붙은 카드를 찾지 못해 T2 를 판정할 수 없다")

        target.locator(ADD_TAG_BTN).first.click()
        page.wait_for_selector(SUGGESTION, timeout=10000)

        shown = set(page.locator(SUGGESTION).all_inner_texts())
        overlap = shown & {t.strip() for t in attached}
        assert not overlap, f"이미 붙은 태그가 추천에 나왔다: {sorted(overlap)}"
    finally:
        context.close()


@pytest.mark.e2e
def test_t3_clicking_suggestion_persists_to_server(browser, server_url, tags_restored):
    """T3: 추천 칩을 누르면 서버에 저장된다. 끝나면 fixture 가 원복한다."""
    catalog = _get_catalog(server_url)
    tags = tags_restored

    used = set()
    for value in tags.values():
        if isinstance(value, list):
            used.update(value)
    unused = sorted(set(catalog.keys()) - used)
    if not unused:
        pytest.skip("사용 0건 카탈로그 태그가 없어 T3 을 판정할 수 없다")
    target_tag = unused[0]

    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    try:
        page.goto(f"{server_url}/")
        page.wait_for_selector(CARD, timeout=20000)
        page.wait_for_timeout(1200)

        page.locator(CARD).first.locator(ADD_TAG_BTN).first.click()
        page.wait_for_selector(SUGGESTION, timeout=10000)

        chip = page.locator(SUGGESTION, has_text=target_tag).first
        assert chip.count() > 0, f"추천 칩에서 {target_tag!r} 을 찾지 못했다"
        chip.click()
        page.wait_for_timeout(1500)

        after = _get_tags(server_url)
        attached_anywhere = any(
            isinstance(v, list) and target_tag in v for v in after.values()
        )
        assert attached_anywhere, f"{target_tag!r} 이 서버 태그 상태에 반영되지 않았다"
    finally:
        context.close()
