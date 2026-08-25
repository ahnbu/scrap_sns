"""linkedin_scrap.merge_linkedin_full_posts 의 지표 보존 가드 테스트.

계획: _docs/20260825_01_LinkedIn-참여지표-비로그인-수집전환-계획.md 2.5절 / 3.6절

병합은 `{**existing, **post}` 라 새 수집분이 기존값을 덮어쓴다. 저장글 목록 API 는
지표를 주지 않으므로, 가드가 없으면 전체 재수집 한 번에 확보한 지표가 전부 사라진다.
"""

from linkedin_scrap import merge_linkedin_full_posts, preserve_existing_metrics


def _existing_post(**overrides):
    base = {
        "platform_id": "7411204617524391938",
        "sns_platform": "linkedin",
        "username": "someone",
        "full_text": "기존 본문",
        "sequence_id": 12,
        "crawled_at": "2026-08-24T10:00:00.000",
        "like_count": 252,
        "comment_count": 3,
        "metrics_updated_at": "2026-08-24T21:00:00.000",
    }
    base.update(overrides)
    return base


def _scraped_post(**overrides):
    """저장글 목록 API 가 만들어내는 형태 - 지표 키가 아예 없다."""
    base = {
        "platform_id": "7411204617524391938",
        "sns_platform": "linkedin",
        "username": "someone",
        "full_text": "기존 본문",
        "sequence_id": 0,
        "crawled_at": "2026-08-25T12:00:00.000",
    }
    base.update(overrides)
    return base


# --- preserve_existing_metrics 단위 ------------------------------------


def test_guard_carries_over_metrics_when_new_value_is_none():
    merged = {"like_count": None, "comment_count": None, "metrics_updated_at": None}
    existing = {"like_count": 252, "comment_count": 3, "metrics_updated_at": "2026-08-24T21:00:00.000"}

    preserve_existing_metrics(merged, existing)

    assert merged["like_count"] == 252
    assert merged["comment_count"] == 3
    assert merged["metrics_updated_at"] == "2026-08-24T21:00:00.000"


def test_guard_keeps_existing_zero():
    """0 은 유효한 지표값이다. truthy 검사로 구현하면 여기서 깨진다."""
    merged = {"like_count": None, "comment_count": None}
    existing = {"like_count": 0, "comment_count": 0}

    preserve_existing_metrics(merged, existing)

    assert merged["like_count"] == 0
    assert merged["comment_count"] == 0


def test_guard_does_not_overwrite_fresh_value():
    """새로 읽어온 값이 있으면 그것이 이긴다."""
    merged = {"like_count": 300, "comment_count": 0}
    existing = {"like_count": 252, "comment_count": 3}

    preserve_existing_metrics(merged, existing)

    assert merged["like_count"] == 300
    assert merged["comment_count"] == 0


def test_guard_ignores_sentinel_minus_one():
    merged = {"like_count": None}
    existing = {"like_count": -1}

    preserve_existing_metrics(merged, existing)

    assert merged["like_count"] is None


def test_guard_preserves_metrics_updated_at_field():
    """metrics_updated_at 이 보존 대상에서 빠지면 상시 갱신 정책이 고장난다."""
    merged = {"metrics_updated_at": None}
    existing = {"metrics_updated_at": "2026-08-24T21:00:00.000"}

    preserve_existing_metrics(merged, existing)

    assert merged["metrics_updated_at"] == "2026-08-24T21:00:00.000"


# --- merge_linkedin_full_posts 통합 -------------------------------------


def test_merge_keeps_metrics_when_scraped_post_has_no_metric_keys():
    """지표 키가 아예 없는 현재 파서 출력 - 기존값이 살아남아야 한다."""
    final_posts, _new_items, _report = merge_linkedin_full_posts(
        [_existing_post()], [_scraped_post()], "all"
    )

    merged = final_posts[0]
    assert merged["like_count"] == 252
    assert merged["comment_count"] == 3
    assert merged["metrics_updated_at"] == "2026-08-24T21:00:00.000"


def test_merge_keeps_metrics_when_scraped_post_carries_none():
    """normalize_post 를 적용하면 지표가 None 으로 실려온다 - 이때가 진짜 함정이다."""
    scraped = _scraped_post(
        like_count=None, comment_count=None, metrics_updated_at=None
    )

    final_posts, _new_items, _report = merge_linkedin_full_posts(
        [_existing_post()], [scraped], "all"
    )

    merged = final_posts[0]
    assert merged["like_count"] == 252
    assert merged["comment_count"] == 3
    assert merged["metrics_updated_at"] == "2026-08-24T21:00:00.000"


def test_merge_keeps_existing_zero_metrics():
    existing = _existing_post(like_count=0, comment_count=0)
    scraped = _scraped_post(like_count=None, comment_count=None)

    final_posts, _new_items, _report = merge_linkedin_full_posts(
        [existing], [scraped], "all"
    )

    merged = final_posts[0]
    assert merged["like_count"] == 0
    assert merged["comment_count"] == 0


def test_merge_accepts_fresh_metrics_from_consumer():
    """consumer 가 새 지표를 실어오면 그 값으로 갱신된다."""
    scraped = _scraped_post(
        like_count=400, comment_count=11, metrics_updated_at="2026-08-25T12:00:00.000"
    )

    final_posts, _new_items, _report = merge_linkedin_full_posts(
        [_existing_post()], [scraped], "all"
    )

    merged = final_posts[0]
    assert merged["like_count"] == 400
    assert merged["comment_count"] == 11
    assert merged["metrics_updated_at"] == "2026-08-25T12:00:00.000"


def test_merge_does_not_alter_body_or_author():
    final_posts, _new_items, _report = merge_linkedin_full_posts(
        [_existing_post()], [_scraped_post()], "all"
    )

    merged = final_posts[0]
    assert merged["full_text"] == "기존 본문"
    assert merged["username"] == "someone"
    assert merged["sequence_id"] == 12
