"""벤치마킹 소속 표식 재계산(utils/benchmark_match.py).

계획: _docs/20260910_01 (W1 T1-a)

플랫폼마다 저자를 담는 칸이 다르다는 것이 이 모듈의 전부다. 그 차이를 케이스로
고정한다 - 실측에서 나온 실제 값 모양을 그대로 쓴다.
"""

from utils.benchmark_match import (
    apply_benchmark_marks,
    build_match_index,
    match_account_id,
    normalize_key,
)


ACCOUNTS = [
    {
        "id": "seungpil",
        "name": "이승필",
        "status": "active",
        "channels": {"linkedin": "seungpil"},
        # 실측: 피드 수집은 불투명 ID, 벤치마킹 수집은 표시명을 username 에 넣는다.
        "match_keys": {"linkedin": ["ACoAAChsCqABHbZtEaJtYtkT7lT7f1V9dwBlyIE", "seungpil"]},
    },
    {
        "id": "marketer_ai_seulki",
        "name": "강슬기",
        "status": "off",
        "channels": {"threads": "@marketer.ai.seulki"},
        "match_keys": {"threads": ["marketer.ai.seulki"]},
    },
    {
        "id": "jangpm",
        "name": "일잘러 장피엠",
        "status": "active",
        "channels": {"youtube": "@jangpm"},
        "match_keys": {"youtube": ["UCjangpmChannelId0000000"]},
    },
    {
        "id": "themodellers",
        "name": "뺀 계정",
        "status": "excluded",
        "channels": {"threads": "@themodellers"},
        "match_keys": {"threads": ["themodellers"]},
    },
]


def test_normalize_key_strips_at_and_case():
    assert normalize_key("@Handle") == "handle"
    assert normalize_key("  UCabc  ") == "ucabc"
    assert normalize_key(None) == ""


def test_index_skips_excluded_but_keeps_off():
    index = build_match_index(ACCOUNTS)
    # 꺼둔 계정도 과거에 모은 글을 가리켜야 한다. 켜고 끄는 것은 화면 판정이다.
    assert index[("threads", "marketer.ai.seulki")] == "marketer_ai_seulki"
    # 후보에서 아예 뺀 계정만 인덱스에 없다.
    assert ("threads", "themodellers") not in index


def test_linkedin_matches_both_opaque_id_and_display_name():
    index = build_match_index(ACCOUNTS)
    feed_post = {
        "sns_platform": "linkedin",
        "username": "ACoAAChsCqABHbZtEaJtYtkT7lT7f1V9dwBlyIE",
        "display_name": "Seungpil Lee",
    }
    benchmark_post = {
        "sns_platform": "linkedin",
        "username": "seungpil",
        "display_name": "Seungpil Lee",
    }
    assert match_account_id(feed_post, index) == "seungpil"
    assert match_account_id(benchmark_post, index) == "seungpil"


def test_youtube_matches_channel_id_not_display_name():
    index = build_match_index(ACCOUNTS)
    post = {
        "sns_platform": "youtube",
        # username 은 채널 표시명이라 @handle 과 이어지지 않는다.
        "username": "일잘러 장피엠",
        "channel_id": "UCjangpmChannelId0000000",
    }
    assert match_account_id(post, index) == "jangpm"


def test_no_match_for_unrelated_author():
    index = build_match_index(ACCOUNTS)
    post = {"sns_platform": "linkedin", "username": "ACoAA_someone_else", "display_name": "Soyeong Choi"}
    assert match_account_id(post, index) is None


def test_name_similarity_does_not_match():
    """동명이인 방어. 이름 문자열은 런타임 판정에 쓰지 않는다(SPEC D12)."""
    index = build_match_index(ACCOUNTS)
    post = {"sns_platform": "linkedin", "username": "ACoAA_other", "display_name": "이승필"}
    assert match_account_id(post, index) is None


def test_apply_marks_adds_and_preserves_existing():
    posts = [
        {"sns_platform": "linkedin", "username": "ACoAAChsCqABHbZtEaJtYtkT7lT7f1V9dwBlyIE"},
        {"sns_platform": "linkedin", "username": "seungpil", "benchmark_accounts": ["seungpil"]},
        {"sns_platform": "threads", "username": "marketer.ai.seulki", "benchmark_accounts": ["someone"]},
        {"sns_platform": "threads", "username": "nobody"},
    ]
    added = apply_benchmark_marks(posts, ACCOUNTS)

    assert posts[0]["benchmark_accounts"] == ["seungpil"]
    # 이미 붙어 있으면 중복으로 더하지 않는다.
    assert posts[1]["benchmark_accounts"] == ["seungpil"]
    # 기존 표식을 지우지 않고 합집합으로 더한다.
    assert posts[2]["benchmark_accounts"] == ["someone", "marketer_ai_seulki"]
    assert "benchmark_accounts" not in posts[3] or not posts[3]["benchmark_accounts"]
    assert added == {"seungpil": 1, "marketer_ai_seulki": 1}


def test_empty_accounts_is_noop():
    posts = [{"sns_platform": "threads", "username": "marketer.ai.seulki"}]
    assert apply_benchmark_marks(posts, []) == {}
    assert not posts[0].get("benchmark_accounts")
