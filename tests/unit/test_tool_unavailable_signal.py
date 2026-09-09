"""자막 도구가 없을 때 그 사실이 기계가 읽는 신호로 남는지 본다.

2026-09-06에 PO token provider 폴더가 지워졌는데 9/9까지 아무도 몰랐다.
수집은 성공(종료코드 0)으로 끝나고 자막만 0건이 됐는데, 그 사실이 사람용 로그
한 줄로만 남아 화면까지 오지 않았다. 계획: _docs/20260909_01 (W5, R12)
"""

import json

import scrap_sns_server
from utils.auth_status import TOOL_UNAVAILABLE_SIGNAL_PREFIX, emit_tool_unavailable


def _emit_and_capture(capsys, **kwargs):
    emit_tool_unavailable("bgutil-pot-provider", **kwargs)
    return capsys.readouterr().out.strip()


def test_signal_line_is_prefix_plus_one_json_line(capsys):
    line = _emit_and_capture(
        capsys,
        platform="youtube",
        reason="entry_missing",
        impact="new_transcripts_blocked",
        path="C:/Users/ahnbu/bgutil-ytdlp-pot-provider/server/build/main.js",
    )

    assert line.startswith(TOOL_UNAVAILABLE_SIGNAL_PREFIX + " ")
    payload = json.loads(line[len(TOOL_UNAVAILABLE_SIGNAL_PREFIX):].strip())
    assert payload["tool"] == "bgutil-pot-provider"
    assert payload["platform"] == "youtube"
    assert payload["reason"] == "entry_missing"
    assert payload["impact"] == "new_transcripts_blocked"
    assert payload["timestamp"]


def test_extra_fields_are_merged(capsys):
    line = _emit_and_capture(
        capsys,
        platform="youtube",
        reason="port_unresponsive",
        impact="new_transcripts_blocked",
        path="http://127.0.0.1:4416",
        extra={"timeout_seconds": 90},
    )

    payload = json.loads(line[len(TOOL_UNAVAILABLE_SIGNAL_PREFIX):].strip())
    assert payload["timeout_seconds"] == 90


def test_server_passes_warnings_through_without_platform_normalization():
    """🔴 이 경고의 주인공은 youtube 다. 그런데 서버의 플랫폼 정규화는
    threads·linkedin·x 만 인정해 youtube 를 버린다. 그래서 warnings 는
    그 정규화를 타지 않아야 한다."""
    summary = {
        "platform_results": {"youtube": {"status": "ok"}},
        "auth_required": [],
        "warnings": [
            {
                "tool": "bgutil-pot-provider",
                "platform": "youtube",
                "reason": "entry_missing",
                "impact": "new_transcripts_blocked",
                "slot": "youtube",
            }
        ],
    }

    normalized = scrap_sns_server._normalize_scrap_summary(summary)

    assert normalized["warnings"] == summary["warnings"]
    # 플랫폼 결과 쪽은 종전처럼 youtube 를 버린다 - 그 동작은 건드리지 않았다.
    assert "youtube" not in normalized["platform_results"]


def test_summary_without_warnings_key_yields_empty_list():
    normalized = scrap_sns_server._normalize_scrap_summary(
        {"platform_results": {}, "auth_required": []}
    )

    assert normalized["warnings"] == []


def test_non_dict_summary_still_has_warnings_key():
    assert scrap_sns_server._normalize_scrap_summary(None)["warnings"] == []
