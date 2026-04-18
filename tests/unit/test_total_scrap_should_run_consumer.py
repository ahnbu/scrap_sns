import json
import os
import subprocess
import sys
from pathlib import Path


def test_should_run_consumer_skips_threads_targets_when_fail_count_reaches_limit(
    tmp_path,
):
    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "threads_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "ROOT123",
                        "code": "ROOT123",
                        "is_detail_collected": False,
                    }
                ]
            }
        ),
        encoding="utf-8-sig",
    )
    (tmp_path / "scrap_failures_threads.json").write_text(
        json.dumps({"ROOT123": {"fail_count": 3}}),
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    script = f"""
import total_scrap
total_scrap.OUTPUT_THREADS_DIR = r"{output_dir}"
print(total_scrap.should_run_consumer("Threads"))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
