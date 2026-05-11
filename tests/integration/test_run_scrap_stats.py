import io
import json
from unittest.mock import MagicMock, patch


def _write_total_file(base_dir, date_str, total, threads, linkedin, twitter, posts=None):
    path = base_dir / f"total_full_{date_str}.json"
    payload = {
        "metadata": {
            "generated_at": f"{date_str}T00:00:00+09:00",
            "total_count": total,
            "threads_count": threads,
            "linkedin_count": linkedin,
            "twitter_count": twitter,
        },
        "posts": posts or [],
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


def test_run_scrap_suppresses_x_auth_required_when_signal_url_is_not_auth_page(
    client,
    tmp_path,
    monkeypatch,
):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260510", total=100, threads=50, linkedin=30, twitter=20)

    summary_output = "\n".join(
        [
            "scraping finished",
            (
                'SNS_SCRAP_SUMMARY {"platform_results":{"x":{"status":"auth_required",'
                '"auth_signal":{"platform":"x","reason":"login_required",'
                '"current_url":"https://x.com/i/bookmarks"},'
                '"phases":{"producer":{"status":"auth_required","auth_signal":'
                '{"platform":"x","reason":"login_required","current_url":"https://x.com/i/bookmarks"}},'
                '"consumer":{"status":"ok"}}}},'
                '"auth_required":["x"]}'
            ),
            "",
        ]
    )

    with patch("subprocess.Popen", return_value=_make_process(output=summary_output)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["auth_required"] == []
    assert payload["platform_results"]["x"]["status"] == "failed"
    assert payload["platform_results"]["x"]["auth_suppression"] == {
        "suppressed_auth_required": True,
        "reason": "current_url_not_auth",
        "current_url": "https://x.com/i/bookmarks",
    }


def test_run_scrap_keeps_x_auth_required_when_signal_url_is_login_page(
    client,
    tmp_path,
    monkeypatch,
):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260510", total=100, threads=50, linkedin=30, twitter=20)

    summary_output = "\n".join(
        [
            "scraping finished",
            (
                'SNS_SCRAP_SUMMARY {"platform_results":{"x":{"status":"auth_required",'
                '"auth_signal":{"platform":"x","reason":"login_required",'
                '"current_url":"https://x.com/i/flow/login"},'
                '"phases":{"producer":{"status":"auth_required","auth_signal":'
                '{"platform":"x","reason":"login_required","current_url":"https://x.com/i/flow/login"}}}}},'
                '"auth_required":["x"]}'
            ),
            "",
        ]
    )

    with patch("subprocess.Popen", return_value=_make_process(output=summary_output)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["auth_required"] == ["x"]
    assert "auth_suppression" not in payload["platform_results"]["x"]


def test_run_scrap_response_includes_platform_new_samples(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(
        tmp_path,
        "20260416",
        total=2,
        threads=1,
        linkedin=1,
        twitter=0,
        posts=[
            {
                "sequence_id": 1,
                "platform_id": "li-old",
                "sns_platform": "linkedin",
                "url": "https://www.linkedin.com/feed/update/urn:li:activity:1",
                "full_text": "Old LinkedIn post",
            },
            {
                "sequence_id": 2,
                "platform_id": "th-old",
                "sns_platform": "threads",
                "url": "https://www.threads.com/@user/post/th-old",
                "full_text": "Old Threads post",
            },
        ],
    )

    def write_after_file():
        _write_total_file(
            tmp_path,
            "20260417",
            total=9,
            threads=3,
            linkedin=5,
            twitter=1,
            posts=[
                {
                    "sequence_id": 1,
                    "platform_id": "li-old",
                    "sns_platform": "linkedin",
                    "url": "https://www.linkedin.com/feed/update/urn:li:activity:1",
                    "display_name": "Old Author",
                    "full_text": "Old post",
                    "created_at": "2026-04-16 09:00:00",
                },
                {
                    "sequence_id": 2,
                    "platform_id": "th-old",
                    "sns_platform": "threads",
                    "url": "https://www.threads.com/@user/post/th-old",
                    "full_text": "Old Threads post",
                    "created_at": "2026-04-16 09:00:00",
                },
                {
                    "sequence_id": 3,
                    "platform_id": "li-new-1",
                    "sns_platform": "linkedin",
                    "url": "https://www.linkedin.com/feed/update/urn:li:activity:3",
                    "display_name": "New Author",
                    "full_text": "Unique Harness consistency probe 1",
                    "created_at": "2026-04-17 09:00:00",
                },
                {
                    "sequence_id": 4,
                    "platform_id": "li-new-2",
                    "sns_platform": "linkedin",
                    "url": "https://www.linkedin.com/feed/update/urn:li:activity:4",
                    "full_text": "Unique Harness consistency probe 2",
                    "created_at": "2026-04-17 09:01:00",
                },
                {
                    "sequence_id": 5,
                    "platform_id": "li-new-3",
                    "sns_platform": "linkedin",
                    "url": "https://www.linkedin.com/feed/update/urn:li:activity:5",
                    "full_text": "Unique Harness consistency probe 3",
                    "created_at": "2026-04-17 09:02:00",
                },
                {
                    "sequence_id": 6,
                    "platform_id": "li-new-4",
                    "sns_platform": "linkedin",
                    "url": "https://www.linkedin.com/feed/update/urn:li:activity:6",
                    "full_text": "Unique Harness consistency probe 4",
                    "created_at": "2026-04-17 09:03:00",
                },
                {
                    "sequence_id": 7,
                    "platform_id": "th-new-1",
                    "sns_platform": "threads",
                    "url": "https://www.threads.com/@user/post/th-new-1",
                    "full_text": "New Threads post 1",
                    "created_at": "2026-04-17 09:04:00",
                },
                {
                    "sequence_id": 8,
                    "platform_id": "th-new-2",
                    "sns_platform": "threads",
                    "url": "https://www.threads.com/@user/post/th-new-2",
                    "full_text": "New Threads post 2",
                    "created_at": "2026-04-17 09:05:00",
                },
                {
                    "sequence_id": 9,
                    "platform_id": "x-new-1",
                    "sns_platform": "x",
                    "url": "https://x.com/user/status/x-new-1",
                    "full_text": "New X post 1",
                    "created_at": "2026-04-17 09:00:00",
                },
            ],
        )
        return 0

    with patch("subprocess.Popen", return_value=_make_process(write_after_file)):
        resp = client.post("/api/run-scrap", json={"mode": "update"})

    assert resp.status_code == 200
    consistency = resp.get_json()["consistency_probe"]
    assert consistency["new_counts"] == {"threads": 2, "linkedin": 4, "twitter": 1}
    assert [sample["platform_id"] for sample in consistency["new_samples"]["linkedin"]] == [
        "li-new-4",
        "li-new-3",
        "li-new-2",
    ]
    assert [sample["platform_id"] for sample in consistency["new_samples"]["threads"]] == [
        "th-new-2",
        "th-new-1",
    ]
    assert [sample["platform_id"] for sample in consistency["new_samples"]["twitter"]] == [
        "x-new-1",
    ]


def test_run_scrap_records_filtered_progress_events(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    _write_total_file(tmp_path, "20260416", total=100, threads=50, linkedin=30, twitter=20)

    def write_after_file():
        _write_total_file(tmp_path, "20260417", total=115, threads=52, linkedin=43, twitter=20)
        return 0

    output = "\n".join(
        [
            "🚀 플랫폼별 스크래퍼 병렬 실행 시작 (2-wave 모드)... (모드: update)",
            "🚀 Producer wave 시작...",
            "   [+] Threads Producer 실행 중 (로그: logs/threads.log)...",
            "   [+] LinkedIn Producer 실행 중 (로그: logs/linkedin.log)...",
            "   ✅ Threads Producer 완료.",
            "   ✅ LinkedIn Producer 완료.",
            "📦 결과 병합 및 데이터 정규화 시작...",
            "Traceback with sensitive raw detail should be ignored",
            "SNS_SCRAP_SUMMARY {\"platform_results\":{}}",
            "",
        ]
    )

    with patch("subprocess.Popen", return_value=_make_process(write_after_file, output=output)):
        resp = client.post(
            "/api/run-scrap",
            json={"mode": "update", "run_id": "progress-test"},
        )

    assert resp.status_code == 200

    progress_resp = client.get("/api/scrap-progress?run_id=progress-test&after=0")
    assert progress_resp.status_code == 200
    progress = progress_resp.get_json()
    messages = [event["message"] for event in progress["events"]]

    assert progress["run_id"] == "progress-test"
    assert progress["running"] is False
    assert messages == [
        "최근 업데이트 스크랩 시작",
        "플랫폼별 스크랩 시작",
        "목록 수집 단계 시작",
        "Threads 목록 수집 시작",
        "LinkedIn 목록 수집 시작",
        "Threads 목록 수집 완료",
        "LinkedIn 목록 수집 완료",
        "결과 병합 시작",
        "스크랩 완료: Threads 2건, LinkedIn 13건, X 0건",
    ]
    assert all("Traceback" not in message for message in messages)
    assert all("logs/" not in message for message in messages)

    after_resp = client.get("/api/scrap-progress?run_id=progress-test&after=3")
    assert [event["seq"] for event in after_resp.get_json()["events"]] == list(
        range(4, progress["seq"] + 1)
    )


def test_run_scrap_records_progress_from_child_log_files(client, tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "SCRAP_PROGRESS_LOG_SOURCES",
        {"LinkedIn": str(tmp_path / "linkedin.log")},
        raising=False,
    )
    _write_total_file(tmp_path, "20260416", total=100, threads=50, linkedin=30, twitter=20)
    log_path = tmp_path / "linkedin.log"
    log_path.write_text("", encoding="utf-8")

    def write_after_file():
        log_path.write_text(
            "================================================\n"
            "🚀 LinkedIn Producer 시작: 2026-05-07 10:00:00\n"
            "================================================\n\n"
            "   🔘 '결과 더보기' 버튼 클릭 (현재 42개)\n",
            encoding="utf-8",
        )
        _write_total_file(tmp_path, "20260417", total=101, threads=50, linkedin=31, twitter=20)
        return 0

    with patch(
        "subprocess.Popen",
        return_value=_make_process(
            write_after_file,
            output='SNS_SCRAP_SUMMARY {"platform_results":{}}\n',
        ),
    ):
        resp = client.post(
            "/api/run-scrap",
            json={"mode": "update", "run_id": "child-log-progress-test"},
        )

    assert resp.status_code == 200

    progress_resp = client.get("/api/scrap-progress?run_id=child-log-progress-test&after=0")
    messages = [event["message"] for event in progress_resp.get_json()["events"]]

    assert "LinkedIn 목록 수집 시작" in messages
    assert "LinkedIn 목록 수집 중 42개" in messages


def test_run_scrap_promotes_threads_new_and_retry_counts_with_elapsed_log(
    client,
    tmp_path,
    monkeypatch,
):
    import server

    clock = {"value": 100.0}
    log_path = tmp_path / "threads.log"
    progress_log_path = tmp_path / "scrap_progress.log"

    monkeypatch.setattr(server.time, "monotonic", lambda: clock["value"])
    monkeypatch.setattr(server, "OUTPUT_TOTAL_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "SCRAP_PROGRESS_LOG_SOURCES",
        {"Threads": str(log_path)},
        raising=False,
    )
    monkeypatch.setattr(
        server,
        "SCRAP_PROGRESS_LOG_PATH",
        str(progress_log_path),
        raising=False,
    )
    _write_total_file(tmp_path, "20260508", total=849, threads=849, linkedin=0, twitter=0)
    log_path.write_text("", encoding="utf-8")

    def write_after_file():
        clock["value"] = 136.0
        log_path.write_text(
            "🏁 더 이상 새로운 데이터가 없습니다.\n"
            "💾 최종 데이터 852개 저장 중 (신규: 3개)...\n"
            "[Target] 수집대상 5개 | 기수집 스킵 56개 | 코드없음 스킵 0개 | 실패한도 스킵 30개\n",
            encoding="utf-8",
        )
        _write_total_file(tmp_path, "20260509", total=852, threads=852, linkedin=0, twitter=0)
        return 0

    with patch(
        "subprocess.Popen",
        return_value=_make_process(
            write_after_file,
            output='SNS_SCRAP_SUMMARY {"platform_results":{}}\n',
        ),
    ):
        resp = client.post(
            "/api/run-scrap",
            json={"mode": "update", "run_id": "threads-count-progress-test"},
        )

    assert resp.status_code == 200

    progress_resp = client.get(
        "/api/scrap-progress?run_id=threads-count-progress-test&after=0"
    )
    events = progress_resp.get_json()["events"]
    messages = [event["message"] for event in events]

    assert "Threads 새 데이터 없음" not in messages
    assert "Threads 목록 신규 3건 발견" in messages
    assert (
        "Threads 상세 수집 대상 5건 (신규 3건 + 기존 미완료/재시도 2건)"
        in messages
    )

    elapsed_by_message = {event["message"]: event["elapsed"] for event in events}
    assert elapsed_by_message["Threads 목록 신규 3건 발견"] == "00:36 경과"
    assert (
        elapsed_by_message[
            "Threads 상세 수집 대상 5건 (신규 3건 + 기존 미완료/재시도 2건)"
        ]
        == "00:36 경과"
    )

    progress_log = progress_log_path.read_text(encoding="utf-8")
    assert "00:36 경과 | Threads 목록 신규 3건 발견" in progress_log
    assert (
        "00:36 경과 | Threads 상세 수집 대상 5건 (신규 3건 + 기존 미완료/재시도 2건)"
        in progress_log
    )
    assert "Threads 새 데이터 없음" not in progress_log


def test_scrap_progress_ignores_other_run_id(client):
    resp = client.get("/api/scrap-progress?run_id=missing-run&after=0")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["run_id"] == "missing-run"
    assert payload["running"] is False
    assert payload["events"] == []
