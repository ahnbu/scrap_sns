from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_sns_hub_uses_restart_helper():
    launcher = (PROJECT_ROOT / "sns_hub.vbs").read_text(encoding="utf-8")

    assert "scripts\\restart_viewer_server.ps1" in launcher
    assert "api/get-tag-catalog" not in launcher
    assert "api/status" not in launcher


def test_run_viewer_uses_restart_helper_instead_of_raw_server_start():
    launcher = (PROJECT_ROOT / "run_viewer.bat").read_text(encoding="utf-8")
    old_server_name = "server" + ".py"

    assert "scripts\\restart_viewer_server.ps1" in launcher
    assert f"start /b python {old_server_name}" not in launcher.lower()


def test_restart_helper_always_restarts_only_scrap_sns_server_on_port_5000():
    helper = (PROJECT_ROOT / "scripts" / "restart_viewer_server.ps1").read_text(encoding="utf-8")
    old_server_name = "server" + ".py"

    assert "Get-NetTCPConnection" in helper
    assert "scrap_sns_server.py" in helper
    assert f'-ArgumentList "{old_server_name}"' not in helper
    assert f"does not look like {old_server_name}" not in helper
    assert "Test-ViewerServerFresh" not in helper
    assert "Viewer server is fresh" not in helper
    assert "api/get-tag-catalog" in helper
    assert "Stop-Process" in helper
    assert "taskkill /F /IM python.exe" not in helper
    assert "taskkill" not in helper.lower()


def test_restart_helper_allows_one_time_legacy_server_py_migration():
    helper = (PROJECT_ROOT / "scripts" / "restart_viewer_server.ps1").read_text(encoding="utf-8")
    old_server_name = "server" + ".py"

    assert "Test-LegacyViewerServer" in helper
    assert old_server_name in helper
    assert "Test-ViewerServerReady" in helper


def test_sns_hub_failure_message_is_ascii_safe():
    launcher = (PROJECT_ROOT / "sns_hub.vbs").read_text(encoding="utf-8")
    msg_lines = [line.strip() for line in launcher.splitlines() if line.strip().startswith("MsgBox ")]

    assert msg_lines
    for line in msg_lines:
        line.encode("ascii")
