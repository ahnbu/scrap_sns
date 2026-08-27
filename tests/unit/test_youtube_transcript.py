"""youtube_scrap.py 의 자막·설명글·본문 조립 단위 테스트.

계획서: _docs/20260825_02_유튜브-요약-파이프라인-재설계-구현계획(실행완료).md
"""

import os
import types

import pytest

import youtube_scrap as ys


VTT_SAMPLE = """WEBVTT
Kind: captions
Language: ko

00:00:00.040 --> 00:00:01.550 align:start position:0%

정부<00:00:00.320><c> 지원</c><00:00:00.520><c> 사업은</c>

00:00:01.550 --> 00:00:01.560 align:start position:0%
정부 지원 사업은


00:00:01.560 --> 00:00:03.790 align:start position:0%
정부 지원 사업은
시드머니다.

00:01:10.000 --> 00:01:12.000 align:start position:0%
두 번째 구간 문장

00:02:30.000 --> 00:02:32.000 align:start position:0%
세 번째 구간 문장
"""


# --------------------------------------------------------------- clean_vtt

def test_clean_vtt_emits_bucket_markers():
    out = ys.clean_vtt(VTT_SAMPLE).splitlines()
    assert out[0] == "[00:00]"
    assert "[01:00]" in out
    assert "[02:00]" in out


def test_clean_vtt_drops_vtt_noise():
    out = ys.clean_vtt(VTT_SAMPLE)
    assert "WEBVTT" not in out
    assert "-->" not in out
    assert "<c>" not in out
    assert "align:start" not in out


def test_clean_vtt_dedupes_rolling_lines():
    """자동 자막은 직전 줄을 반복한다. 중복 제거가 안 되면 분량이 배로 뛴다."""
    out = ys.clean_vtt(VTT_SAMPLE)
    assert out.count("정부 지원 사업은") == 1


def _synthetic_vtt():
    """0~29초와 60~89초에 각각 30줄. 60초 버킷이면 마커는 2개뿐이어야 한다."""
    cues = []
    for index in range(30):
        cues.append(
            f"00:00:{index:02d}.000 --> 00:00:{index + 1:02d}.000" + "\n" + f"문장 {index}"
        )
    for index in range(30):
        cues.append(
            f"00:01:{index:02d}.000 --> 00:01:{index + 1:02d}.000" + "\n" + f"문장 {index + 100}"
        )
    return "WEBVTT\n\n" + "\n\n".join(cues)


def test_bucket_marker_is_emitted_once_per_bucket():
    """매 줄 접두는 입력이 +42% 늘고 60초 버킷은 +1.5% 다(실측).
    싸지는 이유는 버킷당 마커가 한 개뿐이기 때문이다."""
    raw = _synthetic_vtt()
    out = ys.clean_vtt(raw)

    markers = [line for line in out.splitlines() if line.startswith("[")]
    assert markers == ["[00:00]", "[01:00]"], markers

    plain = ys.clean_vtt(raw, bucket_seconds=0)
    overhead = (len(out) - len(plain)) / len(plain)
    assert overhead < 0.05, f"버킷 오버헤드가 {overhead:.1%} 로 과하다"


# --------------------------------------------------------------- 자막 언어 선택

def test_subtitle_priority_prefers_korean_over_english():
    """알파벳 정렬로 고르면 .en.vtt 가 먼저 와서 영어를 집는 결함이 있었다."""
    produced = ["/x/VID.en.vtt", "/x/VID.ko-orig.vtt", "/x/VID.ko.vtt"]
    assert ys.pick_subtitle_file(produced, "VID").endswith("VID.ko-orig.vtt")


def test_subtitle_priority_falls_back_to_ko_then_en():
    assert ys.pick_subtitle_file(["/x/VID.en.vtt", "/x/VID.ko.vtt"], "VID").endswith("VID.ko.vtt")
    assert ys.pick_subtitle_file(["/x/VID.en.vtt"], "VID").endswith("VID.en.vtt")


# --------------------------------------------------------------- 설명글 정제

def test_split_description_removes_urls_and_hashtags():
    prose, timeline = ys.split_description(
        "좋은 영상입니다 https://example.com/promo 확인하세요\n#창업 #AI"
    )
    assert "https://" not in prose
    assert "#창업" not in prose
    assert "좋은 영상입니다" in prose
    assert timeline == ""


def test_split_description_extracts_timeline():
    prose, timeline = ys.split_description(
        "설명 본문\n00:00 오프닝\n01:31 진짜 이유\n00:02:03 세부 항목\n마무리"
    )
    assert timeline.splitlines() == ["00:00 오프닝", "01:31 진짜 이유", "00:02:03 세부 항목"]
    assert "오프닝" not in prose
    assert prose.splitlines() == ["설명 본문", "마무리"]


def test_split_description_keeps_prose_unedited():
    """산문은 품질 편차가 커 기계로 못 가른다 - 손대지 않는다."""
    ad = "정부지원사업, 안하면 손해🚨 지금 신청하세요"
    prose, _ = ys.split_description(ad)
    assert prose == ad


def test_timeline_from_transcript_fills_missing_toc():
    transcript = "\n".join(
        ["[00:00]", "오프닝 멘트"]
        + [f"[{m:02d}:00]\n{m}분 내용" for m in range(1, 12)]
    )
    out = ys.timeline_from_transcript(transcript, step_minutes=5)
    starts = [line.split(" ")[0] for line in out.splitlines()]
    assert starts == ["00:00", "05:00", "10:00"]


# --------------------------------------------------------------- full_text

def test_full_text_puts_summary_right_after_separator():
    """카드 클램프(6줄) 안에 요약이 들어가려면 제목 바로 뒤여야 한다."""
    text = ys.build_full_text("제목", "[요약] 한줄\n- 핵심1", "설명 본문", "00:00 오프닝")
    lines = text.splitlines()
    assert lines[0] == "제목"
    assert lines[1] == ys.SECTION_SEPARATOR
    assert lines[2].startswith("[요약]")


def test_full_text_orders_sections():
    text = ys.build_full_text("제목", "[요약] 한줄", "설명 본문", "00:00 오프닝")
    assert text.index("[요약]") < text.index("[설명]") < text.index("[타임라인]")


def test_full_text_without_summary_has_no_separator():
    text = ys.build_full_text("제목", "", "설명 본문", "")
    assert ys.SECTION_SEPARATOR not in text
    assert text.startswith("제목")


def test_full_text_has_no_markdown_symbols():
    """뷰어는 마크다운을 렌더링하지 않는다(S5)."""
    text = ys.build_full_text("제목", "[요약] 한줄\n- 핵심1", "설명", "00:00 시작")
    for symbol in ("##", "**", "__"):
        assert symbol not in text


# --------------------------------------------------------------- 캐시 키

def test_prompt_signature_changes_with_template(monkeypatch):
    """프롬프트가 바뀌면 캐시가 미스돼야 한다. 옛 캐시는 sha1 하나만 비교했다."""
    before = ys.prompt_signature()
    monkeypatch.setattr(ys, "SUMMARY_PROMPT_TEMPLATE", ys.SUMMARY_PROMPT_TEMPLATE + " ")
    assert ys.prompt_signature() != before


def test_cache_miss_on_prompt_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "SUMMARY_DIR", str(tmp_path))
    ys.store_summary("VID", "m", "sha-1", "요약본", {}, 1.0, "conv")
    assert ys.load_cached_summary("VID", "sha-1", "m") == "요약본"

    monkeypatch.setattr(ys, "SUMMARY_PROMPT_TEMPLATE", "다른 프롬프트")
    assert ys.load_cached_summary("VID", "sha-1", "m") is None


def test_cache_miss_on_model_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "SUMMARY_DIR", str(tmp_path))
    ys.store_summary("VID", "model-a", "sha-1", "요약본", {}, 1.0, "conv")
    assert ys.load_cached_summary("VID", "sha-1", "model-b") is None


def test_cache_miss_on_transcript_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "SUMMARY_DIR", str(tmp_path))
    ys.store_summary("VID", "m", "sha-1", "요약본", {}, 1.0, "conv")
    assert ys.load_cached_summary("VID", "sha-2", "m") is None


# --------------------------------------------------------------- 웨이브 필터

class _Args:
    def __init__(self, **kw):
        self.min_duration = kw.get("min_duration", 0)
        self.max_duration = kw.get("max_duration", 0)
        self.added_min_days = kw.get("added_min_days")
        self.added_max_days = kw.get("added_max_days")


def _detail(seconds):
    minutes, secs = divmod(seconds, 60)
    return {"contentDetails": {"duration": f"PT{minutes}M{secs}S"}}


def test_duration_boundary_is_half_open(tmp_path, monkeypatch):
    """[min, max) 여야 경계값이 두 웨이브에 겹치거나 빠지지 않는다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    details = {"A": _detail(599), "B": _detail(600), "C": _detail(601)}
    entries = {k: {"playlist_added_at": "2026-08-20 00:00:00"} for k in details}

    w0 = ys.apply_wave_filters(list(details), details, entries, _Args(max_duration=600))
    w1 = ys.apply_wave_filters(list(details), details, entries,
                               _Args(min_duration=600, max_duration=3600))
    assert set(w0) == {"A"}
    assert set(w1) == {"B", "C"}
    assert not set(w0) & set(w1)


def test_wave_filter_sorts_by_transcript_size(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "BIG.txt").write_text("가" * 500, encoding="utf-8")
    (tmp_path / "SMALL.txt").write_text("가" * 10, encoding="utf-8")
    details = {"BIG": _detail(100), "SMALL": _detail(100)}
    entries = {k: {"playlist_added_at": "2026-08-20 00:00:00"} for k in details}
    assert ys.apply_wave_filters(list(details), details, entries, _Args()) == ["SMALL", "BIG"]


@pytest.mark.parametrize("duration,expected", [("PT1H2M3S", 3723), ("PT10M", 600), ("", 0)])
def test_parse_iso_duration(duration, expected):
    assert ys.parse_iso_duration(duration) == expected

# ------------------------------------------- provider 미가동 시 캐시 자막 사용

def test_cached_transcript_is_read_without_provider(tmp_path, monkeypatch):
    """provider 사고로 새 자막을 못 받아도, 이미 가진 자막까지 없는 셈 치면 안 된다.

    all 모드에서 전량이 blocked 로 덮이면 기존 요약이 통합본에서 사라진다.
    """
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "vid1.txt").write_text("캐시된 자막", encoding="utf-8")

    status, text = ys.download_transcript("vid1", str(tmp_path / "_scratch"), allow_download=False)

    assert status == "ok"
    assert text == "캐시된 자막"


def test_missing_transcript_without_provider_is_blocked(tmp_path, monkeypatch):
    """캐시가 없으면 yt-dlp 를 부르지 않고 blocked 로 끝낸다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(
        ys.subprocess, "run",
        lambda *a, **k: pytest.fail("provider 없이 yt-dlp 를 부르면 안 된다"),
    )

    assert ys.download_transcript("vid1", str(tmp_path / "_scratch"), allow_download=False) == (
        "blocked", ""
    )


def test_refresh_falls_back_to_cache_without_provider(tmp_path, monkeypatch):
    """--refresh-transcripts 라도 provider 가 없으면 재수집이 불가능하다.

    캐시를 버리면 멀쩡한 자막을 잃는다. 재수집은 provider 가 살아난 뒤로 미룬다.
    """
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "vid1.txt").write_text("옛 자막", encoding="utf-8")

    status, text = ys.download_transcript(
        "vid1", str(tmp_path / "_scratch"), refresh=True, allow_download=False
    )

    assert (status, text) == ("ok", "옛 자막")


# ------------------------------------------- 자막 언어 2단계 폴백 (2026-08-27)

class _FakeRun:
    """yt-dlp 호출을 가로채 언어 조합별 결과를 흉내낸다.

    sub-langs 값을 키로 (생성할 vtt 파일명 목록, 출력 텍스트) 를 돌려준다.
    호출 이력은 self.calls 에 순서대로 쌓인다.
    """

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, command, **kwargs):
        langs = command[command.index("--sub-langs") + 1]
        out_template = command[command.index("-o") + 1]
        scratch = os.path.dirname(out_template)
        self.calls.append(langs)
        files, output = self.table.get(langs, ([], ""))
        os.makedirs(scratch, exist_ok=True)
        for name in files:
            with open(os.path.join(scratch, name), "w", encoding="utf-8") as handle:
                handle.write(VTT_SAMPLE)
        return types.SimpleNamespace(stdout=output, stderr="", returncode=0)


def test_primary_request_asks_only_original_tracks(tmp_path, monkeypatch):
    """1차는 -orig 만 부른다. ko 를 직접 부르면 번역 요청이 되어 429 를 맞는다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({ys.TRANSCRIPT_LANG_PRIMARY: (["vid1.ko-orig.vtt"], "")})
    monkeypatch.setattr(ys.subprocess, "run", fake)

    status, text = ys.download_transcript("vid1", str(tmp_path / "_scratch"))

    assert status == "ok"
    assert text
    assert fake.calls == [ys.TRANSCRIPT_LANG_PRIMARY]


def test_english_video_is_recovered_by_original_track(tmp_path, monkeypatch):
    """영어 원본 영상은 en-orig 로 내려온다. 예전에는 no_subtitle 로 잘못 굳었다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({ys.TRANSCRIPT_LANG_PRIMARY: (["vid1.en-orig.vtt"], "")})
    monkeypatch.setattr(ys.subprocess, "run", fake)

    assert ys.download_transcript("vid1", str(tmp_path / "_scratch"))[0] == "ok"


def test_fallback_runs_only_when_primary_is_empty(tmp_path, monkeypatch):
    """-orig 가 없는 영상(수동 자막만)은 2차에서 잡는다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({
        ys.TRANSCRIPT_LANG_PRIMARY: ([], "has no automatic captions"),
        ys.TRANSCRIPT_LANG_FALLBACK: (["vid1.en.vtt"], ""),
    })
    monkeypatch.setattr(ys.subprocess, "run", fake)

    status, _ = ys.download_transcript("vid1", str(tmp_path / "_scratch"))

    assert status == "ok"
    assert fake.calls == [ys.TRANSCRIPT_LANG_PRIMARY, ys.TRANSCRIPT_LANG_FALLBACK]


def test_no_subtitle_when_both_stages_are_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({})
    monkeypatch.setattr(ys.subprocess, "run", fake)

    assert ys.download_transcript("vid1", str(tmp_path / "_scratch")) == ("no_subtitle", "")
    assert len(fake.calls) == 2


@pytest.mark.parametrize("message", [
    "ERROR: [youtube] AmePj1SI6Z4: Join this channel to get access to members-only content like this video, and other exclusive perks.",
    "ERROR: [youtube] 3fvglK7Czjg: This video is available to this channel's members on level: 서포터즈 (or any higher level).",
])
def test_members_only_is_detected_in_both_wordings(tmp_path, monkeypatch, message):
    """두 문구 모두 잡아야 한다. members-only 만 보면 두 번째를 놓친다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({ys.TRANSCRIPT_LANG_PRIMARY: ([], message)})
    monkeypatch.setattr(ys.subprocess, "run", fake)

    assert ys.download_transcript("vid1", str(tmp_path / "_scratch")) == ("members_only", "")


def test_members_only_skips_the_fallback_call(tmp_path, monkeypatch):
    """멤버십 결제 전에는 2차를 돌려도 같다. 헛호출을 하지 않는다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({
        ys.TRANSCRIPT_LANG_PRIMARY: ([], "ERROR: members-only content"),
    })
    monkeypatch.setattr(ys.subprocess, "run", fake)

    ys.download_transcript("vid1", str(tmp_path / "_scratch"))

    assert fake.calls == [ys.TRANSCRIPT_LANG_PRIMARY]


def test_po_token_failure_still_reports_blocked(tmp_path, monkeypatch):
    """provider 사고는 자막 없음이 아니다. 기존 판정을 유지한다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    fake = _FakeRun({ys.TRANSCRIPT_LANG_PRIMARY: ([], "PO token is required")})
    monkeypatch.setattr(ys.subprocess, "run", fake)

    assert ys.download_transcript("vid1", str(tmp_path / "_scratch")) == ("blocked", "")


def test_en_orig_is_in_language_priority():
    """1차가 실제로 내려주는 파일명이라 우선순위 목록에 있어야 한다."""
    assert "en-orig" in ys.SUBTITLE_LANG_PRIORITY
    assert ys.SUBTITLE_LANG_PRIORITY.index("ko-orig") < ys.SUBTITLE_LANG_PRIORITY.index("en-orig")


def test_pick_subtitle_file_prefers_korean_over_english_original():
    produced = ["/x/vid1.en-orig.vtt", "/x/vid1.ko-orig.vtt"]
    assert ys.pick_subtitle_file(produced, "vid1").endswith("ko-orig.vtt")


# ------------------------------------------- 자막 재시도 대상 선정 (2026-08-27)

@pytest.mark.parametrize("status,expected", [
    ("no_subtitle", True),
    ("failed", True),
    ("blocked", True),
    ("members_only", False),
    ("ok", False),
])
def test_transcript_retry_targets(status, expected):
    post = {"platform_id": "vid1", "transcript_status": status}
    assert ys.needs_transcript_retry(post) is expected


def test_members_only_never_returns_to_the_queue():
    """결제 전에는 몇 번을 불러도 같은 답이라 매 실행 재질의하지 않는다."""
    existing = {"vid1": {"platform_id": "vid1", "transcript_status": "members_only",
                         "summary_status": "no_transcript"}}
    new_ids, retry_ids = ys.select_update_targets({"vid1": {}}, existing)
    assert (new_ids, retry_ids) == ([], [])


def test_no_subtitle_is_picked_up_by_update_mode(tmp_path, monkeypatch):
    """언어 폴백을 고쳐도 update 가 대상에 넣지 않으면 영원히 그대로다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    existing = {"vid1": {"platform_id": "vid1", "transcript_status": "no_subtitle",
                         "summary_status": "no_transcript"}}
    new_ids, retry_ids = ys.select_update_targets({"vid1": {}}, existing)
    assert (new_ids, retry_ids) == ([], ["vid1"])


def test_transcript_retry_is_suppressed_by_skip_summaries(tmp_path, monkeypatch):
    """요약을 건너뛰는 실행이 대상을 다시 쓰면 재시도 표시가 skipped 로 덮인다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    existing = {"vid1": {"platform_id": "vid1", "transcript_status": "no_subtitle",
                         "summary_status": "no_transcript"}}
    _, retry_ids = ys.select_update_targets({"vid1": {}}, existing, allow_retry=False)
    assert retry_ids == []


def test_summary_and_transcript_retries_coexist(tmp_path, monkeypatch):
    """두 재시도군이 한 실행에서 같이 잡혀야 319건이 한 번에 소진된다."""
    monkeypatch.setattr(ys, "TRANSCRIPT_DIR", str(tmp_path))
    (tmp_path / "vid_sum.txt").write_text("자막", encoding="utf-8")
    existing = {
        "vid_sum": {"platform_id": "vid_sum", "transcript_status": "ok",
                    "summary_status": "deferred"},
        "vid_tr": {"platform_id": "vid_tr", "transcript_status": "no_subtitle",
                   "summary_status": "no_transcript"},
        "vid_done": {"platform_id": "vid_done", "transcript_status": "ok",
                     "summary_status": "ok"},
    }
    entries = {"vid_sum": {}, "vid_tr": {}, "vid_done": {}, "vid_new": {}}
    new_ids, retry_ids = ys.select_update_targets(entries, existing)

    assert new_ids == ["vid_new"]
    assert set(retry_ids) == {"vid_sum", "vid_tr"}


# ------------------------------------------- 요약 응답 정제 (2026-08-27)

def test_sanitize_removes_agy_control_marker():
    """agy 가 응답 끝에 남긴 제어 마커가 요약 본문에 섞여 있었다(449건 중 3건)."""
    raw = "[요약] 한 줄 요약이다.\n\n- 핵심\n\n<!-- GOAL_COMPLETE -->"
    out = ys.sanitize_summary(raw)
    assert "GOAL_COMPLETE" not in out
    assert "<!--" not in out
    assert out.endswith("- 핵심")


def test_sanitize_removes_any_html_comment():
    """마커 하나만 지우면 다음 마커에 또 뚫린다. 주석 전체를 걷어낸다."""
    raw = "[요약] 앞부분\n<!-- 다른 마커 -->\n[상세] 뒷부분"
    out = ys.sanitize_summary(raw)
    assert "<!--" not in out
    assert "앞부분" in out and "뒷부분" in out


def test_sanitize_handles_multiline_comment():
    raw = "[요약] 본문\n\n<!--\n여러 줄\n주석\n-->\n"
    assert ys.sanitize_summary(raw) == "[요약] 본문"


def test_sanitize_collapses_blank_runs_left_behind():
    """마커를 지운 자리에 빈 줄이 세 줄씩 남으면 뷰어 카드가 벌어진다."""
    raw = "가\n\n<!-- x -->\n\n나"
    assert ys.sanitize_summary(raw) == "가\n\n나"


def test_sanitize_keeps_normal_summary_untouched():
    raw = "[요약] 정상 요약\n\n- 핵심 1\n- 핵심 2\n\n[상세]\n소제목\n설명 문장."
    assert ys.sanitize_summary(raw) == raw


@pytest.mark.parametrize("value", [None, "", "   \n\n  "])
def test_sanitize_returns_empty_for_blank_input(value):
    assert ys.sanitize_summary(value) == ""


def test_cached_summary_is_sanitized_on_read(tmp_path, monkeypatch):
    """정제 도입 전 저장된 캐시는 히트라 다시 만들어지지 않는다. 읽을 때 걷어낸다."""
    monkeypatch.setattr(ys, "SUMMARY_DIR", str(tmp_path))
    ys.store_summary("VID", "m", "sha-1", "요약본", {}, 1.0, "conv")
    # 정제 도입 전에 저장된 상태를 흉내낸다.
    import json as _json
    path = ys.summary_path_for("VID")
    with open(path, "r", encoding="utf-8") as handle:
        data = _json.load(handle)
    data["summary"] = "요약본\n\n<!-- GOAL_COMPLETE -->"
    with open(path, "w", encoding="utf-8") as handle:
        _json.dump(data, handle, ensure_ascii=False)

    assert ys.load_cached_summary("VID", "sha-1", "m") == "요약본"
