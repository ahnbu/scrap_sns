"""utils/linkedin_metrics.py 단위 테스트.

계획: _docs/20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획.md 4절 3단계
셀렉터 계약(data-num-*)과 0 엣지 케이스를 고정한다.
"""

from datetime import datetime, timedelta

from utils.linkedin_metrics import (
    build_post_url,
    classify_target,
    extract_activity_id,
    parse_metrics_from_dom,
    select_targets,
)


# --- activity id 추출 -------------------------------------------------


def test_extract_activity_id_from_feed_update_url():
    url = (
        "https://www.linkedin.com/feed/update/urn:li:activity:7253208054928744448"
        "?updateEntityUrn=urn%3Ali%3Afs_updateV2%3A%28urn%3Ali%3Aactivity%3A7253208054928744448"
        "%2CFEED_DETAIL%2CEMPTY%2CDEFAULT%2Cfalse%29"
    )

    assert extract_activity_id(url) == "7253208054928744448"


def test_extract_activity_id_from_clean_permalink():
    url = "https://www.linkedin.com/feed/update/urn:li:activity:7411204617524391938/"

    assert extract_activity_id(url) == "7411204617524391938"


def test_extract_activity_id_returns_none_for_unrelated_url():
    assert extract_activity_id("https://www.threads.com/@user/post/ABC") is None


def test_extract_activity_id_handles_empty_input():
    assert extract_activity_id("") is None
    assert extract_activity_id(None) is None


def test_build_post_url_uses_public_permalink_form():
    assert build_post_url("7411204617524391938") == (
        "https://www.linkedin.com/feed/update/urn:li:activity:7411204617524391938/"
    )


# --- DOM 파싱 ---------------------------------------------------------


def test_parse_metrics_reads_both_attributes():
    raw = {"reactions": "1388", "comments_attr": "39", "comments_text": None}

    metrics = parse_metrics_from_dom(raw)

    assert metrics["like_count"] == 1388
    assert metrics["comment_count"] == 39


def test_parse_metrics_strips_thousands_separator():
    raw = {"reactions": "3,828", "comments_attr": "1,548", "comments_text": None}

    metrics = parse_metrics_from_dom(raw)

    assert metrics["like_count"] == 3828
    assert metrics["comment_count"] == 1548


def test_parse_metrics_records_updated_at():
    metrics = parse_metrics_from_dom({"reactions": "5", "comments_attr": "1"})

    assert metrics["metrics_updated_at"]
    assert "T" in metrics["metrics_updated_at"]


def test_parse_metrics_falls_back_to_comment_link_text():
    """댓글 속성이 없으면 소셜 액션 링크 텍스트를 쓴다."""
    raw = {"reactions": "168", "comments_attr": None, "comments_text": "8"}

    metrics = parse_metrics_from_dom(raw)

    assert metrics["comment_count"] == 8


def test_parse_metrics_treats_missing_comments_as_zero():
    """반응은 있는데 댓글 표기가 전혀 없으면 댓글 0건인 글이다."""
    raw = {"reactions": "41", "comments_attr": None, "comments_text": None}

    metrics = parse_metrics_from_dom(raw)

    assert metrics["like_count"] == 41
    assert metrics["comment_count"] == 0


def test_parse_metrics_keeps_zero_reactions():
    """0 은 유효한 지표값이다. falsy 라고 실패로 처리하면 안 된다."""
    raw = {"reactions": "0", "comments_attr": "0", "comments_text": None}

    metrics = parse_metrics_from_dom(raw)

    assert metrics is not None
    assert metrics["like_count"] == 0
    assert metrics["comment_count"] == 0


def test_parse_metrics_returns_none_when_reactions_absent():
    """반응 속성이 없으면 페이지가 지표를 렌더하지 않은 것이므로 실패로 본다."""
    raw = {"reactions": None, "comments_attr": "12", "comments_text": None}

    assert parse_metrics_from_dom(raw) is None


def test_parse_metrics_returns_none_for_non_numeric_reactions():
    raw = {"reactions": "많음", "comments_attr": "3", "comments_text": None}

    assert parse_metrics_from_dom(raw) is None


def test_parse_metrics_returns_none_for_invalid_input():
    assert parse_metrics_from_dom(None) is None
    assert parse_metrics_from_dom("1388") is None


# --- 갱신 대상 선정 (계획 3.4절) --------------------------------------

NOW = datetime(2026, 8, 25, 12, 0, 0)


def _post(**overrides):
    base = {
        "sns_platform": "linkedin",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7411204617524391938/",
        "created_at": (NOW - timedelta(days=3)).isoformat(),
        "like_count": 10,
        "comment_count": 1,
        "metrics_updated_at": NOW.isoformat(),
    }
    base.update(overrides)
    return base


def test_missing_metrics_is_first_priority():
    rank, reason = classify_target(_post(like_count=None), now=NOW)

    assert rank == 1
    assert reason == "missing-metrics"


def test_fresh_post_without_update_time_is_second_priority():
    """갱신 시각 미상은 보수적으로 '오래된 것'으로 본다."""
    rank, reason = classify_target(_post(metrics_updated_at=None), now=NOW)

    assert rank == 2
    assert reason == "fresh-never-updated"


def test_settled_post_without_update_time_is_skipped():
    """레거시 수집분이라도 작성 30일을 넘겼으면 다시 읽지 않는다.

    지표는 이미 갖고 있고 반응도 수렴했다. 갱신 시각이 없다는 이유만으로
    660건을 통째로 다시 읽으면 55분이 든다.
    """
    post = _post(
        created_at=(NOW - timedelta(days=120)).isoformat(),
        metrics_updated_at=None,
    )

    rank, reason = classify_target(post, now=NOW)

    assert rank is None
    assert reason == "settled"


def test_post_without_created_at_is_skipped_when_metrics_exist():
    rank, reason = classify_target(_post(created_at=None), now=NOW)

    assert rank is None
    assert reason == "settled"


def test_fresh_post_with_stale_metrics_is_third_priority():
    post = _post(
        created_at=(NOW - timedelta(days=10)).isoformat(),
        metrics_updated_at=(NOW - timedelta(days=8)).isoformat(),
    )

    rank, reason = classify_target(post, now=NOW)

    assert rank == 3
    assert reason == "stale-fresh-post"


def test_recently_updated_post_is_skipped():
    post = _post(metrics_updated_at=(NOW - timedelta(days=2)).isoformat())

    rank, reason = classify_target(post, now=NOW)

    assert rank is None
    assert reason == "up-to-date"


def test_old_post_is_not_refreshed_even_when_stale():
    """작성 30일을 넘긴 글은 반응이 수렴했으므로 다시 읽지 않는다."""
    post = _post(
        created_at=(NOW - timedelta(days=200)).isoformat(),
        metrics_updated_at=(NOW - timedelta(days=100)).isoformat(),
    )

    rank, reason = classify_target(post, now=NOW)

    assert rank is None
    assert reason == "settled"


def test_zero_like_count_is_not_treated_as_missing():
    """좋아요 0건은 지표가 있는 것이다. 매번 다시 읽으면 안 된다."""
    rank, _reason = classify_target(_post(like_count=0), now=NOW)

    assert rank is None


def test_post_without_activity_id_is_skipped():
    rank, reason = classify_target(_post(url="https://example.com/x"), now=NOW)

    assert rank is None
    assert reason == "no-activity-id"


def test_repeated_failures_are_excluded():
    post = _post(like_count=None)
    counts = {"7411204617524391938": 3}

    rank, reason = classify_target(post, now=NOW, failure_counts=counts)

    assert rank is None
    assert reason == "failure-limit"


def test_failures_below_limit_still_retried():
    post = _post(like_count=None)
    counts = {"7411204617524391938": 2}

    rank, _reason = classify_target(post, now=NOW, failure_counts=counts)

    assert rank == 1


def test_select_targets_orders_by_priority():
    def with_id(activity_id, **kw):
        return _post(
            url=f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/",
            **kw,
        )

    posts = [
        with_id("1", metrics_updated_at=None),  # 2순위
        with_id("2", like_count=None),  # 1순위
        with_id("3"),  # 제외
    ]

    selected = select_targets(posts, now=NOW, limit=None)

    ids = [extract_activity_id(p["url"]) for p in selected]
    assert ids == ["2", "1"]


def test_select_targets_applies_run_limit():
    posts = [
        _post(
            url=f"https://www.linkedin.com/feed/update/urn:li:activity:{i}/",
            like_count=None,
        )
        for i in range(10)
    ]

    selected = select_targets(posts, now=NOW, limit=4)

    assert len(selected) == 4


def test_select_targets_ignores_other_platforms():
    posts = [
        _post(sns_platform="threads", like_count=None),
        _post(sns_platform="linkedin", like_count=None),
    ]

    selected = select_targets(posts, now=NOW, limit=None)

    assert len(selected) == 1
    assert selected[0]["sns_platform"] == "linkedin"
