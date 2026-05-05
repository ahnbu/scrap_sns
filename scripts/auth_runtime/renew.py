from __future__ import annotations

import sys
import argparse
import json
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from export_x_artifacts import export_x_artifacts_from_context
    from auth_paths import linkedin_storage, skool_storage, threads_storage, x_user_data
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.auth_runtime.export_x_artifacts import export_x_artifacts_from_context
    from utils.auth_paths import linkedin_storage, skool_storage, threads_storage, x_user_data


# LinkedIn fingerprint 회복 목적으로 추가됨 (plan: docs/plans/20260505_03_renew.py-환경정렬-LinkedIn-fingerprint-회복.md).
# 갱신기와 수집기의 user_agent/locale/viewport를 정렬해 LinkedIn step-up redirect를 회피한다.
# Threads/Skool에도 동일 환경을 적용해 회귀 재발을 방지한다 (X는 별도 persistent profile 경로).
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
BROWSER_LOCALE = "ko-KR"
BROWSER_VIEWPORT = {"width": 1280, "height": 1000}


def _require_tty() -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("interactive login required; run this command in a terminal")


def _browser_args(window_position: str, window_size: str) -> list[str]:
    return [
        f"--window-position={window_position}",
        f"--window-size={window_size}",
    ]


def _signal_path(signal_dir: Path, session_id: str) -> Path:
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"_", "-"})
    return signal_dir / f"{safe_id}.complete"


def _wait_for_web_complete(name: str, signal_dir: Path, session_id: str) -> None:
    path = _signal_path(signal_dir, session_id)
    print(json.dumps({"status": "ready", "platform": name.lower()}, ensure_ascii=False), flush=True)
    while not path.exists():
        time.sleep(0.5)


def renew_storage_state(name: str, url: str, target: Path) -> None:
    _require_tty()
    target.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context_args = {
            "user_agent": BROWSER_USER_AGENT,
            "locale": BROWSER_LOCALE,
            "viewport": BROWSER_VIEWPORT,
        }
        if target.exists() and target.stat().st_size > 10:
            context_args["storage_state"] = str(target)
        context = browser.new_context(**context_args)
        page = context.new_page()
        page.goto(url)
        input(f"[{name}] 로그인 완료 후 Enter: ")
        context.storage_state(path=str(target))
        browser.close()


def renew_storage_state_web(
    name: str,
    url: str,
    target: Path,
    signal_dir: Path,
    session_id: str,
    window_position: str,
    window_size: str,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    signal_dir.mkdir(parents=True, exist_ok=True)

    width, height = [int(part.strip()) for part in window_size.split(",", 1)]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=_browser_args(window_position, window_size),
        )
        context_args = {
            "user_agent": BROWSER_USER_AGENT,
            "locale": BROWSER_LOCALE,
            "viewport": {"width": width, "height": height},
        }
        if target.exists() and target.stat().st_size > 10:
            context_args["storage_state"] = str(target)
        context = browser.new_context(**context_args)
        page = context.new_page()
        page.goto(url)
        _wait_for_web_complete(name, signal_dir, session_id)
        context.storage_state(path=str(target))
        browser.close()


def renew_x_profile() -> None:
    _require_tty()
    x_user_data().mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(x_user_data()),
            channel="chrome",
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/i/flow/login")
        try:
            input("[X] 로그인 완료 후 Enter: ")
            export_x_artifacts_from_context(context)
            print("USER_DATA_OK")
        finally:
            context.close()


def renew_x_profile_web(
    signal_dir: Path,
    session_id: str,
    window_position: str,
    window_size: str,
) -> None:
    signal_dir.mkdir(parents=True, exist_ok=True)
    x_user_data().mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(x_user_data()),
            channel="chrome",
            headless=False,
            args=_browser_args(window_position, window_size),
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/i/flow/login")
        try:
            _wait_for_web_complete("X", signal_dir, session_id)
            export_x_artifacts_from_context(context)
            print("USER_DATA_OK")
        finally:
            context.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Renew SNS auth runtime artifacts.")
    parser.add_argument("targets", nargs="*", default=["linkedin", "threads", "skool", "x"])
    parser.add_argument("--web", action="store_true", help="Wait for a completion signal instead of terminal input.")
    parser.add_argument("--session-id", default="", help="Web renewal session id.")
    parser.add_argument(
        "--signal-dir",
        default=str(Path(tempfile.gettempdir()) / "scrap_sns_auth_runtime"),
        help="Directory containing web completion signal files.",
    )
    parser.add_argument("--window-position", default="80,80")
    parser.add_argument("--window-size", default="1100,800")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    requested = args.targets or ["linkedin", "threads", "skool", "x"]
    if "all" in requested:
        requested = ["linkedin", "threads", "skool", "x"]

    mapping = {
        "linkedin": ("LinkedIn", "https://www.linkedin.com/login", linkedin_storage()),
        "threads": ("Threads", "https://www.threads.com/login", threads_storage()),
        "skool": ("Skool", "https://www.skool.com/login", skool_storage()),
    }

    try:
        if args.web and len(requested) != 1:
            print("❌ web mode requires exactly one target")
            return 1
        if args.web and not args.session_id:
            print("❌ web mode requires --session-id")
            return 1

        for target in requested:
            if target in mapping:
                name, url, storage_path = mapping[target]
                if args.web:
                    renew_storage_state_web(
                        name,
                        url,
                        storage_path,
                        Path(args.signal_dir),
                        args.session_id,
                        args.window_position,
                        args.window_size,
                    )
                else:
                    renew_storage_state(name, url, storage_path)
            elif target == "x":
                if args.web:
                    renew_x_profile_web(
                        Path(args.signal_dir),
                        args.session_id,
                        args.window_position,
                        args.window_size,
                    )
                else:
                    renew_x_profile()
            else:
                print(f"알 수 없는 대상: {target}")
                return 1
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
