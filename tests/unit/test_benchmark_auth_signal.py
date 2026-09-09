"""벤치마킹 인증 실패가 화면까지 가는 경로를 지킨다.

이 파일이 지키는 것은 하나다 — **인증 신호만 벤치마킹을 알아보고, 수집 결과 표시는
지금대로 둔다.** 둘을 같은 함수로 처리하면 `bench_linkedin` 과 `linkedin` 이 같은 키가
되어 한쪽이 조용히 사라진다.

계획: _docs/20260908_02 (W2-5, W3)
"""

import contextlib
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def server():
    return importlib.import_module("scrap_sns_server")


def test_bench_slot_is_recognized_as_auth_required(server):
    """total_scrap 이 보낸 `bench_linkedin` 이 화면용 `linkedin` 으로 정규화된다."""
    result = server._normalize_scrap_summary({
        "auth_required": ["bench_linkedin"],
        "platform_results": {},
    })
    assert result["auth_required"] == ["linkedin"]


def test_bench_threads_slot_is_recognized(server):
    result = server._normalize_scrap_summary({
        "auth_required": ["bench_threads"],
        "platform_results": {},
    })
    assert result["auth_required"] == ["threads"]


def test_same_platform_is_not_duplicated(server):
    """저장글과 벤치마킹이 함께 만료돼도 안내는 한 줄이다."""
    result = server._normalize_scrap_summary({
        "auth_required": ["linkedin", "bench_linkedin"],
        "platform_results": {},
    })
    assert result["auth_required"] == ["linkedin"]


def test_platform_results_still_separates_bench_from_saved(server):
    """🔴 회귀 방지 — 벤치마킹 결과가 저장글 결과를 덮어쓰면 안 된다.

    `_canonical_auth_platform` 자체에 `bench_` 매핑을 넣으면 이 테스트가 깨진다.
    """
    result = server._normalize_scrap_summary({
        "auth_required": [],
        "platform_results": {
            "linkedin": {"status": "ok", "returncode": 0},
            "bench_linkedin": {"status": "failed", "returncode": 1},
        },
    })
    assert result["platform_results"]["linkedin"]["status"] == "ok", (
        "저장글 수집 결과가 벤치마킹 실패로 덮어써졌다"
    )
    assert "bench_linkedin" not in result["platform_results"]


def test_collection_failure_does_not_become_auth_required(server):
    """일반 수집 실패는 재로그인 안내로 바뀌지 않는다."""
    result = server._normalize_scrap_summary({
        "auth_required": [],
        "platform_results": {"linkedin": {"status": "failed", "returncode": 1}},
    })
    assert result["auth_required"] == []


def test_unknown_slot_is_still_dropped(server):
    result = server._normalize_scrap_summary({
        "auth_required": ["bench_youtube", "my_posts"],
        "platform_results": {},
    })
    assert result["auth_required"] == []


def test_benchmark_runner_exits_with_auth_code(monkeypatch):
    """수집기가 인증 실패를 알리면 벤치마킹 러너도 86으로 끝난다 (삼키지 않는다).

    🔴 신호 방식이 바뀌었다. 종전에는 자식 프로세스의 종료코드 86 을 받았고,
    지금은 한 프로세스 안에서 `AuthRequiredError` 예외를 받는다 - 계정마다
    프로세스를 띄우지 않고 브라우저 하나를 공유하기 때문이다.
    **밖으로 나가는 종료코드 86 은 그대로다.** 계획: _docs/20260909_01 (W6 T6-f)
    """
    runner = importlib.import_module("linkedin_scrap_benchmark")
    from utils.auth_status import AUTH_REQUIRED_EXIT_CODE, AuthRequiredError

    calls = []

    class _FakeScraper:
        def __init__(self, user_id, **kwargs):
            self.user_id = user_id

        def run_with_page(self, page):
            calls.append(self.user_id)
            raise AuthRequiredError("linkedin", {"reason": "login_required"})

    class _FakePage:
        def close(self):
            pass

    class _FakeContext:
        def new_page(self):
            return _FakePage()

    @contextlib.contextmanager
    def fake_browser(dry_run):
        yield None, _FakeContext()

    monkeypatch.setattr(runner, "LinkedinUserScraper", _FakeScraper)
    monkeypatch.setattr(runner, "_open_shared_browser", fake_browser)
    monkeypatch.setattr(runner, "load_active_linkedin_accounts", lambda: [
        {"id": "a1", "channels": {"linkedin": "slug-a"}, "limit": 5},
        {"id": "a2", "channels": {"linkedin": "slug-b"}, "limit": 5},
    ])
    monkeypatch.setattr(runner, "load_existing_posts", lambda *a, **k: [])

    count, auth_required = runner.collect(None, False, None)

    assert auth_required is True
    assert count == 0
    assert len(calls) == 1, "첫 계정이 인증 실패면 남은 계정은 돌지 않는다"

    # 종료코드 규약은 그대로다 - 이 값이 total_scrap 을 거쳐 결과창까지 간다.
    monkeypatch.setattr(runner, "collect", lambda *a, **k: (0, True))
    assert runner.main([]) == AUTH_REQUIRED_EXIT_CODE
