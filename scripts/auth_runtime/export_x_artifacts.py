from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from auth_paths import (
        validate_x_cookie_target,
        x_cookie_link,
        x_flat_cookie,
        x_flat_storage,
        x_storage,
        x_user_data,
    )
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from utils.auth_paths import (
        validate_x_cookie_target,
        x_cookie_link,
        x_flat_cookie,
        x_flat_storage,
        x_storage,
        x_user_data,
    )


def extract_token_pair(cookies: list[dict]) -> dict[str, str] | None:
    values = {item.get("name"): item.get("value") for item in cookies}
    if not values.get("auth_token") or not values.get("ct0"):
        return None
    return {"auth_token": values["auth_token"], "ct0": values["ct0"]}


def flat_cookie_link_name() -> str:
    return "x_cookies_current.json"


def flat_storage_link_name() -> str:
    return "x_storage_state_current.json"


def _refresh_link(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    temp_link = link_path.with_name(f".{link_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_link.symlink_to(target_path.resolve())
        os.replace(temp_link, link_path)
    finally:
        if temp_link.exists() or temp_link.is_symlink():
            temp_link.unlink()


def export_x_artifacts(stamp: str | None = None) -> tuple[Path, Path]:
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    x_root = x_user_data().parent
    x_root.mkdir(parents=True, exist_ok=True)
    x_user_data().mkdir(parents=True, exist_ok=True)
    storage_path = x_storage()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    dated_cookie_path = x_root / f"cookies_{stamp}.json"

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(x_user_data()),
            channel="chrome",
            headless=True,
        )
        context.storage_state(path=str(storage_path))
        cookies = context.cookies("https://x.com")
        context.close()

    token_pair = extract_token_pair(cookies)
    if token_pair is None:
        raise RuntimeError("auth_token/ct0 missing after X export")

    dated_cookie_path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _refresh_link(x_cookie_link(), dated_cookie_path)
    _refresh_link(x_flat_cookie(), x_cookie_link())
    _refresh_link(x_flat_storage(), x_storage())

    if not validate_x_cookie_target(dated_cookie_path.name):
        raise RuntimeError("cookies.json still points to stale export target")

    print(f"EXPORTED_COOKIE_FILE={dated_cookie_path.name}")
    print(f"VALIDATED_COOKIE_TARGET={dated_cookie_path.name}")
    return dated_cookie_path, storage_path
