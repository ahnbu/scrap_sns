import json
from pathlib import Path

import thread_scrap_single
from utils.threads_http_adapter import ThreadsFetchResult


def test_main_writes_outputs_with_mocked_fetch(tmp_path):
    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "threads_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "metadata": {"max_sequence_id": 79},
                "posts": [
                    {
                        "platform_id": "ROOT123",
                        "code": "ROOT123",
                        "username": "testuser",
                        "display_name": "testuser",
                        "url": "https://www.threads.com/@testuser/post/ROOT123",
                        "created_at": "2026-04-18 10:00:00",
                        "date": "2026-04-18",
                        "media": [],
                        "full_text": "seed",
                        "sequence_id": 79,
                        "sns_platform": "threads",
                        "source": "producer",
                        "is_detail_collected": False,
                        "is_merged_thread": False,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_threads.json"
    failure_file.write_text("{}", encoding="utf-8")
    fixture_html = Path("tests/fixtures/threads_http/sample_post.html").read_text(
        encoding="utf-8"
    )

    thread_scrap_single.main(
        output_dir=str(output_dir),
        failures_file=str(failure_file),
        auth_file=str(tmp_path / "auth_threads.json"),
        cookie_loader=lambda auth_file="auth/auth_threads.json": {
            "sessionid": "x",
            "csrftoken": "y",
            "ds_user_id": "1",
        },
        fetch_fn=lambda url, cookies, headers, timeout=15: ThreadsFetchResult(
            html=fixture_html, status_code=200
        ),
        sleep_fn=lambda _seconds: None,
        max_workers=1,
        snapshot_saver=lambda *_args, **_kwargs: None,
    )

    full_files = list(output_dir.glob("threads_py_full_*.json"))
    assert len(full_files) == 1
    full_data = json.loads(full_files[0].read_text(encoding="utf-8-sig"))
    assert len(full_data["posts"]) == 1
    full_post = full_data["posts"][0]
    assert full_post["is_merged_thread"] is True
    assert full_post["original_item_count"] == 2
    assert full_post["source"] == "consumer_detail"
    assert full_post["full_text"] == "Hello TDD World!\n\n---\n\nSecond reply"

    simple_data = json.loads(simple_file.read_text(encoding="utf-8-sig"))
    assert simple_data["posts"][0]["is_detail_collected"] is True
    assert json.loads(failure_file.read_text(encoding="utf-8")) == {}
