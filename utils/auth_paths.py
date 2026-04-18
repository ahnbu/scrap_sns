from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_AUTH_HOME = Path.home() / ".config" / "auth"


def auth_home() -> Path:
    return Path(os.environ.get("AUTH_HOME", DEFAULT_AUTH_HOME))


def auth_dir(domain: str) -> Path:
    override = os.environ.get(f"AUTH_HOME_{domain.upper()}")
    return Path(override) if override else auth_home() / domain


def runtime_renew_script() -> Path:
    return auth_home() / "renew.py"


def linkedin_storage() -> Path:
    return auth_dir("linkedin") / "storage_state.json"


def threads_storage() -> Path:
    return auth_dir("threads") / "storage_state.json"


def skool_storage() -> Path:
    return auth_dir("skool") / "storage_state.json"


def x_dir() -> Path:
    return auth_dir("x")


def x_storage() -> Path:
    return x_dir() / "storage_state.json"


def x_user_data() -> Path:
    return x_dir() / "user_data"


def x_cookie_link() -> Path:
    return x_dir() / "cookies.json"


def flat_link(name: str) -> Path:
    return auth_home() / name


def x_flat_cookie() -> Path:
    return flat_link("x_cookies_current.json")


def x_flat_storage() -> Path:
    return flat_link("x_storage_state_current.json")


def _split_x_root(root: str | Path | None) -> tuple[Path, Path]:
    if root is None:
        flat_root = auth_home()
        return flat_root, flat_root / "x"

    path = Path(root)
    if path.name == "x":
        return path.parent, path
    return path, path / "x"


def _read_cookie_values(path: Path) -> dict[str, str] | None:
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    values = {
        item.get("name"): item.get("value")
        for item in cookies
        if item.get("name") in {"auth_token", "ct0"}
    }
    if not values.get("auth_token") or not values.get("ct0"):
        return None
    return {"auth_token": values["auth_token"], "ct0": values["ct0"]}


def x_cookies_latest(root: str | Path | None = None) -> Path | None:
    flat_root, nested_root = _split_x_root(root)
    candidates: list[Path] = []

    for stable in (nested_root / "cookies.json", flat_root / "x_cookies_current.json"):
        if stable.exists():
            candidates.append(stable)

    candidates.extend(sorted(nested_root.glob("cookies_*.json"), reverse=True))
    candidates.extend(sorted(flat_root.glob("x_cookies_*.json"), reverse=True))
    candidates.extend(sorted(flat_root.glob("cookies_*.json"), reverse=True))

    return candidates[0] if candidates else None


def read_x_cookie_tokens(path: str | Path) -> dict[str, str] | None:
    return _read_cookie_values(Path(path))


def validate_x_cookie_target(expected_name: str) -> bool:
    link = x_cookie_link()
    if not link.exists() or not link.is_symlink():
        return False

    try:
        target = link.resolve(strict=True)
    except OSError:
        return False

    return target.name == expected_name and _read_cookie_values(target) is not None
