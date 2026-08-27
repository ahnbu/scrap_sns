"""내 글(LinkedIn·Threads)의 화면 순서를 정하는 순수 함수.

`total_scrap.py` 안에 인라인으로 두면 테스트할 수 없다 — 그 모듈은 import 시점에
`sys.stdout` 을 교체해서(`total_scrap.py:22-24`) pytest 캡처를 깨기 때문에
단위 테스트에서 import 자체가 불가능하다. `utils/my_threads_adapter.py` 와 같은
패턴으로 여기에 둔다.

계획: _docs/20260827_04 (3.2 T1, 3.3 T2, 3.7 T3)
"""

from __future__ import annotations

#: 같은 날 두 플랫폼이 겹칠 때의 고정 순서.
#
# 🔴 방향에 주의한다. 배열은 오름차순으로 정렬해 앞에서부터 sequence_id 를 매기는데,
#    뷰어는 sequence_id **내림차순**으로 보여준다
#    (`web_viewer/script.js`: `filtered.sort((a, b) => b._seqId - a._seqId)`).
#    즉 **배열에서 뒤에 있을수록 화면 위**다. 링크드인을 화면 위에 두려면
#    배열에서 링크드인이 뒤여야 하므로 값이 더 커야 한다.
#    이 값을 뒤집으면 화면도 뒤집힌다.
OWN_SAME_DAY_ORDER = {"threads": 0, "linkedin": 1}


def normalize_ts(value):
    """플랫폼별 타임스탬프 표기를 문자열 비교 가능한 형태로 맞춘다.

    threads 는 '2026-02-12T18:44:53.240', youtube 는 '2026-08-25 10:55:28' 로
    구분자가 다르다. 'T'(0x54) > ' '(0x20) 이라 같은 날짜에서 유튜브가 항상
    앞서는 왜곡이 생긴다.

    🔴 밀리초는 자르지 않는다. Threads 는 같은 초 안에 여러 건이 찍히는데
    (실측: 2026-02-18T10:58:10.089 / .122) 밀리초를 버리면 그 건들이 동률이 돼
    2차 키로 넘어가면서 기존 순서가 뒤집힌다. 실제로 그 회귀를 만들었다.
    """
    return str(value or "").replace("T", " ")


def assign_own_post_order(own_posts, threads_own_posts):
    """내 글 두 플랫폼을 한 묶음으로 세우고 순번을 매긴다.

    내 글은 프로필을 최신→과거로 훑는다. 그 진행 방향이 crawled_at 과
    sequence_id 양쪽에 역순으로 새겨져 「로컬수집순」 화면이 뒤집힌다.
    (실측: LinkedIn 36건은 crawled_at 이 전부 같아 2차 키가, Threads 32건은
     crawled_at 이 초 단위로 갈려 1차 키가 각각 역순을 만들었다.)

    묶음을 **플랫폼별로 쪼개면** 화면에서 쓰레드 32건을 다 지나야 링크드인이
    나온다 — 같은 날 올린 같은 원고가 32칸 떨어진다. 게다가 블록 위치가
    min(crawled_at) 으로 정해져, 어느 플랫폼을 나중에 수집했느냐에 따라
    위아래가 통째로 뒤집힌다. 그래서 두 묶음을 하나로 합친다.

    정렬 키는 세 단계다.
      1. 작성 **날짜**(앞 10자)  - 오름차순
      2. 플랫폼 고정 순서         - OWN_SAME_DAY_ORDER (같은 날이면 링크드인이 화면 위)
      3. 작성 **시각** 전체       - 같은 날 같은 플랫폼에 2건 이상일 때의 결정적 순서

    batch_key 에 max 가 아니라 **min** 을 쓴다. max 면 수집할 때마다 블록이
    최상단으로 튀어 순서가 계속 흔들린다. min 은 한 번 자리를 잡으면 그 뒤
    수집으로 위로 올라가지 않는다.

    ⚠️ `_own_batch_key` 를 여기서 pop 하지 않는다. 이 필드는 `save_total()` 의
       정렬 1차 키(`_saved_at_key`)가 읽고, 정렬이 끝난 뒤 `save_total()` 이 지운다.
       여기서 먼저 지우면 crawled_at 으로 폴백해 내 글이 블록을 잃고 흩어진다.
    """
    own_all = list(own_posts) + list(threads_own_posts)
    if not own_all:
        return own_all

    batch_key = min(normalize_ts(post.get("crawled_at")) for post in own_all)

    def order_key(post):
        created = normalize_ts(post.get("created_at"))
        platform = str(post.get("sns_platform") or "").lower()
        return (created[:10], OWN_SAME_DAY_ORDER.get(platform, 0), created)

    for rank, post in enumerate(sorted(own_all, key=order_key), start=1):
        post["platform_sequence_id"] = rank
        post["_own_batch_key"] = batch_key
    return own_all
