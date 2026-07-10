import json
from datetime import datetime
from pathlib import Path

import pytest

from linkedin_scrap import (
    configure_text_output,
    merge_linkedin_full_posts,
    validate_opencli_payload,
)


class FakeCp949Stream:
    encoding = "cp949"

    def __init__(self):
        self.reconfigured = None

    def reconfigure(self, **kwargs):
        self.reconfigured = kwargs


def test_configure_text_output_switches_cp949_stream_to_utf8():
    stream = FakeCp949Stream()

    configure_text_output(stream)

    assert stream.reconfigured == {"encoding": "utf-8", "errors": "replace"}


def test_opencli_pipeline_merges_without_deleting_unobserved_existing():
    old_posts = [
        {"platform_id": "111", "sequence_id": 1, "full_text": "old retained", "media": []},
        {
            "platform_id": "222",
            "sequence_id": 2,
            "crawled_at": "2026-07-01T10:00:00",
            "full_text": "old updated",
            "media": [],
        },
    ]
    opencli_posts = [
        {"platform_id": "222", "sequence_id": 0, "full_text": "new text", "media": ["m1"]},
        {"platform_id": "333", "sequence_id": 0, "full_text": "new saved", "media": []},
    ]

    final_posts, new_items, report = merge_linkedin_full_posts(old_posts, opencli_posts, "update only")

    ids = {post["platform_id"] for post in final_posts}
    assert ids == {"111", "222", "333"}
    assert len(new_items) == 1
    assert report["unobserved_existing_count"] == 1
    updated = next(post for post in final_posts if post["platform_id"] == "222")
    assert updated["sequence_id"] == 2
    assert updated["crawled_at"] == "2026-07-01T10:00:00"
    assert updated["media"] == ["m1"]


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"parsed_post_count": 0}, "OpenCLI parsed post count is zero"),
        (
            {"parsed_post_count": 1, "duplicate_platform_id_count": 1},
            "OpenCLI duplicate platform_id detected",
        ),
        (
            {"parsed_post_count": 1, "parser_failed_count": 1},
            "OpenCLI parser failed for one or more posts",
        ),
        (
            {"parsed_post_count": 1, "entity_without_save_state_count": 1},
            "OpenCLI SaveState verification failed",
        ),
        (
            {"parsed_post_count": 1, "entity_without_cluster_reference_count": 1},
            "OpenCLI cluster reference verification failed",
        ),
    ],
)
def test_validation_failure_stops_before_writing_full_file(metadata, message):
    payload = {
        "metadata": {
            "parsed_post_count": 1,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
            **metadata,
        },
        "posts": [],
    }

    with pytest.raises(RuntimeError, match=message):
        validate_opencli_payload(payload)


def test_validate_opencli_payload_accepts_clean_payload():
    payload = {
        "metadata": {
            "parsed_post_count": 1,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
        },
        "posts": [{"platform_id": "333"}],
    }

    validate_opencli_payload(payload)


def test_collect_opencli_posts_cleans_browser_session_before_daemon_stop(monkeypatch):
    import linkedin_scrap

    events = []

    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend(["unbind", "close"]),
        raising=False,
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append("stop"), raising=False)
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 1001)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda _hwnd: True)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: None)
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda _hwnd: None)
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_whoami",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: (
            "raw",
            {"pages_collected": 1, "total_unique_activity_ids": 1},
        ),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: {
            "metadata": {
                "parsed_post_count": 1,
                "duplicate_platform_id_count": 0,
                "parser_failed_count": 0,
                "entity_without_save_state_count": 0,
                "entity_without_cluster_reference_count": 0,
            },
            "posts": [{"platform_id": "1"}],
        },
    )

    posts, metadata = linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert posts == [{"platform_id": "1"}]
    assert metadata["opencli_collection"] == {"pages_collected": 1, "total_unique_activity_ids": 1}
    assert events == ["unbind", "close", "stop"]


def test_collect_opencli_posts_keeps_browser_cleanup_when_daemon_stop_is_disabled(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setenv("SCRAP_SNS_KEEP_OPENCLI_DAEMON", "1")
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend(["unbind", "close"]),
        raising=False,
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append("stop"), raising=False)
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 1001)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda _hwnd: True)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: None)
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda _hwnd: None)
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_whoami",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": "me"},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: (
            "raw",
            {"pages_collected": 1, "total_unique_activity_ids": 1},
        ),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: {
            "metadata": {
                "parsed_post_count": 1,
                "duplicate_platform_id_count": 0,
                "parser_failed_count": 0,
                "entity_without_save_state_count": 0,
                "entity_without_cluster_reference_count": 0,
            },
            "posts": [{"platform_id": "1"}],
        },
    )

    linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == ["unbind", "close"]


def test_cleanup_opencli_browser_session_attempts_close_after_unbind_failure(monkeypatch):
    import linkedin_scrap

    events = []

    def fake_browser_command(action, session=linkedin_scrap.OPENCLI_PRODUCTION_SESSION):
        events.append(action)
        return action != "unbind"

    monkeypatch.setattr(linkedin_scrap, "run_opencli_browser_session_command", fake_browser_command)

    linkedin_scrap.cleanup_opencli_browser_session()

    assert events == ["unbind", "close"]


def test_run_opencli_collector_uses_bound_session_for_production(monkeypatch, tmp_path):
    import linkedin_scrap

    commands = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = '{"pages_collected": 1, "total_unique_activity_ids": 1}'
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap, "OPENCLI_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    raw_dir, summary = linkedin_scrap.run_opencli_collector(datetime(2026, 7, 9, 13, 0, 0))

    assert raw_dir.endswith("raw\\20260709_130000") or raw_dir.endswith("raw/20260709_130000")
    assert summary == {"pages_collected": 1, "total_unique_activity_ids": 1}
    assert len(commands) == 1
    assert "--use-bound-session" in commands[0]


def test_is_opencli_daemon_running_does_not_match_not_running(monkeypatch):
    import linkedin_scrap

    class FakeCompletedProcess:
        returncode = 0
        stdout = "Daemon: not running"
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    assert linkedin_scrap.is_opencli_daemon_running() is False


def test_bind_opencli_browser_session_retries_until_saved_posts_url(monkeypatch):
    import linkedin_scrap

    commands = []
    sleeps = []
    payloads = [
        '{"session":"linkedin_saved_production","url":"https://my-bookstations.vercel.app/","title":"마이 북스테이션"}',
        '{"session":"linkedin_saved_production","url":"https://www.linkedin.com/my-items/saved-posts/","title":"저장한 게시물 | LinkedIn"}',
    ]

    class FakeCompletedProcess:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess(payloads.pop(0))

    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)
    monkeypatch.setattr(linkedin_scrap.time, "sleep", lambda interval: sleeps.append(interval))

    linkedin_scrap.bind_opencli_browser_session(retry_interval=0)

    assert len(commands) == 2
    assert sleeps == [0]


def test_collect_opencli_posts_cleans_opencli_after_wrong_url_bind_failure(monkeypatch):
    import linkedin_scrap

    events = []

    class FakeCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, capture_output, text, encoding):
        if command[-2:] == ["daemon", "status"]:
            events.append(("daemon_status", None))
            return FakeCompletedProcess(stdout="Daemon: not running")
        if command[-2:] == ["daemon", "stop"]:
            events.append(("daemon_stop", None))
            return FakeCompletedProcess(stdout="Daemon stopped.")

        action = command[-1]
        if action == "bind":
            events.append(("bind", None))
            return FakeCompletedProcess(
                stdout='{"session":"linkedin_saved_production","url":"https://wrong.example/","title":"Wrong"}'
            )
        if action in {"unbind", "close"}:
            events.append((action, None))
            return FakeCompletedProcess(stdout="{}")

        pytest.fail(f"unexpected OpenCLI command: {command}")

    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 6161)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda hwnd: events.append(("focus", hwnd)) or True)
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)
    monkeypatch.setattr(linkedin_scrap.time, "sleep", lambda _interval: None)
    monkeypatch.setattr(linkedin_scrap, "validate_bound_opencli_session", lambda: pytest.fail("validation must not run"))
    monkeypatch.setattr(linkedin_scrap, "run_opencli_collector", lambda _crawl_start_time: pytest.fail("collector must not run"))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="OpenCLI browser bind attached to unexpected URL: https://wrong.example/"):
        linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == [
        ("focus", 6161),
        ("daemon_status", None),
        ("bind", None),
        ("bind", None),
        ("bind", None),
        ("unbind", None),
        ("close", None),
        ("daemon_stop", None),
        ("wm_close", 6161),
    ]


def _clean_payload():
    return {
        "metadata": {
            "parsed_post_count": 1,
            "duplicate_platform_id_count": 0,
            "parser_failed_count": 0,
            "entity_without_save_state_count": 0,
            "entity_without_cluster_reference_count": 0,
        },
        "posts": [{"platform_id": "1"}],
    }


def test_collect_opencli_posts_uses_bound_validation_without_whoami(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setattr(linkedin_scrap, "run_opencli_whoami", lambda: pytest.fail("whoami must not run"))
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 1001)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda hwnd: events.append(("focus", hwnd)) or True)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: events.append(("bind", None)))
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": None},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: ("raw", {"pages_collected": 1, "total_unique_activity_ids": 1}),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: _clean_payload(),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend([("unbind", None), ("close", None)]),
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append(("stop", None)))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    posts, metadata = linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert posts == [{"platform_id": "1"}]
    assert metadata["opencli_whoami"] == {"site": "linkedin", "logged_in": True, "public_id": None}
    assert events == [
        ("focus", 1001),
        ("bind", None),
        ("unbind", None),
        ("close", None),
        ("stop", None),
        ("wm_close", 1001),
    ]


def test_open_owned_chrome_window_fails_before_bind_when_chrome_missing(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setattr(linkedin_scrap, "resolve_chrome_executable", lambda: None)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: events.append("bind"))

    with pytest.raises(RuntimeError, match="Chrome executable not found"):
        linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == []


def test_open_owned_chrome_window_fails_without_closing_when_no_hwnd_candidates(monkeypatch):
    import linkedin_scrap

    events = []
    records = []
    monkeypatch.setattr(linkedin_scrap, "resolve_chrome_executable", lambda: "chrome.exe")
    monkeypatch.setattr(linkedin_scrap, "snapshot_visible_chrome_windows", lambda: [])
    monkeypatch.setattr(linkedin_scrap, "launch_chrome_new_window", lambda _chrome_path: events.append("launch"))
    monkeypatch.setattr(linkedin_scrap, "record_chrome_window_candidates", lambda reason, candidates: records.append((reason, candidates)))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="0 new visible Chrome windows"):
        linkedin_scrap.open_owned_chrome_window(poll_attempts=1, poll_interval=0)

    assert events == ["launch"]
    assert records == [("no_candidates", [])]


def test_open_owned_chrome_window_fails_without_closing_when_hwnd_is_ambiguous(monkeypatch):
    import linkedin_scrap

    baseline = [linkedin_scrap.ChromeWindowInfo(hwnd=10, title="Existing - Chrome", process_id=100)]
    candidates = [
        linkedin_scrap.ChromeWindowInfo(hwnd=11, title="Saved Posts - Chrome", process_id=101),
        linkedin_scrap.ChromeWindowInfo(hwnd=12, title="Other - Chrome", process_id=102),
    ]
    events = []
    records = []
    snapshots = [baseline, baseline + candidates]
    monkeypatch.setattr(linkedin_scrap, "resolve_chrome_executable", lambda: "chrome.exe")
    monkeypatch.setattr(linkedin_scrap, "snapshot_visible_chrome_windows", lambda: snapshots.pop(0))
    monkeypatch.setattr(linkedin_scrap, "launch_chrome_new_window", lambda _chrome_path: events.append("launch"))
    monkeypatch.setattr(linkedin_scrap, "record_chrome_window_candidates", lambda reason, values: records.append((reason, values)))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="2 new visible Chrome windows"):
        linkedin_scrap.open_owned_chrome_window(poll_attempts=1, poll_interval=0)

    assert events == ["launch"]
    assert records == [("ambiguous_candidates", candidates)]


def test_collect_opencli_posts_closes_only_recorded_hwnd_after_later_failure(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 4242)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda hwnd: events.append(("focus", hwnd)) or True)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: events.append(("bind", None)))
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": None},
    )
    monkeypatch.setattr(linkedin_scrap, "run_opencli_collector", lambda _crawl_start_time: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend([("unbind", None), ("close", None)]),
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append(("stop", None)))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="boom"):
        linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == [
        ("focus", 4242),
        ("bind", None),
        ("unbind", None),
        ("close", None),
        ("stop", None),
        ("wm_close", 4242),
    ]


def test_collect_opencli_posts_fails_before_bind_when_focus_fails(monkeypatch):
    import linkedin_scrap

    events = []
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 5151)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda hwnd: events.append(("focus", hwnd)) or False)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: events.append(("daemon_status", None)) or False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: events.append(("bind", None)))
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: {"site": "linkedin", "logged_in": True, "public_id": None},
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "run_opencli_collector",
        lambda _crawl_start_time: ("raw", {"pages_collected": 1, "total_unique_activity_ids": 1}),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_shadow_raw",
        lambda _raw_dir, _crawl_start_time, require_save_state: _clean_payload(),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend([("unbind", None), ("close", None)]),
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append(("stop", None)))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(RuntimeError, match="OpenCLI Chrome focus failed"):
        linkedin_scrap.collect_opencli_posts(datetime(2026, 7, 9, 13, 0, 0))

    assert events == [("focus", 5151), ("wm_close", 5151)]


def test_bound_validation_authwall_maps_to_auth_required_exit(monkeypatch):
    import linkedin_scrap
    from utils.auth_status import AUTH_REQUIRED_EXIT_CODE

    events = []
    monkeypatch.setattr(linkedin_scrap, "open_owned_chrome_window", lambda: 3003)
    monkeypatch.setattr(linkedin_scrap, "focus_chrome_window", lambda _hwnd: True)
    monkeypatch.setattr(linkedin_scrap, "is_opencli_daemon_running", lambda: False)
    monkeypatch.setattr(linkedin_scrap, "bind_opencli_browser_session", lambda: None)
    monkeypatch.setattr(
        linkedin_scrap,
        "validate_bound_opencli_session",
        lambda: (_ for _ in ()).throw(linkedin_scrap.LinkedInAuthRequiredError("checkpoint", "https://www.linkedin.com/checkpoint/")),
    )
    monkeypatch.setattr(
        linkedin_scrap,
        "cleanup_opencli_browser_session",
        lambda: events.extend(["unbind", "close"]),
    )
    monkeypatch.setattr(linkedin_scrap, "stop_opencli_daemon", lambda: events.append("stop"))
    monkeypatch.setattr(linkedin_scrap, "close_owned_chrome_window", lambda hwnd: events.append(("wm_close", hwnd)))

    with pytest.raises(SystemExit) as exc_info:
        linkedin_scrap.main(["--mode", "update"])

    assert exc_info.value.code == AUTH_REQUIRED_EXIT_CODE
    assert events == ["unbind", "close", "stop", ("wm_close", 3003)]


def test_update_mode_collector_uses_existing_streak_stop(monkeypatch, tmp_path):
    import linkedin_scrap

    commands = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = '{"pages_collected": 2, "total_unique_activity_ids": 20, "end_reason": "existing_streak_20"}'
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "update only")
    monkeypatch.setattr(linkedin_scrap, "OPENCLI_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    raw_dir, summary = linkedin_scrap.run_opencli_collector(
        datetime(2026, 7, 9, 18, 0, 0),
        existing_codes={"111", "222"},
    )

    command = commands[0]
    assert "--use-bound-session" in command
    assert "--until-exhausted" not in command
    assert "--existing-ids-file" in command
    assert "--stop-after-existing-streak" in command
    assert command[command.index("--stop-after-existing-streak") + 1] == "20"
    ids_path = command[command.index("--existing-ids-file") + 1]
    assert json.loads(Path(ids_path).read_text(encoding="utf-8")) == ["111", "222"]
    assert summary["end_reason"] == "existing_streak_20"
    assert raw_dir.endswith("raw\\20260709_180000") or raw_dir.endswith("raw/20260709_180000")


def test_all_mode_collector_keeps_until_exhausted(monkeypatch, tmp_path):
    import linkedin_scrap

    commands = []

    class FakeCompletedProcess:
        returncode = 0
        stdout = '{"pages_collected": 62, "total_unique_activity_ids": 602, "end_reason": "load_button_absent"}'
        stderr = ""

    def fake_run(command, capture_output, text, encoding):
        commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "all")
    monkeypatch.setattr(linkedin_scrap, "OPENCLI_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(linkedin_scrap.subprocess, "run", fake_run)

    linkedin_scrap.run_opencli_collector(
        datetime(2026, 7, 9, 18, 0, 0),
        existing_codes={"111", "222"},
    )

    command = commands[0]
    assert "--use-bound-session" in command
    assert "--until-exhausted" in command
    assert "--existing-ids-file" not in command
    assert "--stop-after-existing-streak" not in command
