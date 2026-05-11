import json
import os
import subprocess
import sys
from pathlib import Path


def _run_total_scrap_probe(script: str, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_read_auth_signal_from_log_ignores_stale_signal_before_offset(tmp_path):
    script = r"""
import json
from pathlib import Path
import total_scrap

log_path = Path("x_twitter.log")
stale_line = (
    'SNS_AUTH_REQUIRED {"platform":"x","reason":"login_required",'
    '"current_url":"https://x.com/i/flow/login"}\n'
)
log_path.write_text(stale_line, encoding="utf-8")
offset = log_path.stat().st_size
current_line = (
    'SNS_AUTH_REQUIRED {"platform":"x","reason":"login_required",'
    '"current_url":"https://x.com/i/bookmarks"}\n'
)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(current_line)

print(json.dumps(total_scrap._read_auth_signal_from_log(str(log_path), offset), ensure_ascii=False))
"""

    completed = _run_total_scrap_probe(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {
        "platform": "x",
        "reason": "login_required",
        "current_url": "https://x.com/i/bookmarks",
    }


def test_read_auth_signal_from_log_returns_none_when_current_phase_has_no_signal(tmp_path):
    script = r"""
import json
from pathlib import Path
import total_scrap

log_path = Path("x_twitter.log")
log_path.write_text(
    'SNS_AUTH_REQUIRED {"platform":"x","reason":"login_required","current_url":"https://x.com/i/flow/login"}\n',
    encoding="utf-8",
)
offset = log_path.stat().st_size
with log_path.open("a", encoding="utf-8") as handle:
    handle.write("normal current run output\n")

print(json.dumps(total_scrap._read_auth_signal_from_log(str(log_path), offset), ensure_ascii=False))
"""

    completed = _run_total_scrap_probe(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) is None


def test_run_scrapers_in_parallel_runs_consumers_in_second_wave_even_when_initial_check_is_false(
    tmp_path,
):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    script = f"""
import json
import total_scrap

launched_commands = []

class FakeProcess:
    _next_pid = 1000

    def __init__(self, command):
        self.command = command
        self.pid = FakeProcess._next_pid
        FakeProcess._next_pid += 1
        self.returncode = 0

    def poll(self):
        return self.returncode

def fake_popen(command, creationflags=None, stdout=None, stderr=None, env=None, cwd=None):
    launched_commands.append({{"command": command, "cwd": cwd}})
    return FakeProcess(command)

total_scrap.running_processes = []
total_scrap.opened_log_files = []
total_scrap.should_run_consumer = lambda platform: False
total_scrap.subprocess.Popen = fake_popen

results = total_scrap.run_scrapers_in_parallel(mode="update")
print(json.dumps({{"commands": launched_commands, "results": results}}, ensure_ascii=False))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert [item["command"] for item in payload["commands"]] == [
        "cmd /c python -u thread_scrap.py --mode update",
        "cmd /c python -u twitter_scrap.py --mode update",
        "cmd /c python -u linkedin_scrap.py --mode update",
        "cmd /c python -u thread_scrap_single.py",
        "cmd /c python -u twitter_scrap_single.py",
    ]
    assert payload["results"]["threads"]["status"] == "ok"
    assert payload["results"]["threads"]["phases"]["producer"]["status"] == "ok"
    assert payload["results"]["threads"]["phases"]["consumer"]["status"] == "ok"
    assert payload["results"]["x"]["status"] == "ok"
    assert payload["results"]["x"]["phases"]["producer"]["status"] == "ok"
    assert payload["results"]["x"]["phases"]["consumer"]["status"] == "ok"
    assert payload["results"]["linkedin"]["status"] == "ok"
    assert payload["results"]["linkedin"]["phases"]["producer"]["status"] == "ok"
