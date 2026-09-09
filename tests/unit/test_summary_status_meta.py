"""요약 상태 두 필드가 목록 응답까지 살아 오는지 본다.

이 레포에서 **네 번째** 반복되는 함정이다 - `metrics_updated_at`(20260826_02),
`is_own_post`(20260826_03), `is_saved`(20260906_01) 가 모두 같은 방식으로 샜다.
META_FIELDS 에 없으면 /api/posts 가 값을 떨어뜨려 프런트가 항상 undefined 를 보고,
카드의 「요약없음」 사유 줄이 통째로 안 뜬다.
계획: _docs/20260909_01 (W2, V11)
"""

from utils.post_meta import META_FIELDS, build_post_meta


def _youtube_post(**overrides):
    post = {
        "sequence_id": 1,
        "sns_platform": "youtube",
        "platform_id": "4kXsF2S5MNY",
        "code": "4kXsF2S5MNY",
        "username": "dev-brother",
        "url": "https://www.youtube.com/watch?v=4kXsF2S5MNY",
        "full_text": "제목\n[설명] 본문",
        "transcript_status": "blocked",
        "summary_status": "no_transcript",
    }
    post.update(overrides)
    return post


def test_meta_fields_include_summary_status_fields():
    assert "transcript_status" in META_FIELDS
    assert "summary_status" in META_FIELDS


def test_build_post_meta_keeps_summary_status_fields():
    meta = build_post_meta(_youtube_post())

    assert meta["transcript_status"] == "blocked"
    assert meta["summary_status"] == "no_transcript"


def test_build_post_meta_keeps_ok_status_too():
    meta = build_post_meta(_youtube_post(transcript_status="ok", summary_status="ok"))

    assert meta["transcript_status"] == "ok"
    assert meta["summary_status"] == "ok"


def test_missing_status_fields_stay_absent_not_invented():
    """옛 수집분에는 이 필드가 없다. 없는 것을 있는 척하지 않는다 -
    뷰어는 값이 없으면 사유 줄을 그리지 않는다."""
    post = _youtube_post()
    post.pop("transcript_status")
    post.pop("summary_status")

    meta = build_post_meta(post)

    assert meta["transcript_status"] is None
    assert meta["summary_status"] is None
