"""sync_benchmark_accounts 의 두 회귀를 고정한다.

  1. 제작자 프로필의 `aliases` 를 이름 후보로 쓴다 (W1 T1-d)
  2. 확인해둔 YouTube `channel_id` 가 다음 동기화에서 사라지지 않는다 (W1 후속)

둘 다 실측에서 나온 것이다.
  - 강슬기는 시드에 영문 별칭이 없어 LinkedIn 매칭 키가 비어 있었다
  - `--verify` 로 채운 유튜브 키가 병합 한 번에 19 → 18계정으로 줄었다

계획: _docs/20260910_01
"""

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

_spec = importlib.util.spec_from_file_location(
    "sync_benchmark_accounts",
    os.path.join(REPO_ROOT, "scripts", "sync_benchmark_accounts.py"),
)
assert _spec and _spec.loader
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


FRONT_WITH_ALIASES = """---
title: 강슬기
type: creator
aliases:
  - 퇴근후AI
  - Seulki Kang
linkedin: "[seulki-kang](https://linkedin.com/in/seulki-kang)"
---
"""


def test_parse_front_aliases_block_form():
    front = FRONT_WITH_ALIASES.split("---")[1]
    assert sync._parse_front_aliases(front) == ["퇴근후AI", "Seulki Kang"]


def test_parse_front_aliases_inline_form():
    front = '\naliases: ["A Kim", "에이킴"]\nlinkedin: "x"\n'
    assert sync._parse_front_aliases(front) == ["A Kim", "에이킴"]


def test_parse_front_aliases_absent():
    assert sync._parse_front_aliases("\ntitle: x\n") == []


def test_profile_aliases_lookup_by_partial_name():
    profiles = {
        "이승필_사용성연구소": {"channels": {}, "aliases": ["Seungpil Lee"]},
    }
    # 계정 이름은 "이승필", 파일명은 수식이 붙어 있다 - 부분 일치로 찾는다.
    assert sync.profile_aliases_for(profiles, "이승필") == ["Seungpil Lee"]
    assert sync.profile_channels_for(profiles, "이승필") == {}


def test_verified_youtube_channel_id_survives_sync_without_verify():
    """`--verify` 없이 다시 돌려도 UC... 키가 남아야 한다."""
    previous = {
        "id": "seulki",
        "status": "off",
        "channels": {"youtube": "@marketer.ai.seulki"},
        "match_keys": {"youtube": ["UC3VyrNE736jxYfda3uaKdOg"]},
    }
    # incoming 은 --verify 없이 만들어져 youtube 키가 비어 있다.
    incoming = {
        "id": "seulki",
        "status": "active",
        "channels": {"youtube": "@marketer.ai.seulki"},
        "match_keys": {"threads": ["marketer.ai.seulki"]},
    }
    merged, _ = sync.merge_preserving_user_settings([previous], [incoming])
    account = merged[0]
    assert account["match_keys"]["youtube"] == ["UC3VyrNE736jxYfda3uaKdOg"]
    # 사용자가 켠 설정은 previous 가 이긴다.
    assert account["status"] == "off"


def test_incoming_youtube_key_still_wins():
    """incoming 이 키를 만들었으면 그쪽이 최신이다 - 낡은 id 를 남기지 않는다.

    채널이 바뀐 뒤에도 옛 channel_id 가 남으면 남의 글을 가져온다. 보존은
    incoming 이 빈칸일 때만이다.
    """
    previous = {
        "id": "y",
        "status": "off",
        "channels": {"youtube": "@handle"},
        "match_keys": {"youtube": ["UC_old"]},
    }
    incoming = {
        "id": "y",
        "status": "off",
        "channels": {"youtube": "@handle"},
        "match_keys": {"youtube": ["UC_new"]},
    }
    merged, _ = sync.merge_preserving_user_settings([previous], [incoming])
    assert merged[0]["match_keys"]["youtube"] == ["UC_new"]


def test_handle_is_not_promoted_to_youtube_match_key():
    """@handle 은 channel_id 가 아니다. 키로 승격하면 매칭이 틀어진다(SPEC D12)."""
    previous = {"id": "x", "status": "off", "channels": {}, "match_keys": {}}
    incoming = {
        "id": "x",
        "status": "off",
        "channels": {"youtube": "@somehandle"},
        "match_keys": {},
    }
    merged, _ = sync.merge_preserving_user_settings([previous], [incoming])
    assert not (merged[0].get("match_keys") or {}).get("youtube")
