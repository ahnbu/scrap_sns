"""제작자 레지스트리 규칙. 계획: _docs/20260911_01 (W4 T4-a~T4-c)."""
import pytest

from utils.creator_registry import (
    apply_links,
    build_creator_match_index,
    handle_from_channel,
    is_safe_creator_id,
    match_creator_id,
    merge_link_request,
    validate_link_request,
)


@pytest.mark.parametrize(
    "platform,value,expected",
    [
        ("threads", '"[@ai.winey_ny](https://www.threads.com/@ai.winey_ny)"', "ai.winey_ny"),
        ("threads", "@Some_Handle", "some_handle"),
        ("youtube", '"[@Chase-H-AI](https://www.youtube.com/@Chase-H-AI)"', "@Chase-H-AI"),
        ("youtube", '"[영상](https://www.youtube.com/watch?v=Lx7Bji_sNWM)"', ""),
        ("x", '"[@chaseai__](https://x.com/chaseai__)"', "chaseai__"),
        ("linkedin", '"[Jinju Park](https://kr.linkedin.com/in/chatdaeri)"', "chatdaeri"),
        ("linkedin", "kook0526", "kook0526"),
        ("threads", "", ""),
    ],
)
def test_handle_from_channel(platform, value, expected):
    assert handle_from_channel(platform, value) == expected


@pytest.mark.parametrize(
    "value,ok",
    [
        ("이승필_사용성연구소", True),
        ("엉클잡스_unclejobs.ai", True),
        ("link_threads_hong", True),
        ("../x", False),
        ("..", False),
        ("a/b", False),
        ("a\\b", False),
        (".hidden", False),
        ("C:x", False),
        ("", False),
        ("x" * 121, False),
    ],
)
def test_is_safe_creator_id(value, ok):
    assert is_safe_creator_id(value) is ok


def _creators():
    return [
        {"id": "홍길동", "name": "홍길동", "profile": True, "channels": {"threads": "hong"}, "match_keys": {"threads": ["hong"]}},
        {"id": "유튜버", "name": "유튜버", "profile": True, "channels": {"youtube": "@tuber"}, "match_keys": {"youtube": ["UC123"]}},
    ]


def test_match_by_keys_not_by_name():
    index = build_creator_match_index(_creators())
    assert match_creator_id({"sns_platform": "threads", "username": "Hong"}, index) == "홍길동"
    assert match_creator_id({"sns_platform": "youtube", "channel_id": "UC123", "username": "아무"}, index) == "유튜버"
    # 표시명이 제작자 이름과 같아도 키가 없으면 잇지 않는다(SPEC 20260906_01 D12).
    assert match_creator_id({"sns_platform": "linkedin", "username": "ACoAAx", "display_name": "홍길동"}, index) is None
    # 유튜브 @handle 칸은 판정 키가 아니다 - 채널 표시명과 우연히 겹칠 수 있다.
    assert match_creator_id({"sns_platform": "youtube", "username": "tuber"}, index) is None


def test_apply_links_extends_existing_and_creates_new():
    links = [
        {"creator_id": "홍길동", "platform": "linkedin", "key": "ACoAAHong", "source": "user"},
        {"creator_id": "link_threads_kim", "name": "김작가", "platform": "threads", "key": "kim", "source": "user"},
        {"creator_id": "link_threads_kim", "name": "김작가", "platform": "x", "key": "kim_x", "source": "user"},
    ]
    creators = _creators()
    merged = apply_links(creators, links)
    assert "linkedin" not in creators[0]["match_keys"]  # 원본은 그대로
    index = build_creator_match_index(merged)
    assert match_creator_id({"sns_platform": "linkedin", "username": "ACoAAHong"}, index) == "홍길동"
    assert match_creator_id({"sns_platform": "x", "username": "kim_x"}, index) == "link_threads_kim"
    new = next(c for c in merged if c["id"] == "link_threads_kim")
    assert new["name"] == "김작가" and new["profile"] is False


def test_validate_link_request_rejects_bad_input():
    assert validate_link_request([])[0] is None
    assert validate_link_request({"accounts": []})[0] is None
    assert validate_link_request({"accounts": [{"platform": "facebook", "key": "a"}]})[0] is None
    assert validate_link_request({"creator_id": "../x", "accounts": [{"platform": "threads", "key": "a"}]})[0] is None
    assert validate_link_request({"accounts": [{"platform": "threads", "key": "a\nb"}]})[0] is None
    assert validate_link_request({"source": "auto", "accounts": [{"platform": "threads", "key": "a"}]})[0] is None


def test_validate_and_merge_link_request_defaults_and_dedupe():
    request, error = validate_link_request(
        {"name": "김작가", "accounts": [{"platform": "twitter", "key": "Kim_X"}, {"platform": "threads", "key": "kim"}]}
    )
    assert error == ""
    assert request["creator_id"] == "link_x_kim_x"
    assert request["accounts"][0]["platform"] == "x"
    links, added = merge_link_request([], request)
    assert added == 2
    links, added = merge_link_request(links, request)
    assert added == 0 and len(links) == 2
