"""내 글 정렬 순서 회귀 가드.

내 글 정렬은 2026-08-27 하루에 두 번 바뀐 영역인데(`_docs/20260827_03` 역순 수정,
`_docs/20260827_04` 두 플랫폼 병합) 순서를 단언하는 테스트가 하나도 없었다.
e2e 는 순서를 보지 않는다.

🔴 방향에 주의한다. 배열은 오름차순으로 정렬해 앞에서부터 sequence_id 를 매기고,
   뷰어는 sequence_id **내림차순**으로 보여준다(`web_viewer/script.js`).
   즉 **platform_sequence_id 가 클수록 화면 위**다.

계획: _docs/20260827_04 (3.7 T3, V1~V6)
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.own_post_order import assign_own_post_order  # noqa: E402


def _post(platform, created_at, crawled_at="2026-08-26 12:00:00"):
    return {
        "sns_platform": platform,
        "created_at": created_at,
        "crawled_at": crawled_at,
        "is_own_post": True,
    }


def _rank(post):
    return post["platform_sequence_id"]


# V1 - 같은 날이면 링크드인이 화면 위 (= 순번이 더 크다)
def test_same_day_linkedin_ranks_above_threads():
    linkedin = _post("linkedin", "2026-08-25 15:34:00")
    threads = _post("threads", "2026-08-25 15:31:00")

    assign_own_post_order([linkedin], [threads])

    assert _rank(linkedin) > _rank(threads), (
        "같은 날 링크드인이 화면 위여야 한다(순번이 더 커야 한다). "
        f"linkedin={_rank(linkedin)} threads={_rank(threads)}"
    )


# V1 - 쓰레드를 먼저 올린 날도 링크드인이 위여야 한다 (작성 시각에 좌우되지 않는다)
def test_same_day_order_is_fixed_even_when_threads_posted_first():
    linkedin = _post("linkedin", "2026-07-03 15:37:00")
    threads = _post("threads", "2026-07-03 15:39:00")  # 쓰레드가 2분 늦게 올라감

    assign_own_post_order([linkedin], [threads])

    assert _rank(linkedin) > _rank(threads), (
        "작성 시각과 무관하게 같은 날은 링크드인이 위여야 한다"
    )


# V1 - 작성 시각이 완전히 같아도 결정적이어야 한다
def test_same_day_same_minute_is_deterministic():
    linkedin = _post("linkedin", "2026-04-23 10:16:00")
    threads = _post("threads", "2026-04-23 10:16:00")

    assign_own_post_order([linkedin], [threads])

    assert _rank(linkedin) > _rank(threads)


# V2 - 날짜가 최신일수록 화면 위
def test_newest_date_ranks_highest():
    old = _post("linkedin", "2025-12-09 11:48:52")
    mid = _post("threads", "2026-05-15 13:11:00")
    new = _post("linkedin", "2026-08-25 15:34:00")

    assign_own_post_order([old, new], [mid])

    assert _rank(new) > _rank(mid) > _rank(old)


# V2 - 두 플랫폼이 날짜순으로 교차한다 (블록이 갈리지 않는다)
def test_two_platforms_interleave_by_date():
    linkedin = [
        _post("linkedin", "2026-08-25 15:34:00"),
        _post("linkedin", "2026-07-24 20:07:00"),
    ]
    threads = [
        _post("threads", "2026-08-25 15:31:00"),
        _post("threads", "2026-07-24 20:02:00"),
    ]

    assign_own_post_order(linkedin, threads)

    on_screen = sorted(linkedin + threads, key=_rank, reverse=True)
    assert [p["sns_platform"] for p in on_screen] == [
        "linkedin",
        "threads",
        "linkedin",
        "threads",
    ], "날짜 내림차순으로 두 플랫폼이 한 쌍씩 교차해야 한다"


# V3 - 한쪽 플랫폼만 있는 날도 제자리에 선다
def test_unpaired_day_keeps_date_position():
    linkedin = [
        _post("linkedin", "2026-08-25 15:34:00"),
        _post("linkedin", "2025-12-09 11:48:52"),  # 쓰레드 시작 전이라 짝이 없다
    ]
    threads = [_post("threads", "2026-05-15 13:11:00")]

    assign_own_post_order(linkedin, threads)

    on_screen = sorted(linkedin + threads, key=_rank, reverse=True)
    assert [p["created_at"][:10] for p in on_screen] == [
        "2026-08-25",
        "2026-05-15",
        "2025-12-09",
    ]


# V4 - 한쪽 묶음이 비어도 기존 동작을 유지한다 (회귀 가드)
def test_empty_threads_group_keeps_linkedin_order():
    linkedin = [
        _post("linkedin", "2026-08-25 15:34:00"),
        _post("linkedin", "2026-07-24 20:07:00"),
    ]

    assign_own_post_order(linkedin, [])

    assert _rank(linkedin[0]) > _rank(linkedin[1]), "최신 글이 화면 위"


def test_both_groups_empty_does_not_raise():
    assert assign_own_post_order([], []) == []


# V5 - 같은 날 같은 플랫폼 2건은 작성 시각으로 결정적 정렬
def test_same_day_same_platform_orders_by_time():
    early = _post("linkedin", "2026-08-25 09:00:00")
    late = _post("linkedin", "2026-08-25 18:00:00")
    threads = _post("threads", "2026-08-25 12:00:00")

    assign_own_post_order([early, late], [threads])

    assert _rank(late) > _rank(early), "같은 날 같은 플랫폼은 늦게 쓴 글이 화면 위"
    assert _rank(early) > _rank(threads), "그래도 링크드인 두 건이 쓰레드보다 위"


# V6 - batch_key 는 두 묶음을 합친 전체의 min
def test_batch_key_is_min_across_both_groups():
    linkedin = _post("linkedin", "2026-08-25 15:34:00", crawled_at="2026-08-26 12:56:09")
    threads = _post("threads", "2026-08-25 15:31:00", crawled_at="2026-08-27 13:35:08")

    assign_own_post_order([linkedin], [threads])

    assert linkedin["_own_batch_key"] == threads["_own_batch_key"], (
        "두 플랫폼이 한 묶음이므로 대표 시각이 같아야 한다"
    )
    assert linkedin["_own_batch_key"] == "2026-08-26 12:56:09", (
        "max 가 아니라 min 이어야 한다 - max 면 수집할 때마다 블록이 최상단으로 튄다"
    )


# V6 - 분리 함수가 임시 필드를 지우지 않는다 (pop 금지 회귀 가드)
def test_batch_key_survives_the_function():
    """`_own_batch_key` 는 save_total() 의 정렬 1차 키다.

    이 함수 안에서 정리하려고 pop 하면 `_saved_at_key()` 가 crawled_at 으로
    폴백해 내 글이 블록을 잃고 흩어진다. 정리 책임은 save_total() 에 있다.
    """
    linkedin = _post("linkedin", "2026-08-25 15:34:00")
    threads = _post("threads", "2026-08-25 15:31:00")

    assign_own_post_order([linkedin], [threads])

    assert "_own_batch_key" in linkedin
    assert "_own_batch_key" in threads


# 구분자가 섞여도 같은 날로 묶인다 ('T' vs ' ')
def test_mixed_datetime_separators_group_by_same_date():
    linkedin = _post("linkedin", "2026-08-25 15:34:00")
    threads = _post("threads", "2026-08-25T15:31:00")  # ISO 'T' 구분자

    assign_own_post_order([linkedin], [threads])

    assert _rank(linkedin) > _rank(threads), (
        "'T'(0x54) > ' '(0x20) 이라 날것 비교하면 순서가 뒤집힌다. "
        "_normalize_ts 를 통과시켜야 한다"
    )
