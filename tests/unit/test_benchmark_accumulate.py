"""벤치마킹 수집분의 누적 보존(W1).

Threads·LinkedIn 벤치마킹 수집기는 이번 실행분만 새 파일로 썼고,
`total_scrap.merge_results()` 는 폴더의 최신 파일 하나만 읽는다. 두 성질이
겹치면 수집할 때마다 직전 수집분이 통합본에서 사라진다.

계획: _docs/20260908_01 (W1)
"""

import json
import os

import pytest

from utils.benchmark_store import (
    KEEP_LIMIT,
    atomic_save_json,
    latest_full_file,
    load_existing_posts,
    merge_and_cap,
)

pytestmark = pytest.mark.unit


def _post(code, account, created_at, like_count=0):
    return {
        "code": code,
        "platform_id": code,
        "sns_platform": "threads",
        "username": account,
        "created_at": created_at,
        "date": created_at.split(" ")[0],
        "like_count": like_count,
        "is_saved": False,
        "benchmark_accounts": [account],
    }


def test_merge_keeps_existing_and_prefers_incoming_on_overlap():
    existing = [_post(f"e{i}", "acct", f"2026-09-0{i} 10:00:00", like_count=1) for i in range(1, 6)]
    # 겹치는 2편은 code 가 같고 좋아요만 최신이다.
    incoming = [
        _post("e4", "acct", "2026-09-04 10:00:00", like_count=99),
        _post("e5", "acct", "2026-09-05 10:00:00", like_count=99),
        _post("n1", "acct", "2026-09-07 10:00:00"),
        _post("n2", "acct", "2026-09-08 10:00:00"),
        _post("n3", "acct", "2026-09-09 10:00:00"),
    ]

    posts, removed = merge_and_cap(existing, incoming)

    assert len(posts) == 8, "기존 5 + 신규 3(겹침 2 제외) = 8편"
    assert removed == {}
    by_code = {p["code"]: p for p in posts}
    assert by_code["e4"]["like_count"] == 99, "겹친 글은 이번 수집분이 이긴다"
    assert by_code["e5"]["like_count"] == 99
    assert {"e1", "e2", "e3"} <= set(by_code), "기존 글이 사라지지 않는다"


def test_merge_caps_per_account_and_drops_oldest():
    existing = [
        _post(f"old{i:02d}", "acct", f"2026-08-{i:02d} 10:00:00")
        for i in range(1, 31)
    ]
    incoming = [
        _post(f"new{i}", "acct", f"2026-09-0{i} 10:00:00") for i in range(1, 6)
    ]

    posts, removed = merge_and_cap(existing, incoming)

    assert len(posts) == KEEP_LIMIT
    assert removed == {"acct": 5}
    codes = {p["code"] for p in posts}
    # 잘려나간 것은 가장 오래된 5편이다.
    assert {"old01", "old02", "old03", "old04", "old05"}.isdisjoint(codes)
    assert {"new1", "new2", "new3", "new4", "new5"} <= codes


def test_cap_is_per_account_not_global():
    existing = (
        [_post(f"a{i:02d}", "acct_a", f"2026-08-{i:02d} 10:00:00") for i in range(1, 21)]
        + [_post(f"b{i:02d}", "acct_b", f"2026-08-{i:02d} 10:00:00") for i in range(1, 21)]
    )

    posts, removed = merge_and_cap(existing, [])

    assert removed == {}, "계정당 20편이라 상한 30편에 닿지 않는다"
    assert len(posts) == 40


def test_inactive_account_history_survives():
    """수집 대상에서 빠진 계정의 과거분도 남는다."""
    existing = [_post("gone1", "turned_off", "2026-08-01 10:00:00")]
    incoming = [_post("live1", "still_on", "2026-09-08 10:00:00")]

    posts, _ = merge_and_cap(existing, incoming)

    assert {p["code"] for p in posts} == {"gone1", "live1"}


def test_posts_without_benchmark_mark_are_preserved_without_cap():
    legacy = [
        {"code": f"L{i}", "created_at": f"2026-07-{i:02d} 10:00:00"}
        for i in range(1, 41)
    ]

    posts, removed = merge_and_cap(legacy, [])

    assert removed == {}
    assert len(posts) == 40, "계정 표식이 없으면 상한을 적용하지 않는다"


def test_load_existing_returns_empty_when_no_file(tmp_path):
    assert load_existing_posts(str(tmp_path), "threads_user_full_") == []
    assert latest_full_file(str(tmp_path), "threads_user_full_") is None


def test_load_existing_ignores_broken_json(tmp_path):
    path = tmp_path / "threads_user_full_20260908.json"
    path.write_text("{ this is not json", encoding="utf-8")

    assert load_existing_posts(str(tmp_path), "threads_user_full_") == []


def test_latest_full_file_picks_newest_by_filename_date(tmp_path):
    for stamp in ("20260901", "20260908", "20260905"):
        (tmp_path / f"threads_user_full_{stamp}.json").write_text(
            json.dumps({"posts": []}), encoding="utf-8"
        )
    # 날짜가 아닌 이름은 후보가 아니다.
    (tmp_path / "threads_user_full_backup.json").write_text("{}", encoding="utf-8")

    latest = latest_full_file(str(tmp_path), "threads_user_full_")

    assert latest is not None
    assert os.path.basename(latest) == "threads_user_full_20260908.json"


def test_atomic_save_leaves_original_intact_on_failure(tmp_path):
    path = tmp_path / "threads_user_full_20260908.json"
    original = {"posts": [_post("keep", "acct", "2026-09-01 10:00:00")]}
    assert atomic_save_json(str(path), original) is True

    class Unserializable:
        pass

    # 직렬화 도중 터진다. 원본이 잘리면 안 된다.
    assert atomic_save_json(str(path), {"posts": [Unserializable()]}) is False

    with open(path, "r", encoding="utf-8-sig") as handle:
        assert json.load(handle)["posts"][0]["code"] == "keep"


def test_round_trip_through_disk(tmp_path):
    """저장 → 다시 읽기 → 병합이 이어진다."""
    directory = str(tmp_path)
    first = [_post("p1", "acct", "2026-09-01 10:00:00")]
    assert atomic_save_json(
        os.path.join(directory, "threads_user_full_20260901.json"),
        {"metadata": {}, "posts": first},
    )

    existing = load_existing_posts(directory, "threads_user_full_")
    posts, _ = merge_and_cap(existing, [_post("p2", "acct", "2026-09-08 10:00:00")])

    assert [p["code"] for p in posts] == ["p2", "p1"], "최신순으로 정렬된다"
