import io
import json
from unittest.mock import MagicMock, patch


def _write_total_file(base_dir, date_str, total, threads, linkedin, twitter):
    path = base_dir / f"total_full_{date_str}.json"
    payload = {
        "metadata": {
            "generated_at": f"{date_str}T00:00:00+09:00",
            "total_count": total,
            "threads_count": threads,
            "linkedin_count": linkedin,
            "twitter_count": twitter,
        },
        "posts": [],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _make_process(wait_side_effect=None, output="scraping finished\n"):
    process = MagicMock()
    process.stdout = io.StringIO(output)
    process.wait.side_effect = wait_side_effect
    return process


def test_stats_present_in_response(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260416", total=100, threads=50, linkedin=30, twitter=20)

    def write_after_file():
        _write_total_file(tmp_path, "20260417", total=110, threads=55, linkedin=32, twitter=23)
        return 0

    with patch("subprocess.Popen", return_value=_make_process(write_after_file)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert "stats" in data
    assert set(data["stats"]) >= {
        "total",
        "threads",
        "linkedin",
        "twitter",
        "total_count",
        "threads_count",
        "linkedin_count",
        "twitter_count",
    }


def test_stats_delta_calculation(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260416", total=100, threads=50, linkedin=30, twitter=20)

    def write_after_file():
        _write_total_file(tmp_path, "20260417", total=110, threads=56, linkedin=31, twitter=23)
        return 0

    with patch("subprocess.Popen", return_value=_make_process(write_after_file)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    stats = resp.get_json()["stats"]
    assert stats == {
        "total": 10,
        "threads": 6,
        "linkedin": 1,
        "twitter": 3,
        "total_count": 110,
        "threads_count": 56,
        "linkedin_count": 31,
        "twitter_count": 23,
    }


def test_stats_first_run_no_prior_file(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))

    def write_after_file():
        _write_total_file(tmp_path, "20260417", total=12, threads=5, linkedin=4, twitter=3)
        return 0

    with patch("subprocess.Popen", return_value=_make_process(write_after_file)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    stats = resp.get_json()["stats"]
    assert stats["total"] == 12
    assert stats["threads"] == 5
    assert stats["linkedin"] == 4
    assert stats["twitter"] == 3
    assert stats["total_count"] == 12


def test_phased_summary_marks_auth_required_when_only_consumer_phase_reports_auth(
    client,
    tmp_path,
    monkeypatch,
):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260416", total=100, threads=50, linkedin=30, twitter=20)

    summary_output = "\n".join(
        [
            "scraping finished",
            (
                'SNS_SCRAP_SUMMARY {"platform_results":{"x":{"phases":'
                '{"producer":{"status":"ok"},"consumer":{"status":"auth_required"}}}}}'
            ),
            "",
        ]
    )

    with patch("subprocess.Popen", return_value=_make_process(output=summary_output)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["auth_required"] == ["x"]
    assert payload["platform_results"]["x"]["phases"]["consumer"]["status"] == "auth_required"
