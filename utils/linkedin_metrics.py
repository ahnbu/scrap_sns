"""LinkedIn 참여지표 추출 - 비로그인 공개 페이지 기반.

계획: _docs/20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획.md

저장글 목록 API(Voyager GraphQL)는 지표 값을 응답에 담아주지 않는다(계획 2.2절).
그래서 지표는 게시글 공개 permalink 에 **로그인하지 않고** 접근해 DOM 속성에서 읽는다.

추출 위치는 `data-num-reactions` / `data-num-comments` 속성이며, 2026-08-25 실측에서
좋아요 3 ~ 3,828 구간 8건 전부, 반응+댓글 동시 4건 전부가 기존 로그인 수집값과 일치했다.

⚠️ JSON-LD 의 `interactionStatistic` 은 사용하지 않는다. 같은 페이지에서 좋아요 252 인
   글을 `LikeAction: 0` 으로 반환한다 - 댓글 수만 맞고 좋아요는 신뢰할 수 없다(계획 3.2절 C안).

⚠️ 브라우저는 항상 headless 이고, storage_state 를 주입하지 않은 새 컨텍스트를 쓴다.
   로그인 세션이 섞이면 이 모듈의 전제가 무너진다(계획 3.3절).
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime

from utils import metric_refresh

# 공개 페이지에서 지표를 담고 있는 DOM 속성.
REACTION_ATTR = "data-num-reactions"
COMMENT_ATTR = "data-num-comments"

# 비로그인 컨텍스트 고정값. 수집기와 환경을 맞춰 불필요한 분기 렌더링을 피한다.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
BROWSER_LOCALE = "ko-KR"
BROWSER_VIEWPORT = {"width": 1280, "height": 1000}

POST_URL_TEMPLATE = "https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"

_ACTIVITY_ID_RE = re.compile(r"activity:(\d+)")

# 페이지에서 지표 속성을 읽는 스크립트.
# 반응과 댓글이 서로 다른 요소에 붙어 있으므로 각각 조회한다.
_EXTRACT_JS = """() => {
  const r = document.querySelector('[data-num-reactions]');
  const c = document.querySelector('[data-num-comments]');
  let commentsText = null;
  const link = document.querySelector(
    'a[data-tracking-control-name="public_post_social-actions-comments"]'
  );
  if (link) {
    const m = (link.innerText || '').match(/([\\d,]+)/);
    if (m) commentsText = m[1].replace(/,/g, '');
  }
  return {
    reactions: r ? r.getAttribute('data-num-reactions') : null,
    comments_attr: c ? c.getAttribute('data-num-comments') : null,
    comments_text: commentsText,
  };
}"""


def extract_activity_id(url: str) -> str | None:
    """게시글 URL에서 activity id를 뽑는다."""
    if not url:
        return None
    match = _ACTIVITY_ID_RE.search(str(url))
    return match.group(1) if match else None


def build_post_url(activity_id: str) -> str:
    """activity id로 공개 permalink를 만든다."""
    return POST_URL_TEMPLATE.format(activity_id=activity_id)


def _to_int(value) -> int | None:
    """'1,388' 같은 표기를 정수로. 실패하면 None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text.isdigit():
        return None
    return int(text)


def parse_metrics_from_dom(raw: dict | None) -> dict | None:
    """`_EXTRACT_JS` 결과를 표준 지표 dict로 변환한다.

    반응 수를 얻지 못하면 추출 실패로 본다 - 그 경우 페이지 자체가 지표를
    렌더하지 않은 것이므로 댓글 수만 신뢰할 근거가 없다.
    """
    if not isinstance(raw, dict):
        return None

    like_count = _to_int(raw.get("reactions"))
    if like_count is None:
        return None

    comment_count = _to_int(raw.get("comments_attr"))
    if comment_count is None:
        comment_count = _to_int(raw.get("comments_text"))
    # 반응은 있는데 댓글 표기가 없으면 댓글이 0건인 글이다.
    if comment_count is None:
        comment_count = 0

    return {
        "like_count": like_count,
        "comment_count": comment_count,
        "metrics_updated_at": datetime.now().isoformat(timespec="milliseconds"),
    }


def fetch_metrics(page, activity_id: str, settle_ms: int = 2500) -> dict | None:
    """열려 있는 Playwright page로 한 건의 지표를 읽는다.

    성공하면 지표 dict, 실패하면 None. 호출자가 실패 이력을 기록한다.
    """
    url = build_post_url(activity_id)
    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
    if response is not None and response.status >= 400:
        return None
    page.wait_for_timeout(settle_ms)
    return parse_metrics_from_dom(page.evaluate(_EXTRACT_JS))


def new_anonymous_context(browser):
    """storage_state 없이 비로그인 컨텍스트를 연다."""
    return browser.new_context(
        user_agent=BROWSER_USER_AGENT,
        locale=BROWSER_LOCALE,
        viewport=BROWSER_VIEWPORT,
    )


def polite_sleep(min_seconds: float = 4.0, max_seconds: float = 6.0) -> None:
    """요청 간 지연. IP 단위 속도 제한을 피하기 위한 것이다(계획 4.2절)."""
    time.sleep(random.uniform(min_seconds, max_seconds))


# --- 갱신 대상 선정 --------------------------------------------------
#
# 판정 로직 자체는 `utils/metric_refresh.py` 로 승격했다 - Threads·YouTube 도
# 같은 정책을 쓰는데 세 번 복붙하면 정책이 세 벌로 갈라진다.
# 여기 남는 것은 LinkedIn 고유의 두 가지뿐이다: activity_id 로 식별한다는 것과
# 파라미터 상수의 하위 호환 별칭.

FRESH_POST_DAYS = metric_refresh.PLATFORM_POLICIES["linkedin"]["fresh_post_days"]
REFRESH_AFTER_DAYS = metric_refresh.PLATFORM_POLICIES["linkedin"]["refresh_after_days"]
DEFAULT_RUN_LIMIT = metric_refresh.PLATFORM_POLICIES["linkedin"]["run_limit"]


def _identity(post):
    return extract_activity_id(post.get("url"))


def classify_target(post, now=None, failure_counts=None, max_failures=3):
    """게시글 하나의 갱신 우선순위를 판정한다.

    반환값은 (순위, 사유). 순위가 None 이면 이번 실행에서 건드리지 않는다.
    """
    return metric_refresh.classify_target(
        post,
        fresh_post_days=FRESH_POST_DAYS,
        refresh_after_days=REFRESH_AFTER_DAYS,
        now=now,
        identity=_identity,
        failure_counts=failure_counts,
        max_failures=max_failures,
        identity_reason="no-activity-id",
    )


def select_targets(posts, now=None, limit=DEFAULT_RUN_LIMIT, failure_counts=None):
    """갱신할 게시글을 우선순위 순으로 고른다.

    limit 이 None 이면 상한 없이 전부 반환한다(백필용).
    """
    return metric_refresh.select_targets(
        posts,
        "linkedin",
        now=now,
        limit=limit,
        identity=_identity,
        failure_counts=failure_counts,
    )
