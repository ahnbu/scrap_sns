import json
import subprocess
from pathlib import Path


def _write_storage_state(path: Path, cookie_name: str, cookie_value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": cookie_name,
                        "value": cookie_value,
                        "domain": ".example.com",
                    }
                ],
                "origins": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_sync_auth_runtime_creates_nested_and_flat_links(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    auth_home = tmp_path / "auth-home"
    legacy_dir = tmp_path / "legacy-auth"
    legacy_dir.mkdir()
    _write_storage_state(legacy_dir / "auth_linkedin.json", "li_at", "aaa")
    _write_storage_state(legacy_dir / "auth_threads.json", "sessionid", "bbb")
    _write_storage_state(legacy_dir / "auth_skool.json", "auth_token", "ccc")

    x_user_data = legacy_dir / "x_user_data"
    x_user_data.mkdir()
    (x_user_data / "Local State").write_text("{}", encoding="utf-8")
    (legacy_dir / "x_cookies_20260318.json").write_text(
        json.dumps(
            [
                {"name": "auth_token", "value": "token"},
                {"name": "ct0", "value": "ct0"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_storage_state(legacy_dir / "x_storage_state_20260318.json", "auth_token", "token")

    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(repo_root / "scripts" / "sync_auth_runtime.ps1"),
            "-SourceRoot",
            str(repo_root),
            "-AuthHome",
            str(auth_home),
            "-LegacyAuthDir",
            str(legacy_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (auth_home / "auth_paths.py").exists()
    assert (auth_home / "renew.py").exists()
    assert (auth_home / "auth_linkedin.json").is_symlink()
    assert (auth_home / "auth_threads.json").is_symlink()
    assert (auth_home / "auth_skool.json").is_symlink()
    assert (auth_home / "x_cookies_current.json").is_symlink()
    assert (auth_home / "x_storage_state_current.json").is_symlink()
    assert (auth_home / "x" / "user_data").exists()
    assert (auth_home / "x" / "cookies_20260318.json").exists()
    assert (auth_home / "x" / "storage_state.json").exists()
    assert (legacy_dir / "auth_paths.py").exists()

    rerun = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(repo_root / "scripts" / "sync_auth_runtime.ps1"),
            "-SourceRoot",
            str(repo_root),
            "-AuthHome",
            str(auth_home),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert rerun.returncode == 0, rerun.stderr
    assert (auth_home / "auth_linkedin.json").is_symlink()
    assert (auth_home / "x_cookies_current.json").is_symlink()
