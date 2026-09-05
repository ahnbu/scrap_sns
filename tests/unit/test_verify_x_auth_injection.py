"""probe_producer 가 외부 playwright 를 주입받는 경로를 지킨다.

배경:
    `sync_playwright()` 는 **이미 실행 중인 이벤트 루프** 안에서 부르면 거부한다
    (`Playwright Sync API inside the asyncio loop`). pytest-playwright 의
    `playwright` fixture 는 session 스코프라 한 번 쓰이면 세션 끝까지 루프를 잡는다.

    그래서 LinkedIn·Threads 스모크가 먼저 돌면 X 스모크가 자기 `sync_playwright()`
    를 열다 끊겼다. 단독 실행은 통과하고 함께 돌리면 실패해 「순서 의존」으로 보였지만
    실제 원인은 중첩 호출이었다.

    주입 경로가 사라지면 그 결함이 그대로 돌아온다. 이 테스트가 그것을 막는다.
    브라우저를 띄우지 않으므로 unit 에 둔다.
"""

import pytest

from scripts.auth_runtime import verify_x_auth


class _FakePlaywright:
    """주입 여부만 확인하는 대역. 실제 브라우저를 띄우지 않는다."""

    def __init__(self):
        self.used = False


class _FakeContext:
    def __init__(self):
        self.closed = False
        self.pages = []

    def new_page(self):
        raise RuntimeError("여기까지 오면 안 된다 — 주입 확인용 대역이다")

    def close(self):
        self.closed = True


def test_probe_producer_는_주입된_playwright_를_쓴다(monkeypatch):
    """주입하면 sync_playwright() 를 부르지 않아야 한다."""
    injected = _FakePlaywright()
    seen = {}

    def fake_launch(playwright, **kwargs):
        seen["playwright"] = playwright
        playwright.used = True
        return _FakeContext()

    def forbidden_sync_playwright():
        raise AssertionError(
            "주입했는데도 sync_playwright() 를 열었다 — 중첩 호출 결함이 되돌아온다"
        )

    monkeypatch.setattr(verify_x_auth, "launch_x_persistent_context", fake_launch)
    monkeypatch.setattr(verify_x_auth, "sync_playwright", forbidden_sync_playwright)

    with pytest.raises(RuntimeError):
        verify_x_auth.probe_producer(injected)

    assert seen["playwright"] is injected
    assert injected.used is True


def test_probe_producer_는_주입이_없으면_직접_연다(monkeypatch):
    """단독 실행(main) 경로는 종전대로 자기 인스턴스를 연다."""
    owned = _FakePlaywright()
    opened = {"count": 0}

    class _Ctx:
        def __enter__(self):
            opened["count"] += 1
            return owned

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(verify_x_auth, "sync_playwright", lambda: _Ctx())
    monkeypatch.setattr(
        verify_x_auth,
        "launch_x_persistent_context",
        lambda playwright, **kwargs: _FakeContext(),
    )

    with pytest.raises(RuntimeError):
        verify_x_auth.probe_producer()

    assert opened["count"] == 1


def test_컨텍스트는_예외가_나도_닫힌다(monkeypatch):
    """finally 정리가 살아 있는지 본다. 안 닫으면 브라우저가 샌다."""
    context = _FakeContext()
    monkeypatch.setattr(
        verify_x_auth, "launch_x_persistent_context", lambda playwright, **kwargs: context
    )

    with pytest.raises(RuntimeError):
        verify_x_auth.probe_producer(_FakePlaywright())

    assert context.closed is True
