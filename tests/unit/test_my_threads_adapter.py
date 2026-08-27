"""내 Threads 게시물 어댑터·이어붙이기·인증 신호 테스트.

계획: _docs/20260827_02_내-쓰레드-글-수집-계획.md (5절 V1~V4·V7)
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from utils.my_threads_adapter import (
    MY_THREADS_USERNAME,
    OWN_POST_SOURCE,
    SELF_REPLY_WINDOW_MINUTES,
    extract_shortcode,
    is_repost,
    merge_body,
    merge_own_post,
    select_continuations,
    to_kst_text,
    to_standard_post,
    to_standard_posts,
)
from utils.post_schema import STANDARD_FIELD_ORDER, validate_post


ROOT_TS = "2026-08-25T06:31:04+0000"


def insight_record(**overrides):
    """Graph API 경로가 만드는 `sns_insight.v1` 레코드 1건."""
    record = {
        "schema_version": "sns_insight.v1",
        "platform": "threads",
        "platform_post_id": "18094123802428773",
        "url": "https://www.threads.com/@byungwook.an/post/DbLFk8VE6Kq",
        "author": MY_THREADS_USERNAME,
        "text": "본문 앞부분",
        "created_at": ROOT_TS,
        "collected_at": "2026-08-27T12:00:00+09:00",
        "metrics": {
            "impressions": 91,
            "likes": 3,
            "replies": 4,
            "reposts": 1,
            "quotes": 0,
        },
        "raw": {
            "source": "threads_mcp",
            "thread": {
                "id": "18094123802428773",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example/img.jpg",
                "permalink": "https://www.threads.com/@byungwook.an/post/DbLFk8VE6Kq",
                "text": "본문 앞부분",
                "timestamp": ROOT_TS,
                "username": MY_THREADS_USERNAME,
            },
        },
    }
    record.update(overrides)
    return record


def reply(text, timestamp, username=MY_THREADS_USERNAME):
    return {"id": "r", "text": text, "timestamp": timestamp, "username": username}


# --- V4: UTC → KST 변환 ----------------------------------------------------


def test_utc_to_kst_crosses_midnight():
    """계획 3.5 검증값. 이 한 건이 어긋나면 날짜 정렬·필터가 전부 밀린다."""
    assert to_kst_text("2026-02-15T15:00:18+0000") == "2026-02-16 00:00:18"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-08-25T06:31:04+0000", "2026-08-25 15:31:04"),
        ("2026-08-25T06:31:04+00:00", "2026-08-25 15:31:04"),
        # 타임존이 없으면 UTC 로 본다. 로컬로 가정하면 9시간 어긋난다.
        ("2026-08-25T06:31:04", "2026-08-25 15:31:04"),
        ("", None),
        (None, None),
        ("깨진값", None),
    ],
)
def test_to_kst_text_variants(value, expected):
    assert to_kst_text(value) == expected


# --- shortcode -------------------------------------------------------------


def test_shortcode_comes_from_permalink_not_numeric_id():
    """`code` 로 원문 URL 을 조립하므로(utils/post_meta.py:62) 숫자 id 를 쓰면 안 된다."""
    post = to_standard_post(insight_record())
    assert post["platform_id"] == "DbLFk8VE6Kq"
    assert post["code"] == "DbLFk8VE6Kq"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.threads.com/@byungwook.an/post/DbLFk8VE6Kq", "DbLFk8VE6Kq"),
        ("https://www.threads.net/@x/post/AbC-1_2?igshid=zz", "AbC-1_2"),
        ("https://www.threads.com/@x", ""),
        ("", ""),
    ],
)
def test_extract_shortcode(url, expected):
    assert extract_shortcode(url) == expected


# --- V1: 리포스트 제외 -----------------------------------------------------


def test_repost_detected():
    record = insight_record()
    record["raw"]["thread"]["media_type"] = "REPOST_FACADE"
    assert is_repost(record) is True
    assert is_repost(insight_record()) is False


def test_reposts_dropped_from_standard_posts():
    keep = insight_record()
    drop = insight_record(
        platform_post_id="17978182280974168",
        url="https://www.threads.com/@byungwook.an/post/ZZZZZZ",
        text="",
    )
    drop["raw"]["thread"]["media_type"] = "REPOST_FACADE"

    posts = to_standard_posts([keep, drop])

    assert [p["platform_id"] for p in posts] == ["DbLFk8VE6Kq"]


def test_other_platform_and_urlless_records_dropped():
    posts = to_standard_posts(
        [
            insight_record(platform="linkedin"),
            insight_record(url=""),
        ]
    )
    assert posts == []


# --- V2: 자기 답글 합치기 --------------------------------------------------


def test_continuations_pick_only_my_recent_replies():
    replies = [
        reply("남의 댓글", "2026-08-25T06:32:00+0000", username="vibe.bizness"),
        reply("이어지는 본문", "2026-08-25T06:31:10+0000"),
        reply("9시간 뒤 대화형 답글", "2026-08-25T15:42:46+0000"),
        reply("   ", "2026-08-25T06:31:20+0000"),
    ]

    picked = select_continuations(ROOT_TS, replies)

    assert [item["text"] for item in picked] == ["이어지는 본문"]


def test_continuations_sorted_by_time():
    replies = [
        reply("두번째", "2026-08-25T06:33:00+0000"),
        reply("첫번째", "2026-08-25T06:31:10+0000"),
    ]
    picked = select_continuations(ROOT_TS, replies)
    assert [item["text"] for item in picked] == ["첫번째", "두번째"]


def test_reply_before_root_is_ignored():
    """원글보다 앞선 시각은 데이터 이상이다."""
    picked = select_continuations(ROOT_TS, [reply("과거", "2026-08-25T06:30:00+0000")])
    assert picked == []


def test_continuations_empty_when_root_time_unparseable():
    assert select_continuations("깨진값", [reply("x", ROOT_TS)]) == []


def test_merge_body_joins_with_blank_line():
    body = merge_body("앞부분", [{"text": "뒷부분"}, {"text": "  "}, {"text": "끝"}])
    assert body == "앞부분\n\n뒷부분\n\n끝"


def test_merged_thread_flag_and_body():
    picked = [{"text": "이어지는 본문"}]
    post = to_standard_post(insight_record(), picked)

    assert post["full_text"] == "본문 앞부분\n\n이어지는 본문"
    assert post["is_merged_thread"] is True


def test_not_merged_when_no_continuations():
    post = to_standard_post(insight_record())
    assert post["is_merged_thread"] is False
    assert post["full_text"] == "본문 앞부분"


def test_continuations_applied_by_api_id_not_shortcode():
    """답글은 숫자 id 로 부르므로 매핑 키도 숫자 id 여야 한다."""
    posts = to_standard_posts(
        [insight_record()],
        {"18094123802428773": [{"text": "이어지는 본문"}]},
    )
    assert posts[0]["full_text"].endswith("이어지는 본문")
    assert posts[0]["is_merged_thread"] is True


# --- V3: 30분 경계 ---------------------------------------------------------


def test_window_boundary_inclusive_at_29m59s():
    picked = select_continuations(ROOT_TS, [reply("포함", "2026-08-25T07:01:03+0000")])
    assert [item["text"] for item in picked] == ["포함"]


def test_window_boundary_excludes_30m01s():
    picked = select_continuations(ROOT_TS, [reply("제외", "2026-08-25T07:01:05+0000")])
    assert picked == []


def test_window_default_is_thirty_minutes():
    assert SELF_REPLY_WINDOW_MINUTES == 30


def test_window_is_overridable():
    late = reply("7분 뒤", "2026-08-25T06:38:04+0000")
    assert select_continuations(ROOT_TS, [late], window_minutes=5) == []
    assert len(select_continuations(ROOT_TS, [late], window_minutes=10)) == 1


# --- 표준 스키마 정합 ------------------------------------------------------


def test_standard_post_shape():
    post = to_standard_post(insight_record())

    assert post["sns_platform"] == "threads"
    assert post["username"] == MY_THREADS_USERNAME
    assert post["source"] == OWN_POST_SOURCE
    assert post["is_own_post"] is True
    assert post["created_at"] == "2026-08-25 15:31:04"
    assert post["date"] == "2026-08-25"
    assert validate_post(post) == []
    assert set(post) <= set(STANDARD_FIELD_ORDER)


def test_metrics_mapped_from_graph_api():
    post = to_standard_post(insight_record())

    assert post["view_count"] == 91
    assert post["like_count"] == 3
    assert post["comment_count"] == 4
    assert post["share_count"] == 1
    assert post["quote_count"] == 0


def test_sequence_id_left_unassigned():
    """어댑터는 순번을 매기지 않는다.

    `normalize_post()` 가 표준 필드를 전부 채우므로 키 자체는 남지만 값은 비어 있어야
    한다. 통합 파일 안에서 다시 매겨지는 로컬 순서값이라 durable identity 가
    아니다(AGENTS.md).
    """
    assert not to_standard_post(insight_record()).get("sequence_id")


# --- 병합 ------------------------------------------------------------------


def test_merge_keeps_existing_metric_when_incoming_is_none():
    existing = to_standard_post(insight_record())
    incoming = to_standard_post(insight_record(metrics={"impressions": None}))

    merged = merge_own_post(existing, incoming)

    assert merged["view_count"] == 91


def test_merge_overwrites_with_fresh_metric():
    existing = to_standard_post(insight_record())
    incoming = to_standard_post(insight_record(metrics={"impressions": 500}))

    assert merge_own_post(existing, incoming)["view_count"] == 500


def test_merge_without_existing_returns_incoming():
    incoming = to_standard_post(insight_record())
    assert merge_own_post(None, incoming) == incoming


def test_merge_ignores_sequence_id():
    existing = dict(to_standard_post(insight_record()), sequence_id=7)
    incoming = dict(to_standard_post(insight_record()), sequence_id=1)

    assert merge_own_post(existing, incoming)["sequence_id"] == 7


# --- V7: 인증 실패 경로 ----------------------------------------------------


class _FakeAuthRequired(RuntimeError):
    pass


def _install_fake_collector(monkeypatch, collect_impl):
    """외부 레포를 건드리지 않고 수집기 모듈만 가짜로 세운다.

    실제 `~/.claude/settings.json` 이나 토큰은 전혀 개입하지 않는다(계획 5절 V7).
    """
    pkg = types.ModuleType("sns_insight_update")
    pkg.__path__ = []  # type: ignore[attr-defined]
    collectors = types.ModuleType("sns_insight_update.collectors")
    collectors.__path__ = []  # type: ignore[attr-defined]
    threads = types.ModuleType("sns_insight_update.collectors.threads")
    threads.ThreadsAuthRequired = _FakeAuthRequired  # type: ignore[attr-defined]
    threads.collect_threads_posts = collect_impl  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "sns_insight_update", pkg)
    monkeypatch.setitem(sys.modules, "sns_insight_update.collectors", collectors)
    monkeypatch.setitem(sys.modules, "sns_insight_update.collectors.threads", threads)


def test_auth_failure_emits_threads_platform_signal(monkeypatch, capsys):
    import my_threads_scrap

    def _raise(**_kwargs):
        raise _FakeAuthRequired("auth/threads.json")

    monkeypatch.setattr(my_threads_scrap, "_ensure_insight_path", lambda: None)
    _install_fake_collector(monkeypatch, _raise)

    with pytest.raises(SystemExit) as excinfo:
        my_threads_scrap.collect()

    assert excinfo.value.code == 86  # utils.auth_status.AUTH_REQUIRED_EXIT_CODE

    line = next(
        ln for ln in capsys.readouterr().out.splitlines()
        if ln.startswith("SNS_AUTH_REQUIRED")
    )
    payload = json.loads(line.split(" ", 1)[1])
    assert payload["platform"] == "threads"
    assert payload["reason"] == "login_required"
    assert payload["scope"] == "my_posts"


def test_collect_returns_records_on_success(monkeypatch):
    import my_threads_scrap

    monkeypatch.setattr(my_threads_scrap, "_ensure_insight_path", lambda: None)
    _install_fake_collector(monkeypatch, lambda **_kwargs: ["ok"])

    assert my_threads_scrap.collect() == ["ok"]


# --- 회귀 가드 -------------------------------------------------------------


def test_regression_guard_rejects_halved_snapshot():
    import my_threads_scrap

    with pytest.raises(my_threads_scrap.SnapshotRegression):
        my_threads_scrap.check_regression(32, 10)


def test_regression_guard_allows_first_run_and_normal_run():
    import my_threads_scrap

    my_threads_scrap.check_regression(0, 32)
    my_threads_scrap.check_regression(32, 31)
