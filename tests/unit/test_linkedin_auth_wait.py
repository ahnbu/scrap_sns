import pytest

import linkedin_scrap


class _FakeLocator:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 1 if self.page.current_url == linkedin_scrap.TARGET_URL else 0


class _TransientLoginPage:
    def __init__(self):
        self.current_url = "about:blank"
        self.goto_calls = []
        self.wait_calls = 0

    def goto(self, url):
        self.goto_calls.append(url)
        if url == linkedin_scrap.TARGET_URL:
            self.current_url = (
                "https://www.linkedin.com/uas/login?"
                "session_redirect=https%3A%2F%2Fwww.linkedin.com%2Fmy-items%2Fsaved-posts%2F"
            )
        else:
            self.current_url = url

    @property
    def url(self):
        return self.current_url

    def locator(self, _selector):
        return _FakeLocator(self)

    def wait_for_timeout(self, _milliseconds):
        self.wait_calls += 1
        if self.wait_calls >= 2:
            self.current_url = linkedin_scrap.TARGET_URL


def test_manage_login_waits_for_transient_linkedin_redirect(monkeypatch, tmp_path):
    auth_file = tmp_path / "storage_state.json"
    auth_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(linkedin_scrap, "AUTH_FILE", str(auth_file))
    monkeypatch.setattr(linkedin_scrap.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(linkedin_scrap, "is_orchestrated_run", lambda: True)

    def fail_auth_required(*_args, **_kwargs):
        raise AssertionError("transient login redirect was treated as auth failure")

    monkeypatch.setattr(linkedin_scrap, "exit_auth_required", fail_auth_required)

    page = _TransientLoginPage()
    scraper = linkedin_scrap.LinkedinScraper.__new__(linkedin_scrap.LinkedinScraper)

    scraper.manage_login(page)

    assert page.goto_calls == [linkedin_scrap.TARGET_URL]
    assert page.wait_calls >= 2
