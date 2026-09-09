"""벤치마킹 LinkedIn 수집을 한 프로세스로 합친 뒤에도 실패가 번지지 않는지 본다.

종전에는 계정마다 자식 프로세스라 OS 가 격리를 공짜로 해줬다. 한 프로세스로
합친 지금은 코드가 그 일을 대신한다 - 그래서 이 테스트가 필요하다.
계획: _docs/20260909_01 (W6-2, W6-4, T6-a)
"""

import pytest

import linkedin_scrap_benchmark as runner
import total_scrap
from utils.auth_status import AUTH_REQUIRED_EXIT_CODE, AuthRequiredError


class FakePage:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self):
        self.pages = []

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


def make_fake_scraper(behavior):
    """slug -> 동작('ok' | 'boom' | 'auth') 을 받아 가짜 수집기를 만든다."""

    calls = []

    class FakeScraper:
        def __init__(self, user_id, **kwargs):
            self.user_id = user_id
            self.kwargs = kwargs

        def run_with_page(self, page):
            calls.append(self.user_id)
            action = behavior.get(self.user_id, "ok")
            if action == "boom":
                raise RuntimeError("수집 중 터졌다")
            if action == "auth":
                raise AuthRequiredError("linkedin", {"reason": "login_required"})

    return FakeScraper, calls


def test_account_error_returns_1_and_does_not_raise(monkeypatch):
    """계정 하나가 터져도 예외가 밖으로 나가지 않는다 - 나가면 나머지 계정이 죽는다."""
    fake, calls = make_fake_scraper({"bad": "boom"})
    monkeypatch.setattr(runner, "LinkedinUserScraper", fake)

    context = FakeContext()
    assert runner.run_collector(context, "bad", 5, False) == 1
    assert calls == ["bad"]


def test_auth_failure_returns_86(monkeypatch):
    """인증 만료는 86 으로 나가야 total_scrap 이 재로그인 안내를 띄운다."""
    fake, _ = make_fake_scraper({"expired": "auth"})
    monkeypatch.setattr(runner, "LinkedinUserScraper", fake)

    context = FakeContext()
    assert runner.run_collector(context, "expired", 5, False) == AUTH_REQUIRED_EXIT_CODE


def test_page_is_closed_even_on_failure(monkeypatch):
    """계정마다 연 page 를 닫는다. 안 닫으면 계정 수만큼 쌓인다."""
    fake, _ = make_fake_scraper({"bad": "boom"})
    monkeypatch.setattr(runner, "LinkedinUserScraper", fake)

    context = FakeContext()
    runner.run_collector(context, "bad", 5, False)
    runner.run_collector(context, "good", 5, False)

    assert len(context.pages) == 2
    assert all(page.closed for page in context.pages)


def test_collect_skips_failed_account_and_continues(monkeypatch, tmp_path):
    """한 계정이 실패해도 그 다음 계정은 수집된다 (W6-4)."""
    accounts = [
        {"id": "a1", "name": "첫째", "channels": {"linkedin": "first"}, "limit": 2},
        {"id": "a2", "name": "둘째", "channels": {"linkedin": "bad"}, "limit": 2},
        {"id": "a3", "name": "셋째", "channels": {"linkedin": "third"}, "limit": 2},
    ]
    monkeypatch.setattr(runner, "load_active_linkedin_accounts", lambda: accounts)

    seen = []

    def fake_run_collector(context, slug, limit, dry_run):
        seen.append(slug)
        return 1 if slug == "bad" else 0

    monkeypatch.setattr(runner, "run_collector", fake_run_collector)
    monkeypatch.setattr(
        runner,
        "latest_full_file",
        lambda slug: str(tmp_path / f"{slug}.json"),
    )
    monkeypatch.setattr(
        runner,
        "load_json",
        lambda path, default: {"posts": [{"code": f"{path[-10:]}1", "full_text": "x"}]},
    )
    monkeypatch.setattr(runner, "load_existing_posts", lambda *a, **k: [])
    monkeypatch.setattr(runner, "merge_and_cap", lambda existing, merged: (merged, []))
    monkeypatch.setattr(runner, "report_removed", lambda removed: None)
    monkeypatch.setattr(runner, "atomic_save_json", lambda path, payload: True)

    count, auth_required = runner.collect(None, False, None)

    assert seen == ["first", "bad", "third"], "실패한 계정 뒤로 진행이 멈췄다"
    assert auth_required is False
    assert count > 0


def test_collect_stops_on_auth_failure(monkeypatch, tmp_path):
    """인증 실패는 예외다 - 남은 계정도 같은 세션이라 즉시 멈춘다(현행 규칙 유지)."""
    accounts = [
        {"id": "a1", "name": "첫째", "channels": {"linkedin": "first"}, "limit": 2},
        {"id": "a2", "name": "둘째", "channels": {"linkedin": "expired"}, "limit": 2},
        {"id": "a3", "name": "셋째", "channels": {"linkedin": "third"}, "limit": 2},
    ]
    monkeypatch.setattr(runner, "load_active_linkedin_accounts", lambda: accounts)

    seen = []

    def fake_run_collector(context, slug, limit, dry_run):
        seen.append(slug)
        return AUTH_REQUIRED_EXIT_CODE if slug == "expired" else 0

    monkeypatch.setattr(runner, "run_collector", fake_run_collector)
    monkeypatch.setattr(runner, "latest_full_file", lambda slug: str(tmp_path / f"{slug}.json"))
    monkeypatch.setattr(
        runner,
        "load_json",
        lambda path, default: {"posts": [{"code": "1234567890", "full_text": "x"}]},
    )
    monkeypatch.setattr(runner, "load_existing_posts", lambda *a, **k: [])
    monkeypatch.setattr(runner, "merge_and_cap", lambda existing, merged: (merged, []))
    monkeypatch.setattr(runner, "report_removed", lambda removed: None)
    monkeypatch.setattr(runner, "atomic_save_json", lambda path, payload: True)

    _, auth_required = runner.collect(None, False, None)

    assert seen == ["first", "expired"], "인증 실패 후에도 계정을 계속 돌았다"
    assert auth_required is True


def test_saved_post_failure_cannot_block_benchmark_wave():
    """저장글 수집과 벤치마킹 수집이 서로 다른 웨이브에 있고 `&&` 로 묶이지 않는다.

    같은 웨이브에 넣거나 `&&` 로 이으면 저장글 수집 실패가 벤치마킹까지 멈춘다.
    웨이브 사이에는 중단 조건이 없으므로, 이 구조가 곧 실패 격리다 (R3).
    """
    phases = total_scrap.build_phase_commands("update")
    phase_names = [name for name, _ in phases]
    assert phase_names == ["producer", "consumer", "benchmark"]

    producer = dict(phases[0][1])
    benchmark = dict(phases[2][1])

    assert "LinkedIn" in producer, "저장글 LinkedIn 수집이 producer 에 없다"
    assert "BenchLinkedIn" in benchmark, "벤치마킹 LinkedIn 수집이 benchmark 웨이브에 없다"

    for slot, command in benchmark.items():
        assert "&&" not in command, f"{slot} 이 다른 명령과 직렬로 묶여 있다"


@pytest.mark.parametrize("slot", ["LinkedIn", "MyPosts"])
def test_login_session_slots_never_share_a_wave_with_bench_linkedin(slot):
    """로그인 세션을 쓰는 슬롯과 벤치마킹 LinkedIn 이 같은 웨이브에 있으면 안 된다.

    같은 계정 세션 2개가 동시에 붙는다. 공용 세션 파일 하나를 두 프로세스가
    읽고 쓰게 되고, 만료 시 어느 쪽 상태가 남는지 보장이 없다.
    """
    phases = dict(total_scrap.build_phase_commands("update"))
    for name, commands in phases.items():
        if "BenchLinkedIn" in commands:
            assert slot not in commands, f"{slot} 이 BenchLinkedIn 과 같은 웨이브({name})에 있다"
