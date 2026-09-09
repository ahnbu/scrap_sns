from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any


AUTH_REQUIRED_EXIT_CODE = 86
AUTH_SIGNAL_PREFIX = "SNS_AUTH_REQUIRED"
#: 외부 도구가 없어 수집의 일부가 조용히 비는 경우를 알리는 신호.
#: 인증 신호와 같은 「접두사 + JSON 한 줄」 규약을 쓴다 - total_scrap 이 로그에서
#: 주워 결과 모달까지 올린다. 종료코드를 쓰지 않는 이유: 수집 자체는 성공했고
#: 일부만 빈 것이라 실패로 표시하면 사용자가 전체를 다시 돌리게 된다.
#: 계획: _docs/20260909_01 (W5)
TOOL_UNAVAILABLE_SIGNAL_PREFIX = "SNS_TOOL_UNAVAILABLE"
ORCHESTRATED_RUN_ENV = "SNS_ORCHESTRATED_RUN"
KST = timezone(timedelta(hours=9))


class AuthRequiredError(Exception):
    """인증이 만료돼 더 진행할 수 없다.

    `exit_auth_required()` 와 같은 신호를 내지만 프로세스를 죽이지 않는다.
    수집기를 한 프로세스 안에서 여러 번 부르는 경로(벤치마킹 계정 수집)는
    `sys.exit(86)` 을 쓰면 **부모까지 죽어** 여기까지 모은 결과와 누적 저장이
    통째로 날아간다. 호출부가 잡아 저장을 끝내고 종료코드로 바꾼다.
    계획: _docs/20260909_01 (W6 T6-f)
    """

    def __init__(self, platform: str, payload: dict[str, Any] | None = None):
        self.platform = platform
        self.payload = payload or {}
        super().__init__(f"{platform} 인증이 필요하다: {self.payload.get('reason') or 'unknown'}")


def is_orchestrated_run() -> bool:
    return os.environ.get(ORCHESTRATED_RUN_ENV) == "1"


def emit_auth_required(
    platform: str,
    *,
    reason: str,
    current_url: str | None = None,
    auth_file: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "platform": platform,
        "reason": reason,
        "current_url": current_url,
        "auth_file": auth_file,
        "timestamp": datetime.now(KST).isoformat(timespec="seconds"),
    }
    if extra:
        payload.update(extra)

    print(f"{AUTH_SIGNAL_PREFIX} {json.dumps(payload, ensure_ascii=False)}", flush=True)


def emit_tool_unavailable(
    tool: str,
    *,
    platform: str,
    reason: str,
    impact: str,
    path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """외부 도구 부재를 기계가 읽을 수 있는 한 줄로 남긴다.

    2026-09-06에 PO token provider 폴더가 지워졌는데 9/9까지 아무도 몰랐다.
    수집은 「성공」으로 끝나고 자막만 0건이 됐는데, 그 사실이 로그의 사람용
    경고 한 줄로만 남아 화면까지 오지 않았기 때문이다.
    계획: _docs/20260909_01 (W5, R12)
    """
    payload: dict[str, Any] = {
        "tool": tool,
        "platform": platform,
        "reason": reason,
        "impact": impact,
        "path": path,
        "timestamp": datetime.now(KST).isoformat(timespec="seconds"),
    }
    if extra:
        payload.update(extra)

    print(
        f"{TOOL_UNAVAILABLE_SIGNAL_PREFIX} {json.dumps(payload, ensure_ascii=False)}",
        flush=True,
    )


def raise_auth_required(
    platform: str,
    *,
    reason: str,
    current_url: str | None = None,
    auth_file: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """신호는 그대로 찍고 예외로 던진다. 종료코드 전파는 호출부가 맡는다.

    `exit_auth_required()` 를 없애지 않는다 - 저장글 수집기(linkedin_scrap.py)와
    내 글 수집기는 프로세스 하나가 하나의 일만 하므로 그 자리에서 죽는 편이 맞다.
    """
    emit_auth_required(
        platform,
        reason=reason,
        current_url=current_url,
        auth_file=auth_file,
        extra=extra,
    )
    raise AuthRequiredError(
        platform,
        {
            "reason": reason,
            "current_url": current_url,
            "auth_file": auth_file,
            **(extra or {}),
        },
    )


def exit_auth_required(
    platform: str,
    *,
    reason: str,
    current_url: str | None = None,
    auth_file: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    emit_auth_required(
        platform,
        reason=reason,
        current_url=current_url,
        auth_file=auth_file,
        extra=extra,
    )
    sys.exit(AUTH_REQUIRED_EXIT_CODE)
