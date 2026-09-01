"""자막 언어 폴백 수정으로 회수한 유튜브 요약이 뷰어에 실제로 뜨는지 검증한다.

계획서: _docs/20260827_01_유튜브-자막-언어폴백-결함수정과-요약-319건-소진-계획.md (S10)

육안 확인이 아니라 assertion 으로 판정한다. 브라우저는 headless 로 고정한다 -
창이 뜨면 사용자 포커스를 뺏는다.

이 테스트는 뷰어 서버가 이미 떠 있는 상태를 전제한다(다른 e2e 모듈과 같다).
playwright 와 flask 가 서로 다른 인터프리터에 설치돼 있어 한 프로세스에서
둘을 함께 import 할 수 없다.
"""

import glob
import json
import os

import pytest
import requests
from playwright.sync_api import sync_playwright

CARD = "#masonryGrid article.glass-card"
VIEWER_URL = os.environ.get("SNS_VIEWER_URL", "http://localhost:5000")

# 자막 언어 폴백 수정으로 회수한 영상 중 표본. 둘 다 예전에는 no_subtitle 이었다.
#   rsSUIvAkjvk — 영어 원본(en-orig)으로 회수
#   Qt50DVNJcvw — -orig 트랙이 없어 2차 폴백(수동 en 자막)으로 회수
# 검색 문구는 카드 렌더 확인용이다. 뷰어 검색은 본문 기준이라 video_id 로는 안 걸린다.
RECOVERED_SAMPLES = [
    ("rsSUIvAkjvk", "The One-Person Startup Era"),
    ("Qt50DVNJcvw", "듀얼 브레인"),
]


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


@pytest.fixture
def viewer(browser, server_url):
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    page.goto(f"{server_url}/")
    page.wait_for_selector(CARD, timeout=20000)
    page.wait_for_timeout(1200)
    yield page
    context.close()


def _latest_total_file():
    files = glob.glob(os.path.join("output_total", "total_full_*.json"))
    if not files:
        pytest.fail("output_total/total_full_*.json 이 없습니다. 통합본을 먼저 생성하세요.")
    return max(files, key=os.path.getmtime)


def _latest_total_posts():
    # 통합본은 BOM 포함 UTF-8 로 저장된다. utf-8 로 열면 JSONDecodeError 가 난다.
    with open(_latest_total_file(), "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data.get("posts", data) if isinstance(data, dict) else data


def test_viewer_total_matches_latest_total_file(viewer):
    """뷰어 상단 총건수와 최신 통합본 게시글 수가 같아야 한다.

    둘이 어긋나면 뷰어가 옛 파일을 읽고 있거나 병합이 덜 끝난 것이다.
    """
    expected = len(_latest_total_posts())
    served = viewer.evaluate(
        "async () => (await (await fetch('/api/posts')).json()).posts.length"
    )
    assert served == expected, (
        f"뷰어가 내려주는 글 수 {served} != 최신 통합본 {expected} "
        f"({os.path.basename(_latest_total_file())})"
    )


@pytest.mark.parametrize("video_id,_query", RECOVERED_SAMPLES)
def test_recovered_video_is_served_with_summary(viewer, video_id, _query):
    """회수분이 뷰어 데이터에 있고 요약이 본문에 실려 있어야 한다.

    목록 API 는 축약본이라 full_text_preview 만 준다. 요약 블록은 본문 앞머리에
    붙으므로 preview 로도 판정할 수 있다.
    """
    post = viewer.evaluate(
        """async (vid) => {
            const data = await (await fetch('/api/posts')).json();
            return data.posts.find(p => p.platform_id === vid) || null;
        }""",
        video_id,
    )
    assert post is not None, f"{video_id} 가 뷰어 데이터에 없다"
    assert "[요약]" in (post.get("full_text_preview") or ""), (
        f"{video_id} 본문 앞머리에 요약 블록이 없다: "
        f"{(post.get('full_text_preview') or '')[:80]}"
    )

    # 저장 데이터 쪽 상태도 함께 본다. 목록 API 에는 이 필드가 없다.
    stored = next(
        (p for p in _latest_total_posts() if p.get("platform_id") == video_id), None
    )
    assert stored is not None, f"{video_id} 가 통합본에 없다"
    assert stored.get("transcript_status") == "ok", (
        f"{video_id} 자막 상태가 ok 가 아니다: {stored.get('transcript_status')}"
    )
    assert stored.get("summary_status") == "ok", (
        f"{video_id} 요약 상태가 ok 가 아니다: {stored.get('summary_status')}"
    )


@pytest.mark.parametrize("video_id,query", RECOVERED_SAMPLES)
def test_recovered_video_renders_as_card(viewer, video_id, query):
    """검색으로 회수분 카드가 화면에 실제로 그려지는지 확인한다."""
    viewer.fill("#searchInput", query)
    viewer.wait_for_timeout(2000)
    html = viewer.inner_html("#masonryGrid")
    assert video_id in html, (
        f"'{query}' 검색 결과에 {video_id} 카드가 없다 (렌더된 길이 {len(html)})"
    )


def test_members_only_videos_are_not_summarized():
    """멤버 전용은 자막을 못 받으므로 요약도 없어야 한다.

    이것이 깨지면 엉뚱한 자막을 요약에 넣은 것이다.
    """
    posts = [p for p in _latest_total_posts() if p.get("sns_platform") == "youtube"]
    bad = [
        p.get("platform_id")
        for p in posts
        if p.get("transcript_status") == "members_only" and p.get("summary_status") == "ok"
    ]
    assert not bad, f"멤버 전용인데 요약이 붙은 글: {bad}"
