"""내 게시물 어댑터·병합·정책 테스트.

계획: _docs/20260826_03_내-게시물-성과지표-통합-수집-계획.md (5절 V1~V5)
"""

from __future__ import annotations

import pytest

from utils import metric_refresh
from utils.common import reorder_post
from utils.linkedin_metrics import select_own_targets
from utils.my_posts_adapter import (
    MY_LINKEDIN_MEMBER_ID,
    OWN_POST_SOURCE,
    merge_own_post,
    to_standard_post,
    to_standard_posts,
)
from utils.post_schema import STANDARD_FIELD_ORDER, normalize_post, validate_post


def insight_record(**overrides):
    record = {
        "schema_version": "sns_insight.v1",
        "platform": "linkedin",
        "platform_post_id": "7486376409918185472",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7486376409918185472/",
        "author": "안병욱",
        "text": "본문",
        "created_at": "2026-07-24T20:07:06.272000+09:00",
        "collected_at": "2026-07-25T11:01:50+09:00",
        "metrics": {
            "impressions": 911,
            "reactions": 15,
            "comments": 1,
            "reposts": 1,
        },
    }
    record.update(overrides)
    return record


# --- V1: 어댑터 변환 -------------------------------------------------------


def test_adapter_output_passes_schema_validation():
    post = to_standard_post(insight_record())

    assert validate_post(post) == []
    assert post["is_own_post"] is True
    assert post["sns_platform"] == "linkedin"
    assert post["username"] == MY_LINKEDIN_MEMBER_ID
    assert post["source"] == OWN_POST_SOURCE


def test_adapter_maps_impressions_to_view_count_only():
    """로그인 경로는 노출수만 신뢰한다.

    recent-activity 카드는 반응수를 상위 몇 건만 렌더링한다(실측 5/36).
    그 값을 like_count 로 흘리면 비로그인 경로가 채운 최신 반응수를 덮어쓴다.
    """
    post = to_standard_post(insight_record())

    assert post["view_count"] == 911
    assert post["like_count"] is None
    assert post["comment_count"] is None
    assert post["share_count"] is None


def test_adapter_normalizes_timezone_aware_created_at():
    post = to_standard_post(insight_record())

    assert post["created_at"] == "2026-07-24 20:07:06"
    assert post["date"] == "2026-07-24"


def test_adapter_drops_non_linkedin_and_identityless_records():
    records = [
        insight_record(),
        insight_record(platform="threads"),
        insight_record(platform_post_id=""),
    ]

    assert len(to_standard_posts(records)) == 1


# --- V2: 필드 단위 병합 가드 ------------------------------------------------


def test_merge_preserves_non_login_metrics():
    """로그인 수집 결과가 비로그인이 채운 반응·댓글을 덮지 않는다."""
    existing = to_standard_post(insight_record())
    existing.update({"like_count": 350, "comment_count": 15, "share_count": 4})

    incoming = to_standard_post(insight_record(metrics={"impressions": 40101}))
    merged = merge_own_post(existing, incoming)

    assert merged["like_count"] == 350
    assert merged["comment_count"] == 15
    assert merged["share_count"] == 4
    assert merged["view_count"] == 40101


def test_merge_without_existing_returns_incoming():
    incoming = to_standard_post(insight_record())

    assert merge_own_post(None, incoming) == incoming


# --- V3: 갱신 정책 격리 -----------------------------------------------------


def test_own_policy_ignores_freshness():
    """내 글은 작성 30일이 지나도 갱신 대상에서 빠지지 않는다."""
    policy = metric_refresh.get_policy("linkedin_own")
    assert policy["fresh_post_days"] is None

    old_post = to_standard_post(
        insight_record(created_at="2020-01-01T00:00:00+09:00")
    )
    old_post.update({"like_count": 10, "metrics_updated_at": "2020-01-02T00:00:00"})

    rank, reason = metric_refresh.classify_target(
        old_post,
        fresh_post_days=policy["fresh_post_days"],
        refresh_after_days=policy["refresh_after_days"],
    )
    assert rank is not None
    assert reason != "settled"


def test_saved_post_policy_still_settles_old_posts():
    """저장글 정책은 그대로다 - 내 글 예외가 저장글로 새지 않는다."""
    policy = metric_refresh.get_policy("linkedin")
    old_post = to_standard_post(
        insight_record(created_at="2020-01-01T00:00:00+09:00")
    )
    old_post.update({"like_count": 10, "metrics_updated_at": "2020-01-02T00:00:00"})

    rank, reason = metric_refresh.classify_target(
        old_post,
        fresh_post_days=policy["fresh_post_days"],
        refresh_after_days=policy["refresh_after_days"],
    )
    assert rank is None
    assert reason == "settled"


def test_own_run_limit_is_separate_from_saved_budget():
    own_limit = metric_refresh.get_policy("linkedin_own")["run_limit"]
    saved_limit = metric_refresh.get_policy("linkedin")["run_limit"]

    # 40: 내 글은 68건뿐이고 성과 비교가 목적이라 20 이면 절반이 항상 2주 전 값이 된다.
    # 계획: _docs/20260827_04 (3.5 T5-c)
    assert own_limit == 40
    assert saved_limit == 120
    assert own_limit != saved_limit, "전용 슬롯이라 저장글 예산과 공유하지 않는다"

    posts = []
    for index in range(own_limit + 10):
        post = to_standard_post(insight_record(platform_post_id=str(7480000000000000000 + index)))
        post["url"] = f"https://www.linkedin.com/feed/update/urn:li:activity:{post['platform_id']}/"
        posts.append(post)

    assert len(select_own_targets(posts)) == own_limit


def test_own_selection_does_not_need_platform_field_rename():
    """내 글의 sns_platform 은 여전히 'linkedin' 이다.

    정책 이름(linkedin_own)으로 플랫폼 필드를 매칭하면 아무것도 안 걸리므로
    select_own_targets 는 플랫폼 필터를 끈다. 그 계약을 고정한다.
    """
    post = to_standard_post(insight_record())
    assert post["sns_platform"] == "linkedin"

    assert len(select_own_targets([post])) == 1


# --- V4: 회귀 가드 ----------------------------------------------------------


def test_regression_guard_rejects_partial_collection():
    """부분 수집이 전수 수집을 덮어쓰지 못하게 막는다.

    sns_insight_update 에서 2026-07-15·07-24 두 번 실제로 난 사고다.
    """
    import my_posts_scrap

    with pytest.raises(my_posts_scrap.SnapshotRegression):
        my_posts_scrap.check_regression(36, 5)


def test_regression_guard_allows_normal_variation():
    import my_posts_scrap

    my_posts_scrap.check_regression(36, 35)
    my_posts_scrap.check_regression(36, 40)
    # 첫 수집(기존 0건)은 비교 대상이 없으므로 통과한다.
    my_posts_scrap.check_regression(0, 3)


# --- V5: 스키마 순서·기본값 -------------------------------------------------


def test_is_own_post_defaults_to_false():
    post = normalize_post(
        {
            "sns_platform": "threads",
            "username": "someone",
            "url": "https://www.threads.com/@someone/post/ABC",
            "created_at": "2026-01-01 00:00:00",
            "full_text": "본문",
        }
    )

    assert post["is_own_post"] is False


@pytest.mark.parametrize("field", ["is_own_post", "view_count", "metrics_updated_at"])
def test_common_reorder_shares_field_order_with_schema(field):
    """utils/common.py 의 중복 사본이 정본과 어긋나면 필드 순서가 갈린다."""
    post = {name: None for name in STANDARD_FIELD_ORDER}
    ordered = list(reorder_post(post).keys())

    assert field in ordered
    assert ordered == STANDARD_FIELD_ORDER


# ---------------------------------------------------------------------------
# V25 - 로그인 경로가 metrics_updated_at 을 덮지 않는다 (P9 회귀 가드)
#
# 이 필드는 "지표를 언제 읽었는가"이지 "레코드를 언제 수집했는가"가 아니다.
# 어댑터가 collected_at 으로 덮으면 신선도 정책이 "방금 읽었다"고 오판해
# 지표를 영원히 다시 읽지 않는다.
# 계획: _docs/20260827_04 (3.5 T5-d / V25)
# ---------------------------------------------------------------------------

def test_merge_own_post_preserves_metrics_updated_at():
    existing = {
        "platform_id": "1",
        "like_count": 10,
        "comment_count": 2,
        "metrics_updated_at": "2026-08-20T10:00:00+09:00",
        "view_count": 100,
    }
    incoming = {
        "platform_id": "1",
        "like_count": None,
        "comment_count": None,
        "metrics_updated_at": "2026-08-27T09:00:00+09:00",  # 수집 시각
        "view_count": 150,
    }

    merged = merge_own_post(existing, incoming)

    assert merged["metrics_updated_at"] == "2026-08-20T10:00:00+09:00", (
        "지표 갱신 시각을 수집 시각으로 덮으면 신선도 판정이 거짓말을 한다"
    )
    assert merged["like_count"] == 10, "반응수는 기존대로 보존"
    assert merged["view_count"] == 150, "노출수는 로그인 경로가 갱신"


def test_merge_own_post_uses_incoming_when_no_existing_record():
    incoming = {"platform_id": "1", "metrics_updated_at": "2026-08-27T09:00:00+09:00"}
    merged = merge_own_post(None, incoming)
    assert merged["metrics_updated_at"] == "2026-08-27T09:00:00+09:00", (
        "신규 레코드는 수집 시각을 그대로 쓴다 - like_count 가 없어 어차피 1순위로 뽑힌다"
    )
