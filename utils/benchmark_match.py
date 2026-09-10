"""저장된 글이 어느 벤치마킹 계정의 것인지 판정한다.

왜 이 파일이 필요한가
---------------------
`benchmark_accounts` 표식은 **벤치마킹 전용 수집기를 통과한 글에만** 붙는다
(`linkedin_scrap_benchmark.to_standard()`, `threads_scrap_benchmark`,
`youtube_scrap`). 계정을 등록하기 전에 일반 수집기로 모아둔 같은 사람의 글에는
표식이 없다. 뷰어의 벤치마킹 칩은 그 필드 하나만 보므로(`web_viewer/script.js`
`matchesActiveBenchmarkAccount()`), 같은 사람 글이 반쪽만 나온다.

실측(2026-09-10, `total_full_20260910.json` 2,922건): 이승필 25건 중 표식 6건.
전체로는 205건에 표식이 있고, 계정 정보의 `match_keys`·`channels` 로 소급
매칭하면 376건이 된다 - 171건이 누락돼 있었다.

매칭 재료는 이미 `web_viewer/benchmark_accounts.json` 안에 있다. 여기서는 그것을
읽어 글 한 건의 소속을 판정하기만 한다.

이름 문자열로 매칭하지 않는다(SPEC D12)
---------------------------------------
동명이인이 섞인다. 실측으로 확인했다 - 활성 19계정에 이름 유사도를 걸었더니
후보가 나온 것은 CHOI 하나뿐이었고 그마저 Seolhun Choi·Jongwon Choi·Soyeong
Choi·Jay Choi 로 전부 다른 사람이었다. 이름은 `sync_benchmark_accounts.py` 가
후보를 **찾을 때만** 쓰고, 런타임 판정은 `match_keys` 로만 한다.

플랫폼별로 비교 대상이 다르다
----------------------------
  threads/x : `username`
  linkedin  : `username`. 수집 경로에 따라 불투명 ID(`ACoAA...`) 또는 표시명이
              들어 있어 둘 다 키가 될 수 있다
  youtube   : `channel_id`(UC...)가 우선이다. `username` 은 채널 표시명이라
              `@handle` 과 이어지지 않는다

계획: _docs/20260910_01 (W1 T1-a)
"""

from __future__ import annotations

# 계정 주소(`channels`)도 매칭 키로 함께 쓴다. `match_keys` 는 저장글에서
# 역추적해 얻으므로 그 계정의 글을 아직 한 건도 저장하지 않았으면 비어 있다.
PLATFORM_KEYS = ("threads", "x", "linkedin", "youtube")


def normalize_key(value) -> str:
    """비교용 정규화. 앞의 `@` 를 떼고 소문자로 만든다.

    핸들은 `@handle` 로도 `handle` 로도 저장된다 - 둘을 같은 것으로 봐야 한다.
    """
    return str(value or "").strip().lower().lstrip("@")


def build_match_index(accounts) -> dict:
    """{(platform, key): account_id} 인덱스.

    글마다 계정 목록을 훑으면 O(글 × 계정)이 된다. 통합본이 3천 건에 계정이
    스무 개면 6만 번이다. 인덱스를 한 번 만들어 두면 글당 상수 번의 조회로 끝난다.

    `status` 로 거르지 않는다 - 꺼둔 계정도 과거에 모은 글을 가리켜야 한다.
    켜고 끄는 것은 화면에서 판정하며(`matchesActiveBenchmarkAccount`), 표식 자체는
    "누구 글인가"라는 사실이라 계정을 껐다고 사라지지 않는다.
    `excluded` 만 뺀다 - 후보에서 아예 빼기로 한 계정이다.
    """
    index: dict[tuple[str, str], str] = {}
    for account in accounts or []:
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or "").strip()
        if not account_id or account.get("status") == "excluded":
            continue

        for platform, keys in (account.get("match_keys") or {}).items():
            platform_key = normalize_key(platform)
            for key in keys or []:
                normalized = normalize_key(key)
                if normalized:
                    # 먼저 등록된 계정이 이긴다. 키가 겹치면 나중 계정이 남의 글을
                    # 가져가는데, 그건 계정 설정이 잘못된 것이라 여기서 덮어써서
                    # 감출 일이 아니다.
                    index.setdefault((platform_key, normalized), account_id)

        for platform, value in (account.get("channels") or {}).items():
            platform_key = normalize_key(platform)
            normalized = normalize_key(value)
            if normalized:
                index.setdefault((platform_key, normalized), account_id)

    return index


def _candidate_keys(post: dict) -> list:
    """이 글에서 계정 키가 될 수 있는 값들. 플랫폼별로 다르다."""
    platform = normalize_key(post.get("sns_platform"))

    if platform == "youtube":
        # channel_id 가 정본이다. username 은 채널 표시명이라 @handle 과 다르지만,
        # `sync_benchmark_accounts.find_author()` 가 표시명으로 계정을 찾아
        # match_keys 에 넣어둔 경우가 있어 보조로 함께 본다.
        return [post.get("channel_id"), post.get("username"), post.get("user")]

    if platform == "linkedin":
        # 피드 수집은 불투명 ID(ACoAA...), 벤치마킹 수집은 표시명을 username 에
        # 넣는다. 한 사람이 두 값으로 저장돼 있어 둘 다 키가 된다(W2 가 이 이원화
        # 자체를 없애지만, 그 전에 모은 글은 여기서 받아야 한다).
        return [post.get("username"), post.get("user"), post.get("display_name")]

    return [post.get("username"), post.get("user")]


def match_account_id(post: dict, index: dict) -> str | None:
    """이 글이 속한 계정 id. 못 찾으면 None."""
    if not isinstance(post, dict) or not index:
        return None

    platform = normalize_key(post.get("sns_platform"))
    if not platform:
        return None

    for candidate in _candidate_keys(post):
        normalized = normalize_key(candidate)
        if not normalized:
            continue
        account_id = index.get((platform, normalized))
        if account_id:
            return account_id
    return None


def apply_benchmark_marks(posts, accounts) -> dict:
    """글 목록에 소속 표식을 채운다. 이미 붙은 표식은 지우지 않는다.

    합집합으로 더하는 이유: 한 글이 여러 계정에 걸릴 수 있고(같은 사람을 두 계정으로
    등록한 경우), 수집기가 붙여둔 표식이 여기서 못 찾은 것일 수도 있다. 지우는 쪽이
    이득인 경우가 없다.

    반환: {계정 id: 이번에 새로 붙인 건수}. 조용히 늘면 검증과 구분되지 않는다.
    """
    index = build_match_index(accounts)
    added: dict[str, int] = {}
    if not index:
        return added

    for post in posts or []:
        if not isinstance(post, dict):
            continue
        account_id = match_account_id(post, index)
        if not account_id:
            continue
        current = list(post.get("benchmark_accounts") or [])
        if account_id in current:
            continue
        current.append(account_id)
        post["benchmark_accounts"] = current
        added[account_id] = added.get(account_id, 0) + 1

    return added


def report_added(added: dict) -> None:
    """새로 붙인 표식을 드러낸다."""
    if not added:
        print("   🔖 벤치마킹 표식 재계산: 새로 붙은 것 없음")
        return
    total = sum(added.values())
    print(f"   🔖 벤치마킹 표식 재계산: {total}건 추가")
    for account_id, count in sorted(added.items(), key=lambda item: (-item[1], item[0])):
        print(f"      + {account_id}: {count}건")
