"""후보 풀 동기화의 보존 규칙.

이 규칙이 깨지면 도구를 못 쓴다 - 동기화를 돌릴 때마다 내가 켠 설정이
초기화되고, 뺀 계정이 되살아난다(R9·R10). 계획: _docs/20260906_01 (P2)
"""

import importlib.util
import os

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "sync_benchmark_accounts.py",
)
_spec = importlib.util.spec_from_file_location("sync_benchmark_accounts", _MODULE_PATH)
assert _spec and _spec.loader
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)

merge = sync.merge_preserving_user_settings


def _incoming(account_id="a", status="active", limit=5, memo="", purpose="형식학습"):
    return {
        "id": account_id,
        "name": account_id,
        "status": status,
        "limit": limit,
        "memo": memo,
        "purpose": purpose,
        "channels": {"youtube": f"@{account_id}"},
        "match_keys": {"youtube": ["UC_seed"]},
    }


def test_user_settings_survive_resync():
    existing = [_incoming(status="off", limit=30, memo="내 메모", purpose="선점소재")]
    merged, report = merge(existing, [_incoming(status="active", limit=5)])

    account = merged[0]
    assert account["status"] == "off"
    assert account["limit"] == 30
    assert account["memo"] == "내 메모"
    assert account["purpose"] == "선점소재"
    assert report["kept"] == 1


def test_resync_refreshes_code_owned_fields():
    """사용자 소유가 아닌 값은 갱신돼야 한다 - 주소·매칭키가 굳으면 소용없다."""
    existing = [_incoming(status="off")]
    existing[0]["match_keys"] = {"youtube": ["UC_old"]}

    incoming = _incoming(status="active")
    incoming["match_keys"] = {"youtube": ["UC_new"]}

    merged, _ = merge(existing, [incoming])
    assert merged[0]["match_keys"] == {"youtube": ["UC_new"]}
    assert merged[0]["status"] == "off"


def test_excluded_account_is_not_revived():
    """뺀 계정이 소스에 남아 있어도 다시 올리지 않는다(R10).

    themodellers 가 실제 사례다 - 수집 데이터에 9건이 남아 있어 이 규칙이
    없으면 동기화마다 후보로 되살아난다.
    """
    existing = [_incoming(status="excluded", memo="뺀 이유")]
    merged, report = merge(existing, [_incoming(status="active")])

    assert merged[0]["status"] == "excluded"
    assert merged[0]["memo"] == "뺀 이유"
    assert report["skipped_excluded"] == 1
    assert report["kept"] == 0


def test_account_missing_from_source_is_kept_and_flagged():
    """소스에서 사라져도 지우지 않는다 - 수집한 글이 가리킬 계정을 잃는다."""
    existing = [_incoming("gone", status="active")]
    merged, report = merge(existing, [_incoming("still_here")])

    gone = next(a for a in merged if a["id"] == "gone")
    assert gone["orphaned"] is True
    assert report["orphaned"] == 1
    assert report["added"] == 1


def test_new_account_is_added_as_is():
    merged, report = merge([], [_incoming("brand_new", status="off")])

    assert merged[0]["id"] == "brand_new"
    assert merged[0]["status"] == "off"
    assert report["added"] == 1


def test_merge_is_idempotent():
    incoming = [_incoming("a", status="active"), _incoming("b", status="off")]
    first, _ = merge([], incoming)
    second, _ = merge(first, incoming)

    assert first == second


def test_existing_address_is_not_overwritten_by_seed():
    """이미 들어 있는 주소를 시드 값으로 덮지 않는다.

    시드는 명단이지 주소의 정본이 아니다. LinkedIn 수집기는
    `/in/<slug>/recent-activity/` 를 여는데 시드에 불투명 ID(ACoAA...)가 적혀
    있으면 그 계정 수집이 깨진다 - 화면에서 slug 로 고쳐도 동기화가 매번
    되돌려 놓았다. 계획: _docs/20260908_01 (W3)
    """
    existing = [_incoming("k")]
    existing[0]["channels"] = {"linkedin": "steve0530", "threads": "@k"}

    incoming = _incoming("k")
    incoming["channels"] = {"linkedin": "ACoAA_opaque_id", "threads": "@k"}
    incoming["match_keys"] = {"linkedin": ["ACoAA_opaque_id"]}

    merged, _ = merge(existing, [incoming])

    assert merged[0]["channels"]["linkedin"] == "steve0530"
    # 보존한 주소는 매칭 키에도 남는다 - 안 그러면 계정 필터가 그 글을 놓친다.
    assert merged[0]["match_keys"]["linkedin"] == ["ACoAA_opaque_id", "steve0530"]


def test_seed_fills_only_empty_channel_slots():
    """시드에 새 플랫폼이 추가되면 그 칸은 들어온다."""
    existing = [_incoming("k")]
    existing[0]["channels"] = {"linkedin": "steve0530"}

    incoming = _incoming("k")
    incoming["channels"] = {"linkedin": "ACoAA_opaque_id", "threads": "@newly_added"}

    merged, _ = merge(existing, [incoming])

    assert merged[0]["channels"] == {
        "linkedin": "steve0530",
        "threads": "@newly_added",
    }
    assert "threads" in merged[0]["collectable"]


def test_verify_emptied_channel_is_not_revived():
    """`--verify` 가 열리지 않는다고 비운 칸은 되살리지 않는다."""
    existing = [_incoming("k")]
    existing[0]["channels"] = {"youtube": "@gone"}

    incoming = _incoming("k")
    incoming["channels"] = {}
    incoming["unverified"] = ["youtube"]

    merged, _ = merge(existing, [incoming])

    assert merged[0]["channels"] == {}
    assert merged[0]["collectable"] == []


def test_youtube_handle_is_not_pushed_into_match_keys():
    """YouTube 매칭 키는 channel_id 다 - @handle 을 섞으면 안 된다(SPEC D12)."""
    existing = [_incoming("y")]
    existing[0]["channels"] = {"youtube": "@handle_name"}

    incoming = _incoming("y")
    incoming["match_keys"] = {"youtube": ["UC_real_id"]}

    merged, _ = merge(existing, [incoming])

    assert merged[0]["match_keys"]["youtube"] == ["UC_real_id"]
