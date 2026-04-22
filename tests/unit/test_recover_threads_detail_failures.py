import json
from pathlib import Path

from utils.threads_http_adapter import ThreadsFetchResult


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def test_recover_failures_dry_run_and_apply(tmp_path):
    from scripts.recover_threads_detail_failures import recover_failures

    output_dir = tmp_path / "output_threads" / "python"
    output_dir.mkdir(parents=True)
    full_path = output_dir / "threads_py_full_20990101.json"
    simple_path = output_dir / "threads_py_simple_20990101.json"
    failures_path = tmp_path / "scrap_failures_threads.json"

    seed_post = {
        "sequence_id": 79,
        "platform_id": "ROOT123",
        "sns_platform": "threads",
        "code": "ROOT123",
        "username": "testuser",
        "display_name": "testuser",
        "full_text": "seed",
        "media": [],
        "url": "https://www.threads.com/@testuser/post/ROOT123",
        "created_at": "2026-04-18 10:00:00",
        "date": "2026-04-18",
        "crawled_at": "2026-04-18T10:00:00",
        "source": "network",
        "local_images": [],
        "is_detail_collected": False,
        "is_merged_thread": False,
    }
    _write_json(full_path, {"metadata": {"total_count": 1}, "posts": [seed_post]})
    _write_json(simple_path, {"metadata": {"total_count": 1}, "posts": [dict(seed_post)]})
    _write_json(failures_path, {"ROOT123": {"fail_count": 3}})

    fixture_html = Path("tests/fixtures/threads_http/sample_post.html").read_text(
        encoding="utf-8"
    )

    common_kwargs = {
        "output_dir": str(output_dir),
        "failures_file": str(failures_path),
        "auth_file": str(tmp_path / "auth_threads.json"),
        "codes": ["ROOT123"],
        "cookie_loader": lambda auth_file=None: {"sessionid": "x"},
        "fetch_fn": lambda url, cookies, headers, timeout=15: ThreadsFetchResult(
            html=fixture_html,
            status_code=200,
        ),
    }

    dry_result = recover_failures(dry_run=True, **common_kwargs)

    assert dry_result["recoverable_count"] == 1
    assert json.loads(full_path.read_text(encoding="utf-8-sig"))["posts"][0][
        "full_text"
    ] == "seed"

    apply_result = recover_failures(dry_run=False, **common_kwargs)

    full_post = json.loads(full_path.read_text(encoding="utf-8-sig"))["posts"][0]
    simple_post = json.loads(simple_path.read_text(encoding="utf-8-sig"))["posts"][0]
    failures = json.loads(failures_path.read_text(encoding="utf-8-sig"))

    assert apply_result["updated_count"] == 1
    assert full_post["is_merged_thread"] is True
    assert full_post["is_detail_collected"] is True
    assert full_post["original_item_count"] == 2
    assert full_post["sequence_id"] == 79
    assert full_post["full_text"] == "Hello TDD World!\n\n---\n\nSecond reply"
    assert simple_post["is_detail_collected"] is True
    assert failures == {}
