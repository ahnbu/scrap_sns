from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_sns_hub_uses_restart_helper_and_catalog_freshness_check():
    launcher = (PROJECT_ROOT / "sns_hub.vbs").read_text(encoding="utf-8")

    assert "scripts\\restart_viewer_server.ps1" in launcher
    assert "api/get-tag-catalog" in launcher
    assert "api/status" in launcher


def test_run_viewer_uses_restart_helper_instead_of_raw_server_start():
    launcher = (PROJECT_ROOT / "run_viewer.bat").read_text(encoding="utf-8")

    assert "scripts\\restart_viewer_server.ps1" in launcher
    assert "start /b python server.py" not in launcher.lower()


def test_restart_helper_restarts_only_server_py_on_port_5000():
    helper = (PROJECT_ROOT / "scripts" / "restart_viewer_server.ps1").read_text(encoding="utf-8")

    assert "Get-NetTCPConnection" in helper
    assert "api/get-tag-catalog" in helper
    assert "server.py" in helper
    assert "Stop-Process" in helper
    assert "taskkill /F /IM python.exe" not in helper
    assert "taskkill" not in helper.lower()
