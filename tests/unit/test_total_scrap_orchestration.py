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


def test_run_calls_cleanup_after_save_total_success(tmp_path):
    script = r"""
import json
import total_scrap

events = []

def fake_run_scrapers_in_parallel(mode="update"):
    events.append(["run_scrapers", mode])
    return {"threads": {"status": "ok"}}

def fake_merge_results():
    events.append(["merge_results"])
    return ([{"platform_id": "1", "media": []}], 1, 0, 0)

def fake_download_images(posts):
    events.append(["download_images", len(posts)])

def fake_save_total(posts, threads_count, linkedin_count, twitter_count, local_image_link_posts=None):
    events.append(["save_total", len(posts), threads_count, linkedin_count, twitter_count])

def fake_cleanup():
    events.append(["cleanup"])
    return True

total_scrap.run_scrapers_in_parallel = fake_run_scrapers_in_parallel
total_scrap.merge_results = fake_merge_results
total_scrap.download_images = fake_download_images
total_scrap.save_total = fake_save_total
total_scrap.cleanup_old_output_json_after_success = fake_cleanup

total_scrap.run(mode="update")
print(json.dumps(events, ensure_ascii=False))
"""

    completed = _run_total_scrap_probe(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == [
        ["run_scrapers", "update"],
        ["merge_results"],
        ["download_images", 1],
        ["save_total", 1, 1, 0, 0],
        ["cleanup"],
    ]


def test_run_update_downloads_images_only_for_posts_missing_from_previous_total(tmp_path):
    script = f"""
import json
from pathlib import Path
import total_scrap

events = []
output_total = Path({str(tmp_path / "output_total")!r})
output_total.mkdir()
image_path = Path({str(tmp_path / "web_viewer" / "images" / "old.jpg")!r})
image_path.parent.mkdir(parents=True)
image_path.write_bytes(b"old")
(output_total / "total_full_20990101.json").write_text(json.dumps({{
    "posts": [
        {{
            "sns_platform": "linkedin",
            "platform_id": "old-post",
            "media": ["https://media.licdn.com/old.jpg"],
            "local_images": ["web_viewer/images/old.jpg"]
        }}
    ]
}}, ensure_ascii=False), encoding="utf-8")

def fake_run_scrapers_in_parallel(mode="update"):
    events.append(["run_scrapers", mode])
    return {{"threads": {{"status": "ok"}}}}

def fake_merge_results():
    events.append(["merge_results"])
    return ([
        {{"sns_platform": "linkedin", "platform_id": "old-post", "media": ["https://media.licdn.com/old.jpg"]}},
        {{"sns_platform": "linkedin", "platform_id": "new-post", "media": ["https://media.licdn.com/new.jpg"]}},
    ], 0, 2, 0)

def fake_download_images(posts):
    events.append(["download_images", [post["platform_id"] for post in posts]])

def fake_save_total(posts, threads_count, linkedin_count, twitter_count, local_image_link_posts=None):
    events.append(["save_total", [post["platform_id"] for post in posts]])
    old_post = next(post for post in posts if post["platform_id"] == "old-post")
    events.append(["old_local_images", old_post.get("local_images")])

total_scrap.PROJECT_ROOT = str(Path({str(tmp_path)!r}))
total_scrap.OUTPUT_TOTAL_DIR = str(output_total)
total_scrap.run_scrapers_in_parallel = fake_run_scrapers_in_parallel
total_scrap.merge_results = fake_merge_results
total_scrap.download_images = fake_download_images
total_scrap.save_total = fake_save_total
total_scrap.cleanup_old_output_json_after_success = lambda: True

total_scrap.run(mode="update")
print(json.dumps(events, ensure_ascii=False))
"""

    completed = _run_total_scrap_probe(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == [
        ["run_scrapers", "update"],
        ["merge_results"],
        ["download_images", ["new-post"]],
        ["save_total", ["old-post", "new-post"]],
        ["old_local_images", ["web_viewer/images/old.jpg"]],
    ]


def test_run_does_not_cleanup_when_save_total_fails(tmp_path):
    script = r"""
import json
import total_scrap

events = []

total_scrap.run_scrapers_in_parallel = lambda mode="update": {}
total_scrap.merge_results = lambda: ([{"platform_id": "1", "media": []}], 1, 0, 0)
total_scrap.download_images = lambda posts: events.append(["download_images"])

def fake_save_total(*args, **kwargs):
    events.append(["save_total"])
    raise RuntimeError("save failed")

def fake_cleanup():
    events.append(["cleanup"])

total_scrap.save_total = fake_save_total
total_scrap.cleanup_old_output_json_after_success = fake_cleanup

try:
    total_scrap.run(mode="update")
except RuntimeError as exc:
    print(json.dumps({"error": str(exc), "events": events}, ensure_ascii=False))
"""

    completed = _run_total_scrap_probe(script, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {
        "error": "save failed",
        "events": [["download_images"], ["save_total"]],
    }
