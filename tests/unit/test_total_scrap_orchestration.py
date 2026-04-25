import json
import os
import subprocess
import sys
from pathlib import Path


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
