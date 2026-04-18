import json

import twitter_scrap_single
from utils.twitter_cli_adapter import TwitterCliDetail


def test_main_writes_temp_outputs_without_touching_repo_paths(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "Unknown",
                        "url": "https://x.com/i/status/2034688795652816948",
                        "media": [],
                        "created_at": "2026-03-19 17:49:46",
                        "date": "2026-03-19",
                        "sequence_id": 79,
                        "is_detail_collected": False,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"
    failure_file.write_text(
        json.dumps(
            {
                "2034688795652816948": {
                    "count": 2,
                    "last_fail": "2026-04-01T00:00:00",
                    "url": "https://x.com/i/status/2034688795652816948",
                }
            }
        ),
        encoding="utf-8",
    )

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": {"auth_token": "token", "ct0": "ct0"},
        fetch_detail=lambda url, target_user, env, timeout=30: TwitterCliDetail(
            full_text="We wanted to come on here to clear the air and confirm that the rumors are true...",
            media=[],
            real_user="NotebookLM",
        ),
        sleep_fn=lambda _seconds: None,
    )

    saved_simple = json.loads(simple_file.read_text(encoding="utf-8-sig"))
    saved_post = saved_simple["posts"][0]
    assert saved_post["is_detail_collected"] is True
    assert saved_post["username"] == "NotebookLM"
    assert saved_post["url"] == "https://x.com/NotebookLM/status/2034688795652816948"
    assert saved_post["source"] == "full_tweet_cli"

    full_files = list(output_dir.glob("twitter_py_full_*.json"))
    assert len(full_files) == 1
    full_data = json.loads(full_files[0].read_text(encoding="utf-8-sig"))
    assert full_data["posts"][0]["full_text"].startswith("We wanted to come on here")

    update_files = list((output_dir / "update").glob("twitter_py_full_update_*.json"))
    assert len(update_files) == 1
    assert json.loads(failure_file.read_text(encoding="utf-8")) == {}


def test_main_normalizes_none_url_before_fetch_detail(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "Unknown",
                        "url": "https://x.com/None/status/2034688795652816948",
                        "media": [],
                        "sequence_id": 79,
                        "is_detail_collected": False,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"
    calls = []

    def fake_fetch_detail(url, target_user, env, timeout=30):
        calls.append(url)
        return TwitterCliDetail(
            full_text="normalized",
            media=[],
            real_user="NotebookLM",
        )

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": {"auth_token": "token", "ct0": "ct0"},
        fetch_detail=fake_fetch_detail,
        sleep_fn=lambda _seconds: None,
    )

    assert calls == ["https://x.com/i/status/2034688795652816948"]


def test_main_persists_failure_when_fetch_detail_raises(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "Unknown",
                        "url": "https://x.com/i/status/2034688795652816948",
                        "media": [],
                        "sequence_id": 79,
                        "is_detail_collected": False,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": {"auth_token": "token", "ct0": "ct0"},
        fetch_detail=lambda url, target_user, env, timeout=30: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
        sleep_fn=lambda _seconds: None,
    )

    saved_simple = json.loads(simple_file.read_text(encoding="utf-8-sig"))
    assert saved_simple["posts"][0]["is_detail_collected"] is False
    failures = json.loads(failure_file.read_text(encoding="utf-8"))
    assert failures["2034688795652816948"]["count"] == 1
    assert failures["2034688795652816948"]["url"] == "https://x.com/i/status/2034688795652816948"


def test_main_syncs_full_output_without_update_when_no_targets(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "NotebookLM",
                        "url": "https://x.com/NotebookLM/status/2034688795652816948",
                        "media": [],
                        "full_text": "already collected",
                        "sequence_id": 79,
                        "is_detail_collected": True,
                        "source": "full_tweet_cli",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": {"auth_token": "token", "ct0": "ct0"},
        fetch_detail=lambda url, target_user, env, timeout=30: TwitterCliDetail(
            full_text="should not be called",
            media=[],
            real_user="NotebookLM",
        ),
        sleep_fn=lambda _seconds: None,
    )

    full_files = list(output_dir.glob("twitter_py_full_*.json"))
    assert len(full_files) == 1
    full_data = json.loads(full_files[0].read_text(encoding="utf-8-sig"))
    assert full_data["posts"][0]["full_text"] == "already collected"
    update_dir = output_dir / "update"
    assert not update_dir.exists()


def test_main_syncs_full_output_when_tokens_missing(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "target-post",
                        "username": "Unknown",
                        "url": "https://x.com/i/status/target-post",
                        "media": [],
                        "sequence_id": 80,
                        "is_detail_collected": False,
                    },
                    {
                        "platform_id": "2034688795652816948",
                        "username": "NotebookLM",
                        "url": "https://x.com/NotebookLM/status/2034688795652816948",
                        "media": [],
                        "full_text": "already collected",
                        "sequence_id": 79,
                        "is_detail_collected": True,
                        "source": "full_tweet_cli",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": None,
        fetch_detail=lambda url, target_user, env, timeout=30: TwitterCliDetail(
            full_text="should not be called",
            media=[],
            real_user="NotebookLM",
        ),
        sleep_fn=lambda _seconds: None,
    )

    full_files = list(output_dir.glob("twitter_py_full_*.json"))
    assert len(full_files) == 1
    full_data = json.loads(full_files[0].read_text(encoding="utf-8-sig"))
    assert len(full_data["posts"]) == 1
    assert full_data["posts"][0]["platform_id"] == "2034688795652816948"
    assert full_data["posts"][0]["full_text"] == "already collected"
    update_dir = output_dir / "update"
    assert not update_dir.exists()


def test_main_merges_same_day_full_file_and_updates_max_sequence_id(tmp_path):
    output_dir = tmp_path / "output_twitter" / "python"
    output_dir.mkdir(parents=True)
    simple_file = output_dir / "twitter_py_simple_20990101.json"
    simple_file.write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "platform_id": "2034688795652816948",
                        "username": "NotebookLM",
                        "url": "https://x.com/NotebookLM/status/2034688795652816948",
                        "media": [],
                        "full_text": "new collected",
                        "sequence_id": 79,
                        "is_detail_collected": True,
                        "source": "full_tweet_cli",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    today = twitter_scrap_single.datetime.now().strftime("%Y%m%d")
    full_file = output_dir / f"twitter_py_full_{today}.json"
    full_file.write_text(
        json.dumps(
            {
                "metadata": {
                    "updated_at": "2026-04-01T00:00:00",
                    "total_count": 1,
                    "max_sequence_id": 50,
                    "platform": "x",
                },
                "posts": [
                    {
                        "platform_id": "legacy-post",
                        "username": "Legacy",
                        "url": "https://x.com/Legacy/status/legacy-post",
                        "media": [],
                        "full_text": "legacy full",
                        "sequence_id": 50,
                        "is_detail_collected": True,
                        "source": "full_tweet_cli",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    failure_file = tmp_path / "scrap_failures_twitter.json"

    twitter_scrap_single.main(
        limit=1,
        output_dir=str(output_dir),
        failure_file=str(failure_file),
        auth_dir=str(tmp_path / "auth"),
        token_loader=lambda auth_dir="auth": None,
        fetch_detail=lambda url, target_user, env, timeout=30: TwitterCliDetail(
            full_text="should not be called",
            media=[],
            real_user="NotebookLM",
        ),
        sleep_fn=lambda _seconds: None,
    )

    merged = json.loads(full_file.read_text(encoding="utf-8-sig"))
    assert merged["metadata"]["max_sequence_id"] == 79
    assert merged["metadata"]["total_count"] == 2
    assert [post["platform_id"] for post in merged["posts"]] == [
        "2034688795652816948",
        "legacy-post",
    ]
