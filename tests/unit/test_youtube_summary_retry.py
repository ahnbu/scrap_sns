"""--max-summaries 상한에 걸린 요약이 다음 실행에서 다시 대상이 되는지 검증한다.

배경: BL-0826-04. update 모드의 처리 대상이 "기존 파일에 없는 영상"뿐이라,
한 번 `deferred` 로 저장된 295건이 다시는 요약되지 않았다.
"""

import pytest

import youtube_scrap as ys


pytestmark = pytest.mark.unit


@pytest.fixture
def transcript_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    return tmp_path


def _post(video_id, summary_status, transcript_status="ok"):
    return {
        "platform_id": video_id,
        "summary_status": summary_status,
        "transcript_status": transcript_status,
    }


def _with_transcript(transcript_dir, video_id):
    (transcript_dir / f"{video_id}.txt").write_text("자막 본문", encoding="utf-8")


# ------------------------------------------------------- needs_summary_retry

def test_deferred_with_cached_transcript_is_retried(transcript_dir):
    _with_transcript(transcript_dir, "vid1")
    assert ys.needs_summary_retry(_post("vid1", "deferred")) is True


def test_failed_summary_is_retried(transcript_dir):
    """agy 타임아웃(실측 1건)은 토큰을 거의 쓰지 않는다. 다시 부르는 편이 맞다."""
    _with_transcript(transcript_dir, "vid1")
    assert ys.needs_summary_retry(_post("vid1", "failed")) is True


def test_completed_summary_is_not_retried(transcript_dir):
    _with_transcript(transcript_dir, "vid1")
    assert ys.needs_summary_retry(_post("vid1", "ok")) is False


def test_no_transcript_is_not_retried(transcript_dir):
    """자막이 없으면 요약할 재료가 없다. 다시 불러도 결과가 같다."""
    assert ys.needs_summary_retry(_post("vid1", "no_transcript", "no_subtitle")) is False


def test_deferred_without_cached_file_is_not_retried(transcript_dir):
    """상태는 deferred 인데 자막 파일이 사라진 경우 - 요약이 아니라 재수집 대상이다."""
    assert ys.needs_summary_retry(_post("vid1", "deferred")) is False


# ------------------------------------------------------ select_update_targets

def test_update_targets_include_deferred_backlog(transcript_dir):
    """BL-0826-04 회귀 방어: 신규 0건이어도 대기분은 대상에 들어와야 한다."""
    for vid in ("old_ok", "old_deferred"):
        _with_transcript(transcript_dir, vid)
    entries = {"old_ok": {}, "old_deferred": {}, "brand_new": {}}
    existing = {
        "old_ok": _post("old_ok", "ok"),
        "old_deferred": _post("old_deferred", "deferred"),
    }

    new_ids, retry_ids = ys.select_update_targets(entries, existing)

    assert new_ids == ["brand_new"]
    assert retry_ids == ["old_deferred"]


def test_skip_summaries_run_does_not_touch_backlog(transcript_dir):
    """--skip-summaries 로 대기분을 다시 쓰면 deferred 가 skipped 로 덮인다."""
    _with_transcript(transcript_dir, "old_deferred")
    entries = {"old_deferred": {}}
    existing = {"old_deferred": _post("old_deferred", "deferred")}

    new_ids, retry_ids = ys.select_update_targets(entries, existing, allow_retry=False)

    assert new_ids == []
    assert retry_ids == []


# ------------------------------------------------------------ order_new_first

def test_new_videos_are_summarized_before_backlog():
    """상한이 뒤를 자르므로, 신규가 앞에 서야 방금 저장한 영상이 요약된다."""
    ordered = ys.order_new_first(["a_wait", "b_new", "c_wait", "d_new"], {"a_wait", "c_wait"})
    assert ordered == ["b_new", "d_new", "a_wait", "c_wait"]


def test_order_is_untouched_without_backlog():
    assert ys.order_new_first(["a", "b"], set()) == ["a", "b"]
