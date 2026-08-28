"""`/api/run-scrap` 중복 실행 가드.

두 벌이 동시에 돌면 인증 방식과 무관하게 같은 날짜 output JSON, 통합본,
youtube 요약 ledger, 서버 전역 진행 상태가 겹친다.
"""

import time


def _mark_running(server, *, run_id="run-1", elapsed_seconds=0):
    """실행 중 상태를 만든다. started_monotonic 을 과거로 밀어 경과를 흉내낸다."""
    with server.SCRAP_PROGRESS_LOCK:
        server.SCRAP_PROGRESS.update(
            {
                "run_id": run_id,
                "running": True,
                "seq": 0,
                "events": [],
                "started_at": "2026-08-28T18:00:00+09:00",
                "started_monotonic": time.monotonic() - elapsed_seconds,
                "updated_at": "2026-08-28T18:00:00+09:00",
                "platform_list_new_counts": {},
            }
        )


def _clear_running(server):
    with server.SCRAP_PROGRESS_LOCK:
        server.SCRAP_PROGRESS["running"] = False
        server.SCRAP_PROGRESS["started_monotonic"] = None


def test_rejects_second_run_with_409_and_does_not_spawn(app, monkeypatch):
    import scrap_sns_server as server

    spawned = []
    monkeypatch.setattr(
        server.subprocess, "Popen", lambda *a, **k: spawned.append(a) or (_ for _ in ()).throw(AssertionError("spawned"))
    )
    _mark_running(server, run_id="running-run", elapsed_seconds=42)
    try:
        response = app.test_client().post("/api/run-scrap", json={"mode": "update"})
    finally:
        _clear_running(server)

    assert response.status_code == 409
    body = response.get_json()
    assert body["status"] == "error"
    assert body["running_run_id"] == "running-run"
    assert body["elapsed_seconds"] >= 42
    assert spawned == []


def test_guard_does_not_overwrite_running_progress(app, monkeypatch):
    """거부된 요청이 진행 상태를 덮어쓰면 실행 중인 쪽의 진행률이 사라진다."""
    import scrap_sns_server as server

    monkeypatch.setattr(
        server.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned"))
    )
    _mark_running(server, run_id="keep-me", elapsed_seconds=10)
    try:
        app.test_client().post("/api/run-scrap", json={"mode": "update"})
        assert server.SCRAP_PROGRESS["run_id"] == "keep-me"
        assert server.SCRAP_PROGRESS["running"] is True
    finally:
        _clear_running(server)


def test_stale_run_is_reclaimed(app, monkeypatch):
    """비정상 종료로 running 이 남으면 서버 재시작 전까지 영구히 막힌다."""
    import scrap_sns_server as server

    class _FakeProc:
        stdout = None
        returncode = 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **k: _FakeProc())
    _mark_running(
        server, run_id="dead-run", elapsed_seconds=server.SCRAP_STALE_SECONDS + 60
    )
    try:
        response = app.test_client().post("/api/run-scrap", json={"mode": "update"})
    finally:
        _clear_running(server)

    assert response.status_code != 409


def test_active_scrap_run_helper_respects_threshold():
    import scrap_sns_server as server

    _mark_running(server, run_id="fresh", elapsed_seconds=5)
    try:
        with server.SCRAP_PROGRESS_LOCK:
            assert server._active_scrap_run() is not None

        _mark_running(
            server, run_id="stale", elapsed_seconds=server.SCRAP_STALE_SECONDS + 1
        )
        with server.SCRAP_PROGRESS_LOCK:
            assert server._active_scrap_run() is None
    finally:
        _clear_running(server)


def test_stale_threshold_covers_observed_max_runtime():
    """실측 관측 최대 13분 05초. 그보다 넉넉해야 정상 실행을 stale 로 오판하지 않는다."""
    import scrap_sns_server as server

    observed_max_seconds = 13 * 60 + 5
    assert server.SCRAP_STALE_SECONDS > observed_max_seconds * 10
