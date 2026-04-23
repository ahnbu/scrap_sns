from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any


AUTH_REQUIRED_EXIT_CODE = 86
AUTH_SIGNAL_PREFIX = "SNS_AUTH_REQUIRED"
ORCHESTRATED_RUN_ENV = "SNS_ORCHESTRATED_RUN"
KST = timezone(timedelta(hours=9))


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
