"""참여지표 갱신 대상 선정 - 플랫폼 중립 정책.

`utils/linkedin_metrics.py` 에만 있던 판정 로직을 승격한 것이다. Threads·YouTube 에도
같은 정책을 쓰는데 세 번 복붙하면 정책이 세 벌로 갈라진다.

플랫폼별로 다른 것은 세 가지뿐이다.
  1. 갱신 단위를 식별하는 키 (LinkedIn 은 activity_id, Threads 는 code, YouTube 는 video_id)
  2. 신선도·주기·상한 파라미터
  3. "지표를 이미 가졌는가" 판정 필드

나머지 — 순위 규칙, 실패 한도, 정렬 — 는 공통이다.

파라미터 근거:
- LinkedIn 30일/7일: 도입 시점 값을 그대로 유지한다.
- Threads 14일/5일: 짧게 잡아 관측을 먼저 쌓는다. 게시 7일 이내 글을 두 번 읽은
  기록이 레포에 0건이라 "언제까지 자라는가"를 아직 아무도 모른다. 재수집 비용이
  17건 6초 수준이라 짧게 잡는 쪽이 싸다. 관측이 쌓이면 늘린다.
- 게시 100일 이상 글은 재수집해도 거의 안 변한다(83건 중 8건, 변화폭 ±1~5,
  감소 포함). 그래서 신선도 상한 밖은 아예 건드리지 않는다.

계획: _docs/20260826_02_뷰어정리-유튜브확대-지표갱신-웨이브계획.md (W5)
"""

from __future__ import annotations

from datetime import datetime

DEFAULT_MAX_FAILURES = 3

# 플랫폼별 갱신 파라미터. 여기 한 곳에서만 바꾼다.
PLATFORM_POLICIES = {
    "linkedin": {"fresh_post_days": 30, "refresh_after_days": 7, "run_limit": 120},
    # Threads 는 로그인 세션으로 읽으므로 1회 상한이 시간이 아니라 계정 리스크로 정해진다.
    "threads": {"fresh_post_days": 14, "refresh_after_days": 5, "run_limit": 50},
    # YouTube 는 videos.list 가 50건 배치라 전량 갱신해도 API 호출이 몇 번뿐이다.
    # 상한을 두지 않는다(run_limit=None).
    "youtube": {"fresh_post_days": 30, "refresh_after_days": 7, "run_limit": None},
    # 내 게시물. 저장글과 달리 성과 추적 대상이라 "수렴했으니 그만 읽는다"가 성립하지 않는다.
    # fresh_post_days=None 은 신선도 검사 자체를 건너뛴다(작성 30일이 지나도 계속 갱신).
    # run_limit 은 저장글 예산(120건)과 공유하지 않는 전용 슬롯이다 - 공유하면 내 글이
    # 항상 후보에 올라 앞자리를 잠식해 저장글 갱신이 굶는다.
    # 계획: _docs/20260826_03 (3.7)
    "linkedin_own": {"fresh_post_days": None, "refresh_after_days": 7, "run_limit": 20},
}

_DT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_dt(value):
    """수집기마다 다른 시각 표기를 하나로 읽는다. 못 읽으면 None."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "")
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def days_since(value, now):
    parsed = parse_dt(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 86400.0


def get_policy(platform):
    """알 수 없는 플랫폼은 LinkedIn 값을 쓰지 않고 명시적으로 끊는다."""
    key = str(platform or "").strip().lower()
    if key not in PLATFORM_POLICIES:
        raise KeyError(f"갱신 정책이 정의되지 않은 플랫폼: {platform!r}")
    return PLATFORM_POLICIES[key]


def classify_target(
    post,
    *,
    fresh_post_days,
    refresh_after_days,
    now=None,
    identity=None,
    failure_counts=None,
    max_failures=DEFAULT_MAX_FAILURES,
    has_metric=None,
    identity_reason="no-identity",
):
    """게시글 하나의 갱신 우선순위를 판정한다.

    반환값은 (순위, 사유). 순위가 None 이면 이번 실행에서 건드리지 않는다.
    순위가 작을수록 먼저 처리한다.
    """
    now = now or datetime.now()

    key = identity(post) if identity else None
    if identity and not key:
        return None, identity_reason

    if failure_counts and key is not None:
        if failure_counts.get(key, 0) >= max_failures:
            return None, "failure-limit"

    metric_present = has_metric(post) if has_metric else post.get("like_count") is not None

    # 1순위 - 지표가 아예 없다. 커버리지를 먼저 채운다.
    if not metric_present:
        return 1, "missing-metrics"

    # 여기부터는 지표를 이미 가진 글이다. 반응이 수렴했으면 다시 읽지 않는다.
    # 작성일을 알 수 없는 글도 갱신 대상에서 뺀다 - 신선도를 판단할 근거가 없고,
    # 지표는 이미 갖고 있으므로 매 실행마다 다시 읽는 쪽이 더 나쁘다.
    #
    # fresh_post_days 가 None 이면 이 검사를 통째로 건너뛴다. 내 게시물처럼
    # 오래돼도 계속 추적해야 하는 대상이 여기 해당한다(계획 _docs/20260826_03 3.7).
    # 이때는 작성일을 몰라도 탈락시키지 않는다 - 신선도를 안 보기 때문이다.
    if fresh_post_days is not None:
        age_days = days_since(post.get("created_at"), now)
        if age_days is None or age_days > fresh_post_days:
            return None, "settled"

    stale_days = days_since(post.get("metrics_updated_at"), now)

    # 2순위 - 신선도 안인데 갱신 시각이 없다.
    # 갱신 시각 미상은 "오래된 것"으로 보수적으로 취급한다.
    # (이 정책 도입 전에 수집된 레거시 데이터가 여기 해당한다)
    if stale_days is None:
        return 2, "fresh-never-updated"

    # 3순위 - 반응이 아직 늘어나는 구간이면서 마지막 갱신이 오래됐다.
    if stale_days >= refresh_after_days:
        return 3, "stale-fresh-post"

    return None, "up-to-date"


def select_targets(
    posts,
    platform,
    *,
    now=None,
    limit=-1,
    identity=None,
    failure_counts=None,
    max_failures=DEFAULT_MAX_FAILURES,
    has_metric=None,
    platform_field: str | None = "sns_platform",
):
    """갱신할 게시글을 우선순위 순으로 고른다.

    limit 이 -1 이면 플랫폼 기본 상한을 쓴다. None 이면 상한 없이 전부 반환한다(백필용).
    """
    policy = get_policy(platform)
    now = now or datetime.now()
    effective_limit = policy["run_limit"] if limit == -1 else limit
    target_platform = str(platform).strip().lower()

    ranked = []
    for post in posts:
        if platform_field:
            value = str(post.get(platform_field) or "").strip().lower()
            if value != target_platform:
                continue
        rank, _reason = classify_target(
            post,
            fresh_post_days=policy["fresh_post_days"],
            refresh_after_days=policy["refresh_after_days"],
            now=now,
            identity=identity,
            failure_counts=failure_counts,
            max_failures=max_failures,
            has_metric=has_metric,
        )
        if rank is None:
            continue
        ranked.append((rank, post))

    ranked.sort(key=lambda item: item[0])
    selected = [post for _rank, post in ranked]
    if effective_limit is None:
        return selected
    return selected[:effective_limit]


def count_metric_changes(before_posts, after_posts, key_fn, fields=("like_count", "comment_count", "view_count")):
    """갱신 전후로 실제 값이 바뀐 글 수와 최대 증가폭을 센다.

    운영 로그("지표 갱신 N건 · 값이 바뀐 글 M건")의 근거값이다. 이 숫자가 화면에
    매번 보이면 파라미터 재검토 시점을 사람이 달력에 기억할 필요가 없다.
    """
    before = {key_fn(p): p for p in before_posts if key_fn(p)}
    refreshed = 0
    changed = 0
    max_delta = 0

    for post in after_posts:
        key = key_fn(post)
        if not key or key not in before:
            continue
        old = before[key]
        if post.get("metrics_updated_at") != old.get("metrics_updated_at"):
            refreshed += 1
        for field in fields:
            new_value = post.get(field)
            old_value = old.get(field)
            if new_value is None or old_value is None:
                continue
            if new_value != old_value:
                changed += 1
                try:
                    max_delta = max(max_delta, int(new_value) - int(old_value))
                except (TypeError, ValueError):
                    pass
                break

    return {"refreshed": refreshed, "changed": changed, "max_delta": max_delta}


def format_refresh_log(stats):
    """total_scrap.py stdout 에 실을 한 줄. 서버 필터가 이 형식을 인식한다."""
    if not stats or not stats.get("refreshed"):
        return ""
    line = f"지표 갱신 {stats['refreshed']}건 · 값이 바뀐 글 {stats['changed']}건"
    if stats.get("max_delta"):
        line += f" (최대 +{stats['max_delta']})"
    return line
