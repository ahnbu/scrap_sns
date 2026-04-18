from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from export_x_artifacts import export_x_artifacts
    from auth_paths import linkedin_storage, skool_storage, threads_storage, x_user_data
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.auth_runtime.export_x_artifacts import export_x_artifacts
    from utils.auth_paths import linkedin_storage, skool_storage, threads_storage, x_user_data


def _require_tty() -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("interactive login required; run this command in a terminal")


def renew_storage_state(name: str, url: str, target: Path) -> None:
    _require_tty()
    target.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context_args = {}
        if target.exists() and target.stat().st_size > 10:
            context_args["storage_state"] = str(target)
        context = browser.new_context(**context_args)
        page = context.new_page()
        page.goto(url)
        input(f"[{name}] 로그인 완료 후 Enter: ")
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
        input("[X] 로그인 완료 후 Enter: ")
        context.close()


def main(argv: list[str]) -> int:
    requested = argv or ["linkedin", "threads", "skool", "x"]
    if "all" in requested:
        requested = ["linkedin", "threads", "skool", "x"]

    mapping = {
        "linkedin": ("LinkedIn", "https://www.linkedin.com/login", linkedin_storage()),
        "threads": ("Threads", "https://www.threads.com/login", threads_storage()),
        "skool": ("Skool", "https://www.skool.com/login", skool_storage()),
    }

    try:
        for target in requested:
            if target in mapping:
                name, url, storage_path = mapping[target]
                renew_storage_state(name, url, storage_path)
            elif target == "x":
                renew_x_profile()
                export_x_artifacts()
            else:
                print(f"알 수 없는 대상: {target}")
                return 1
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
