"""agy CLI 호출 클라이언트.

계획서: _docs/20260825_02_유튜브-요약-파이프라인-재설계-구현계획(실행완료).md (2-D, 3.5.3)

`agy --print="<프롬프트>"` 를 쓰지 않는다. Windows CreateProcess 명령줄 상한이
32,767자인데 유튜브 자막은 최대 93,501자다(실측). 대신 stream-json 입력으로
stdin 을 통해 프롬프트를 넘긴다.

호출 인자와 실패 판별은 ~/.claude/skills/_shared/run-agy-reviewer.mjs 에서
얻은 운용 지식을 이식한 것이다. 그 파일을 그대로 쓸 수 없는 이유는 두 가지다.
  1. 프롬프트 상한이 8,000자라 자막 중앙값(23,575자)이 거부된다.
  2. --print 텍스트 모드 고정이라 usage 를 받을 수 없다.
"""

from __future__ import annotations

import json
import subprocess
import time

# 세션DB 서브태스크 판정용 태그. 호출자는 붙이지 않는다 - 부착 지점은 여기 한 곳이다.
# 첫 줄이 "(agy)" 로 시작하면 detectLeadingAiCliTag() 가 매칭해 is_subtask=1 이 붙고
# 대시보드 기본 목록에서 빠진다. 인자로 끄거나 바꿀 수 없게 두는 것이 요점이다 -
# 옵션이 있으면 언젠가 빠진다.
AGY_TAG = "(agy)"

DEFAULT_COMMAND = "agy"
DEFAULT_MODEL = "gemini-3.7-flash-medium"
DEFAULT_PRINT_TIMEOUT = "10m"
DEFAULT_TIMEOUT_SECONDS = 660
DEFAULT_WARMUP_RETRIES = 2
DEFAULT_WARMUP_WAIT_SECONDS = 20
WARMUP_BACKOFF_FACTOR = 3  # 20s -> 60s

# 재시도해도 나아지지 않는 실패. 이 목록에 없으면 전부 재시도 대상이다.
# 판별을 뒤집은 이유: "일시적으로 보이는 것"의 목록은 새 얼굴이 나올 때마다 뚫리고,
# "재시도해도 안 낫는 것"의 목록은 유한하다.
PERMANENT_STDERR_MARKERS = (
    "invalid model selection",
    "no model configuration is available for this account",
)

# 준비 지연의 이유. 재시도 여부를 가르지 않고, 호출자가 stderr 원문 대신 읽을
# 구조화된 이름을 주는 것이 전부다.
NOT_READY_MARKERS = (
    ("eligibility", (
        "eligibility check failed",
        "unable to verify account eligibility",
        "eligibility verdict did not settle",
        "verifying your account eligibility",
    )),
    ("auth", (
        "authentication required",
        "waiting for authentication",
        "authentication timed out",
        "oauth2 flow failed for",
    )),
    ("update-lock", (
        "failed to acquire lock: another update process is already active",
    )),
)

NOT_READY_MESSAGES = {
    "auth": (
        "agy 가 자격 확인 단계를 넘지 못했다 (이유: auth). stderr 의 로그인 안내는 "
        "계정 만료의 증거가 아니다 - 자격 확인이 일시적으로 실패해도 같은 문구가 나온다."
    ),
    "eligibility": (
        "agy 가 계정 자격 확인 단계를 넘지 못했다 (이유: eligibility). 쿼터 소진이 아니라 "
        "인증·자동업데이트 지연이다 - 잠시 뒤 다시 부르거나 agy --version 으로 준비 상태를 확인한다."
    ),
    "update-lock": (
        "agy 가 자동 업데이트 락에 걸렸다 (이유: update-lock). 다른 agy 프로세스가 "
        "업데이트 중이다 - 그것이 끝나면 정상 동작한다."
    ),
    "unknown": (
        "agy 가 준비 단계를 넘지 못했다 (이유: unknown). 알려진 실패 문구가 아니지만 "
        "영구 실패로도 판별되지 않았다 - stderr 를 확인하고 반복되면 판별 목록에 추가한다."
    ),
}

EMPTY_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "thinking_tokens": 0,
    "cache_read_tokens": 0,
    "total_tokens": 0,
}


def build_stdin_payload(prompt):
    """agy stream-json 입력 한 줄을 만든다.

    스키마가 문서화돼 있지 않아 프로브로 찾았다. 키는 `type` 이 아니라 `event` 이고,
    `event: "user"` 는 `message` 필드를 요구한다.
    """
    tagged = f"{AGY_TAG}\n{str(prompt)}"
    payload = {
        "event": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": tagged}]},
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def build_args(model=DEFAULT_MODEL, print_timeout=DEFAULT_PRINT_TIMEOUT, command=DEFAULT_COMMAND):
    """호출 인자를 만든다.

    --sandbox 를 붙이는 이유: 자막은 제3자가 쓴 외부 입력인데 agy 세션의
    permission_mode 가 always-proceed 이고 노출 도구에 run_command·write_to_file 이
    들어 있다. 대가는 고정 오버헤드 약 +5,500 토큰(실측 19,600 -> 25,105)이다.
    """
    return [
        command,
        "--sandbox",
        "--model", model,
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--print-timeout", print_timeout,
    ]


def classify_not_ready_reason(stderr):
    text = str(stderr or "").lower()
    for reason, markers in NOT_READY_MARKERS:
        if any(marker in text for marker in markers):
            return reason
    return "unknown"


def looks_permanent(stderr):
    text = str(stderr or "").lower()
    return any(marker in text for marker in PERMANENT_STDERR_MARKERS)


def parse_stream_json(stdout):
    """stream-json 출력에서 result 이벤트를 뽑는다.

    앞에 init·step_update 이벤트가 여러 줄 붙으므로 마지막 result 를 찾는다.
    """
    result = None
    for line in str(stdout or "").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "result":
            result = event.get("result") or {}
    return result


def _failure(error, message, stdout="", stderr="", **extra):
    out = {
        "ok": False,
        "error": error,
        "message": message,
        "status": "ERROR",
        "response": "",
        "usage": dict(EMPTY_USAGE),
        "duration_seconds": 0.0,
        "num_turns": 0,
        "conversation_id": "",
        "stdout": stdout,
        "stderr": stderr,
    }
    out.update(extra)
    return out


def call_agy(
    prompt,
    model=DEFAULT_MODEL,
    print_timeout=DEFAULT_PRINT_TIMEOUT,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    warmup_retries=DEFAULT_WARMUP_RETRIES,
    warmup_wait_seconds=DEFAULT_WARMUP_WAIT_SECONDS,
    cwd=None,
    command=DEFAULT_COMMAND,
    runner=None,
    sleeper=None,
):
    """agy 를 한 번 호출하고 결과 dict 를 돌려준다.

    프롬프트 길이 상한은 두지 않는다 - stdin 경로라 명령줄 상한과 무관하다.
    runner / sleeper 는 테스트 주입점이다.
    """
    if not str(prompt or "").strip():
        return _failure("missing-prompt", "prompt is required")

    run = runner or _run_process
    sleep = sleeper or time.sleep
    args = build_args(model=model, print_timeout=print_timeout, command=command)
    stdin_payload = build_stdin_payload(prompt)

    attempts = 0
    proc = {}
    while True:
        proc = run(args, stdin_payload, timeout_seconds, cwd)
        if proc.get("returncode") == 0 and not proc.get("spawn_error"):
            break
        if attempts >= max(0, int(warmup_retries)):
            break
        if proc.get("spawn_error") or proc.get("timed_out") or looks_permanent(proc.get("stderr")):
            break
        # 08-24 실측에서 agy 가 준비를 마치기까지 약 4분 걸렸다. 고정 20초 1회로는
        # 두 번째 시도조차 준비 전에 떨어진다.
        sleep(warmup_wait_seconds * (WARMUP_BACKOFF_FACTOR ** attempts))
        attempts += 1

    if proc.get("spawn_error"):
        return _failure("agy-spawn-failed", str(proc["spawn_error"]),
                        stderr=proc.get("stderr", ""), warmup_retries=attempts)
    if proc.get("timed_out"):
        return _failure("agy-timeout", f"agy 가 {timeout_seconds}초 안에 끝나지 않았다",
                        stdout=proc.get("stdout", ""), stderr=proc.get("stderr", ""),
                        warmup_retries=attempts)

    if proc.get("returncode") != 0:
        if looks_permanent(proc.get("stderr")):
            return _failure("agy-exec-failed",
                            f"agy exited with code {proc.get('returncode')}",
                            stdout=proc.get("stdout", ""), stderr=proc.get("stderr", ""),
                            warmup_retries=attempts)
        reason = classify_not_ready_reason(proc.get("stderr"))
        return _failure("agy-not-ready", NOT_READY_MESSAGES[reason],
                        stdout=proc.get("stdout", ""), stderr=proc.get("stderr", ""),
                        not_ready_reason=reason, warmup_retries=attempts)

    result = parse_stream_json(proc.get("stdout"))
    if not result:
        return _failure("agy-empty-response", "stream-json 출력에 result 이벤트가 없다",
                        stdout=proc.get("stdout", ""), stderr=proc.get("stderr", ""),
                        warmup_retries=attempts)

    usage = dict(EMPTY_USAGE)
    usage.update(result.get("usage") or {})
    status = str(result.get("status") or "")

    return {
        "ok": status == "SUCCESS",
        "error": None if status == "SUCCESS" else "agy-status-not-success",
        "message": result.get("error") or "",
        "status": status,
        "response": str(result.get("response") or "").strip(),
        "usage": usage,
        "duration_seconds": float(result.get("duration_seconds") or 0.0),
        "num_turns": int(result.get("num_turns") or 0),
        "conversation_id": str(result.get("conversation_id") or ""),
        "stdout": proc.get("stdout", ""),
        "stderr": proc.get("stderr", ""),
        "warmup_retries": attempts,
    }


def _run_process(args, stdin_payload, timeout_seconds, cwd):
    try:
        completed = subprocess.run(
            args,
            input=stdin_payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return {"returncode": None, "stdout": error.stdout or "", "stderr": error.stderr or "",
                "timed_out": True}
    except OSError as error:
        return {"returncode": None, "stdout": "", "stderr": str(error), "spawn_error": error}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }
