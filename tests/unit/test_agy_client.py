"""utils/agy_client.py 단위 테스트.

계획서: _docs/20260825_02_유튜브-요약-파이프라인-재설계-구현계획(실행완료).md (S10)
"""

import json

import pytest

from utils import agy_client


def _stream_json(status="SUCCESS", response="요약 본문", usage=None, turns=1):
    events = [
        {"event": "init", "conversation_id": "abc", "init": {"model": "gemini-3.7-flash-medium"}},
        {"event": "step_update", "step_update": {"step_index": 0, "state": "DONE"}},
        {"event": "result", "result": {
            "conversation_id": "abc",
            "status": status,
            "response": response,
            "duration_seconds": 8.0,
            "num_turns": turns,
            "usage": usage or {"input_tokens": 23899, "output_tokens": 1191,
                               "thinking_tokens": 610, "cache_read_tokens": 0,
                               "total_tokens": 25090},
        }},
    ]
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"


def _runner(returncode=0, stdout="", stderr="", record=None):
    def run(args, stdin_payload, timeout_seconds, cwd):
        if record is not None:
            record.append({"args": args, "stdin": stdin_payload})
        return {"returncode": returncode, "stdout": stdout, "stderr": stderr}
    return run


# --------------------------------------------------------------- (agy) 태그

def test_stdin_payload_starts_with_agy_tag():
    """S10 - 태그 누락이 구조적으로 막혔는지. 이 단정이 회귀 잠금장치다."""
    line = agy_client.build_stdin_payload("아무 프롬프트")
    payload = json.loads(line)
    text = payload["message"]["content"][0]["text"]
    assert text.startswith("(agy)\n"), f"(agy) 접두가 없다: {text[:20]!r}"


def test_agy_tag_is_not_configurable():
    """태그를 끄거나 바꾸는 인자가 없어야 한다 - 옵션이 있으면 언젠가 빠진다."""
    import inspect
    params = inspect.signature(agy_client.call_agy).parameters
    assert not any("tag" in name.lower() for name in params), list(params)


def test_stdin_payload_uses_event_key_not_type():
    """스키마는 `type` 이 아니라 `event` 다. 틀리면 agy 가 즉시 거부한다."""
    payload = json.loads(agy_client.build_stdin_payload("x"))
    assert payload["event"] == "user"
    assert "message" in payload


def test_stdin_payload_is_single_ndjson_line():
    line = agy_client.build_stdin_payload("여러\n줄\n프롬프트")
    assert line.endswith("\n")
    assert line.count("\n") == 1, "NDJSON 은 한 줄이어야 한다"


# --------------------------------------------------------------- 인자 구성

def test_build_args_has_sandbox_and_stream_json():
    args = agy_client.build_args()
    assert "--sandbox" in args
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--print" not in args and "-p" not in args


def test_build_args_default_model():
    args = agy_client.build_args()
    assert args[args.index("--model") + 1] == "gemini-3.7-flash-medium"


# --------------------------------------------------------------- usage 파싱

def test_success_returns_usage():
    result = agy_client.call_agy("프롬프트", runner=_runner(stdout=_stream_json()))
    assert result["ok"] is True
    assert result["status"] == "SUCCESS"
    assert result["usage"]["input_tokens"] == 23899
    assert result["usage"]["output_tokens"] == 1191
    assert result["usage"]["thinking_tokens"] == 610
    assert result["num_turns"] == 1
    assert result["response"] == "요약 본문"


def test_parse_ignores_non_result_events():
    noise = "not json\n" + _stream_json()
    assert agy_client.parse_stream_json(noise)["status"] == "SUCCESS"


def test_status_error_is_not_ok():
    out = agy_client.call_agy("프롬프트", runner=_runner(stdout=_stream_json(status="ERROR")))
    assert out["ok"] is False
    assert out["error"] == "agy-status-not-success"


def test_empty_stdout_is_reported():
    out = agy_client.call_agy("프롬프트", runner=_runner(stdout=""))
    assert out["error"] == "agy-empty-response"
    assert out["usage"] == agy_client.EMPTY_USAGE


# --------------------------------------------------------------- 프롬프트 길이

def test_long_prompt_is_not_rejected():
    """자막 최대 93,501자. 상한을 두면 37% 가 거부된다 - run-agy-reviewer.mjs 를
    그대로 쓸 수 없었던 이유다."""
    record = []
    huge = "가" * 100_000
    out = agy_client.call_agy(huge, runner=_runner(stdout=_stream_json(), record=record))
    assert out["ok"] is True
    assert len(record[0]["stdin"]) > 100_000


def test_empty_prompt_is_rejected():
    assert agy_client.call_agy("   ")["error"] == "missing-prompt"


# --------------------------------------------------------------- 실패 분류

@pytest.mark.parametrize("stderr,expected", [
    ("Eligibility check failed: RESOURCE_EXHAUSTED", "eligibility"),
    ("Authentication required. Please visit the URL", "auth"),
    ("authentication timed out", "auth"),
    ("failed to acquire lock: another update process is already active", "update-lock"),
    ("something nobody has seen", "unknown"),
])
def test_not_ready_reason_classification(stderr, expected):
    assert agy_client.classify_not_ready_reason(stderr) == expected


def test_permanent_failure_is_not_retried():
    calls = []

    def run(args, stdin_payload, timeout_seconds, cwd):
        calls.append(1)
        return {"returncode": 1, "stdout": "", "stderr": "Invalid model selection"}

    out = agy_client.call_agy("p", runner=run, sleeper=lambda s: None)
    assert out["error"] == "agy-exec-failed"
    assert len(calls) == 1, "영구 실패는 재시도하지 않는다"


def test_transient_failure_is_retried_with_backoff():
    calls, waits = [], []

    def run(args, stdin_payload, timeout_seconds, cwd):
        calls.append(1)
        if len(calls) < 3:
            return {"returncode": 1, "stdout": "", "stderr": "Authentication required"}
        return {"returncode": 0, "stdout": _stream_json(), "stderr": ""}

    out = agy_client.call_agy("p", runner=run, sleeper=waits.append)
    assert out["ok"] is True
    assert len(calls) == 3
    assert waits == [20, 60], f"백오프가 20s -> 60s 여야 한다: {waits}"


def test_exhausted_retries_report_reason():
    def run(args, stdin_payload, timeout_seconds, cwd):
        return {"returncode": 1, "stdout": "", "stderr": "Eligibility check failed"}

    out = agy_client.call_agy("p", runner=run, sleeper=lambda s: None)
    assert out["error"] == "agy-not-ready"
    assert out["not_ready_reason"] == "eligibility"
    assert out["warmup_retries"] == 2


def test_timeout_is_not_retried():
    calls = []

    def run(args, stdin_payload, timeout_seconds, cwd):
        calls.append(1)
        return {"returncode": None, "stdout": "", "stderr": "", "timed_out": True}

    out = agy_client.call_agy("p", runner=run, sleeper=lambda s: None)
    assert out["error"] == "agy-timeout"
    assert len(calls) == 1
