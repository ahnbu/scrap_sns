"""플랫폼 중립 지표 갱신 정책(utils/metric_refresh.py) 단위 테스트.

LinkedIn 전용이던 판정 로직을 승격한 모듈이다. 세 플랫폼이 같은 규칙을 쓰되
파라미터만 다르다는 것이 핵심이므로, 그 경계를 값으로 고정한다.

계획: _docs/20260826_02_뷰어정리-유튜브확대-지표갱신-웨이브계획.md (W5)
"""

from datetime import datetime, timedelta

import pytest

from utils import metric_refresh

NOW = datetime(2026, 8, 26, 12, 0, 0)


def _post(**overrides):
    base = {
        "sns_platform": "threads",
        "code": "ABC123",
        "created_at": (NOW - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
        "like_count": 10,
        "metrics_updated_at": (NOW - timedelta(days=1)).isoformat(),
    }
    base.update(overrides)
    return base


def _classify(post, platform="threads", **kwargs):
    policy = metric_refresh.get_policy(platform)
    return metric_refresh.classify_target(
        post,
        fresh_post_days=policy["fresh_post_days"],
        refresh_after_days=policy["refresh_after_days"],
        now=NOW,
        **kwargs,
    )


class TestPolicies:
    def test_three_platforms_are_defined(self):
        assert set(metric_refresh.PLATFORM_POLICIES) == {"linkedin", "threads", "youtube"}

    def test_threads_is_shorter_than_linkedin(self):
        """관측이 0건이라 짧게 잡아 먼저 쌓는다 - 계획서 W5 근거."""
        threads = metric_refresh.get_policy("threads")
        linkedin = metric_refresh.get_policy("linkedin")
        assert threads["fresh_post_days"] < linkedin["fresh_post_days"]
        assert threads["refresh_after_days"] < linkedin["refresh_after_days"]

    def test_threads_run_limit_is_account_risk_bound(self):
        """Threads 만 로그인 세션으로 읽는다. 상한이 시간이 아니라 계정 리스크로 정해진다."""
        assert metric_refresh.get_policy("threads")["run_limit"] == 50

    def test_youtube_has_no_run_limit(self):
        """videos.list 가 50건 배치라 전량 갱신해도 API 호출이 몇 번뿐이다."""
        assert metric_refresh.get_policy("youtube")["run_limit"] is None

    def test_unknown_platform_raises_instead_of_defaulting(self):
        """조용히 LinkedIn 값을 쓰면 잘못된 주기로 남의 계정을 두드리게 된다."""
        with pytest.raises(KeyError):
            metric_refresh.get_policy("mastodon")


class TestClassifyTarget:
    def test_missing_metrics_is_first_priority(self):
        rank, reason = _classify(_post(like_count=None))
        assert rank == 1
        assert reason == "missing-metrics"

    def test_zero_is_a_real_metric_not_missing(self):
        rank, _reason = _classify(_post(like_count=0))
        assert rank is None

    def test_fresh_post_never_updated_is_second_priority(self):
        rank, reason = _classify(_post(metrics_updated_at=None))
        assert rank == 2
        assert reason == "fresh-never-updated"

    def test_stale_fresh_post_is_third_priority(self):
        post = _post(metrics_updated_at=(NOW - timedelta(days=6)).isoformat())
        rank, reason = _classify(post)
        assert rank == 3
        assert reason == "stale-fresh-post"

    def test_recently_updated_is_skipped(self):
        rank, reason = _classify(_post())
        assert rank is None
        assert reason == "up-to-date"

    def test_old_post_is_settled(self):
        """게시 100일 넘은 글은 재수집해도 거의 안 변한다(실측 83건 중 8건)."""
        post = _post(created_at=(NOW - timedelta(days=200)).strftime("%Y-%m-%d"))
        rank, reason = _classify(post)
        assert rank is None
        assert reason == "settled"

    def test_unknown_created_at_is_skipped(self):
        rank, reason = _classify(_post(created_at=None))
        assert rank is None
        assert reason == "settled"

    def test_failure_limit_stops_retrying(self):
        rank, reason = _classify(
            _post(like_count=None),
            identity=lambda post: post.get("code"),
            failure_counts={"ABC123": 3},
        )
        assert rank is None
        assert reason == "failure-limit"

    def test_identity_reason_is_caller_supplied(self):
        rank, reason = _classify(
            _post(code=None),
            identity=lambda post: post.get("code"),
            identity_reason="no-activity-id",
        )
        assert rank is None
        assert reason == "no-activity-id"

    def test_threads_boundary_is_shorter_than_linkedin(self):
        """게시 20일 글은 LinkedIn 에선 대상이고 Threads 에선 아니다."""
        post = _post(
            created_at=(NOW - timedelta(days=20)).strftime("%Y-%m-%d"),
            metrics_updated_at=(NOW - timedelta(days=10)).isoformat(),
        )
        assert _classify(post, platform="threads")[0] is None
        assert _classify(post, platform="linkedin")[0] == 3


class TestSelectTargets:
    def test_limit_defaults_to_platform_policy(self):
        posts = [_post(code=f"C{i}", like_count=None) for i in range(80)]
        selected = metric_refresh.select_targets(posts, "threads", now=NOW, platform_field=None)
        assert len(selected) == 50

    def test_none_limit_returns_everything(self):
        posts = [_post(code=f"C{i}", like_count=None) for i in range(80)]
        selected = metric_refresh.select_targets(
            posts, "threads", now=NOW, limit=None, platform_field=None
        )
        assert len(selected) == 80

    def test_priority_order_is_preserved(self):
        missing = _post(code="missing", like_count=None)
        never = _post(code="never", metrics_updated_at=None)
        stale = _post(code="stale", metrics_updated_at=(NOW - timedelta(days=6)).isoformat())
        selected = metric_refresh.select_targets(
            [stale, never, missing], "threads", now=NOW, platform_field=None
        )
        assert [p["code"] for p in selected] == ["missing", "never", "stale"]

    def test_other_platforms_are_filtered_out(self):
        mine = _post(code="mine", like_count=None)
        theirs = _post(code="theirs", like_count=None, sns_platform="linkedin")
        selected = metric_refresh.select_targets([mine, theirs], "threads", now=NOW)
        assert [p["code"] for p in selected] == ["mine"]


class TestChangeSummary:
    def _key(self, post):
        return post.get("code")

    def test_counts_refreshed_and_changed(self):
        before = [
            {"code": "a", "like_count": 10, "metrics_updated_at": "2026-08-20T00:00:00"},
            {"code": "b", "like_count": 5, "metrics_updated_at": "2026-08-20T00:00:00"},
        ]
        after = [
            {"code": "a", "like_count": 28, "metrics_updated_at": "2026-08-26T00:00:00"},
            {"code": "b", "like_count": 5, "metrics_updated_at": "2026-08-26T00:00:00"},
        ]
        stats = metric_refresh.count_metric_changes(before, after, self._key)
        assert stats == {"refreshed": 2, "changed": 1, "max_delta": 18}

    def test_untouched_posts_are_not_counted_as_refreshed(self):
        """값이 복사만 된 글을 갱신으로 세면 이 로그가 거짓말이 된다."""
        same = [{"code": "a", "like_count": 10, "metrics_updated_at": "2026-08-20T00:00:00"}]
        stats = metric_refresh.count_metric_changes(same, list(same), self._key)
        assert stats["refreshed"] == 0

    def test_new_posts_are_ignored(self):
        before = []
        after = [{"code": "new", "like_count": 3, "metrics_updated_at": "2026-08-26T00:00:00"}]
        stats = metric_refresh.count_metric_changes(before, after, self._key)
        assert stats["refreshed"] == 0

    def test_log_line_is_empty_when_nothing_refreshed(self):
        assert metric_refresh.format_refresh_log({"refreshed": 0, "changed": 0}) == ""

    def test_log_line_shape_matches_server_filter(self):
        line = metric_refresh.format_refresh_log(
            {"refreshed": 12, "changed": 3, "max_delta": 18}
        )
        assert line == "지표 갱신 12건 · 값이 바뀐 글 3건 (최대 +18)"
