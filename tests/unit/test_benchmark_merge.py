"""벤치마킹 표식의 양방향 필드 병합(D4-C).

중복 제거는 「먼저 나온 쪽을 남긴다」이고, 배열 순서가 곧 정책이다. 벤치마킹
수집분을 맨 뒤에 두면 기존 저장글이 살아남는데, 그냥 버리면 그 글에
「벤치마킹 계정 소속」 표시가 안 붙어 계정 필터에서 빠진다(R5 위반).

그래서 버리기 전에 표식만 옮긴다. **양방향이어야 한다** - 한쪽만 만들면
「벤치마킹 글을 나중에 북마크」에서 글이 조용히 사라진다(D9-나).

계획: _docs/20260906_01 (P5)
"""

import os

# total_scrap 은 import 하지 않는다 - 모듈 최상단이 콘솔 인코딩을 다시 잡아
# pytest 의 출력 캡처가 깨진다. 소스를 텍스트로 읽어 대조한다.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOTAL_SCRAP_SRC = open(
    os.path.join(_ROOT, "total_scrap.py"), encoding="utf-8"
).read()


def _post(video_id, *, is_saved=True, benchmark=None, source="", channel_id=""):
    return {
        "platform_id": video_id,
        "code": video_id,
        "sns_platform": "youtube",
        "username": "채널명",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "created_at": "2026-09-01 10:00:00",
        "full_text": "본문",
        "source": source,
        "is_saved": is_saved,
        "benchmark_accounts": list(benchmark or []),
        "channel_id": channel_id,
    }


def _merge(posts):
    """merge_results 의 중복 제거 루프만 떼어 재현한다."""
    seen_ids = set()
    seen_pks = set()
    unique = []
    kept_by_id = {}
    marks = {"benchmark": 0, "is_saved": 0}

    def absorb(survivor, dropped):
        incoming = dropped.get("benchmark_accounts") or []
        if incoming:
            current = list(survivor.get("benchmark_accounts") or [])
            merged_ids = sorted(set(current) | set(incoming))
            if merged_ids != current:
                survivor["benchmark_accounts"] = merged_ids
                marks["benchmark"] += 1
        if dropped.get("is_saved") is not False and survivor.get("is_saved") is False:
            survivor["is_saved"] = True
            marks["is_saved"] += 1
        if dropped.get("channel_id") and not survivor.get("channel_id"):
            survivor["channel_id"] = dropped["channel_id"]

    for post in posts:
        pid = str(post.get("platform_id"))
        if pid in seen_ids:
            absorb(kept_by_id[pid], post)
            continue
        unique.append(post)
        seen_ids.add(pid)
        kept_by_id[pid] = post
    return unique, marks


def test_benchmark_mark_moves_onto_existing_saved_post():
    """벤치마킹 → 기존 저장글. source 를 잃지 않고 계정 소속만 얹는다(R5)."""
    saved = _post("vid1", is_saved=True, source="기획new")
    benchmark = _post("vid1", is_saved=False, benchmark=["builderjosh"], source="benchmark:builderjosh")

    unique, marks = _merge([saved, benchmark])

    assert len(unique) == 1
    survivor = unique[0]
    assert survivor["source"] == "기획new", "내가 왜 저장했는지가 날아가면 안 된다"
    assert survivor["is_saved"] is True
    assert survivor["benchmark_accounts"] == ["builderjosh"]
    assert marks["benchmark"] == 1


def test_saved_post_restores_is_saved_on_existing_benchmark_record():
    """저장글 → 기존 벤치마킹 레코드. 반대 방향도 성립해야 한다(D9-나).

    이 방향을 빠뜨리면 벤치마킹 뷰에서 좋은 글을 보고 북마크했을 때
    다음 수집에서 「저장글 아님」으로 오판돼 계정을 끄면 글이 사라진다.
    """
    benchmark = _post("vid2", is_saved=False, benchmark=["pptpro"])
    saved = _post("vid2", is_saved=True, source="기획new")

    unique, marks = _merge([benchmark, saved])

    assert len(unique) == 1
    survivor = unique[0]
    assert survivor["is_saved"] is True, "나중에 북마크한 글이 저장글로 인정돼야 한다"
    assert survivor["benchmark_accounts"] == ["pptpro"]
    assert marks["is_saved"] == 1


def test_two_accounts_on_one_post_are_both_kept():
    """한 글이 두 계정에 걸치는 경우(리포스트·공동출연). 배열이라 둘 다 남는다."""
    first = _post("vid3", is_saved=False, benchmark=["builderjosh"])
    second = _post("vid3", is_saved=False, benchmark=["jangpm"])

    unique, _ = _merge([first, second])

    assert unique[0]["benchmark_accounts"] == ["builderjosh", "jangpm"]


def test_channel_id_is_backfilled_from_dropped_record():
    survivor = _post("vid4", channel_id="")
    dropped = _post("vid4", is_saved=False, benchmark=["heydi"], channel_id="UC_abc")

    unique, _ = _merge([survivor, dropped])

    assert unique[0]["channel_id"] == "UC_abc"


def test_plain_duplicate_does_not_touch_flags():
    """벤치마킹과 무관한 중복은 아무 것도 바꾸지 않는다."""
    first = _post("vid5", source="drive7")
    second = _post("vid5", source="ai.new2")

    unique, marks = _merge([first, second])

    assert unique[0]["source"] == "drive7"
    assert unique[0]["benchmark_accounts"] == []
    assert marks == {"benchmark": 0, "is_saved": 0}


def test_merge_results_reads_benchmark_directory():
    """병합이 벤치마킹 디렉토리를 실제로 소스로 삼는지.

    이 소스를 안 읽으면 벤치마킹 수집분이 통합본에 영원히 안 들어간다.
    linkedin_own 이 같은 함정을 이미 겪었다.
    """
    assert 'OUTPUT_YOUTUBE_BENCHMARK_DIR = os.path.join(PROJECT_ROOT, "output_youtube_user", "python")' in _TOTAL_SCRAP_SRC
    assert 'find_latest_full_file(\n        OUTPUT_YOUTUBE_BENCHMARK_DIR, "youtube_user_full_*.json"\n    )' in _TOTAL_SCRAP_SRC
    assert "+ youtube_bm_posts" in _TOTAL_SCRAP_SRC, "벤치마킹분이 all_posts 에 들어가야 한다"


def test_merge_results_reads_linkedin_benchmark_directory():
    """LinkedIn 벤치마킹분도 같은 함정을 밟지 않는지.

    유튜브 때와 글자 하나 다르지 않은 실패다 - 소스 한 줄이 빠지면 수집은
    되는데 화면에 영원히 안 나온다. 계획: _docs/20260906_03 (W3)
    """
    assert 'OUTPUT_LINKEDIN_BENCHMARK_DIR = os.path.join(PROJECT_ROOT, "output_linkedin_user", "python")' in _TOTAL_SCRAP_SRC
    assert 'find_latest_full_file(\n        OUTPUT_LINKEDIN_BENCHMARK_DIR, "linkedin_user_full_*.json"\n    )' in _TOTAL_SCRAP_SRC
    assert "+ linkedin_bm_posts" in _TOTAL_SCRAP_SRC, "LinkedIn 벤치마킹분이 all_posts 에 들어가야 한다"
    assert "len(linkedin_bm_posts)" in _TOTAL_SCRAP_SRC, "플랫폼 집계에도 들어가야 뷰어 건수와 맞는다"


def test_benchmark_posts_are_last_in_merge_order():
    """배열 순서가 곧 정책이다. 벤치마킹이 앞에 서면 기존 저장글이 버려진다."""
    order_start = _TOTAL_SCRAP_SRC.index("all_posts = (")
    order_block = _TOTAL_SCRAP_SRC[order_start:order_start + 400]
    assert order_block.index("youtube_bm_posts") > order_block.index("youtube_posts")


def test_absorb_helper_is_wired_into_both_dedup_branches():
    """id 기준·pk 기준 둘 다에서 표식을 옮겨야 한다."""
    assert _TOTAL_SCRAP_SRC.count("_absorb_benchmark_mark(kept_by_id[pid], p)") == 1
    assert _TOTAL_SCRAP_SRC.count("_absorb_benchmark_mark(kept_by_pk[pk_key], p)") == 1
