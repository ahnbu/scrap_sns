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


def test_update_mode_stops_after_consecutive_existing_posts_even_when_media_is_empty(monkeypatch):
    activity_id = "7457613653937410048"

    scraper = linkedin_scrap.LinkedinScraper.__new__(linkedin_scrap.LinkedinScraper)
    scraper.posts = []
    scraper.collected_codes = set()
    scraper.existing_codes = {activity_id}
    scraper.existing_posts_map = {
        activity_id: {
            "platform_id": activity_id,
            "media": [],
        }
    }
    scraper.consecutive_existing_count = linkedin_scrap.CONSECUTIVE_EXISTING_LIMIT - 1
    scraper.stopped_early = False

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "update only")

    def fail_parse(*_args, **_kwargs):
        raise AssertionError("existing post should not be reparsed for media backfill")

    monkeypatch.setattr(linkedin_scrap, "parse_linkedin_post", fail_parse)

    scraper.extract_post_from_view_model({"entityUrn": f"urn:li:activity:{activity_id}"})

    assert scraper.stopped_early is True
    assert scraper.posts == []


def test_update_mode_resets_consecutive_existing_count_after_new_post(monkeypatch):
    activity_id = "7457613653937410048"

    scraper = linkedin_scrap.LinkedinScraper.__new__(linkedin_scrap.LinkedinScraper)
    scraper.posts = []
    scraper.collected_codes = set()
    scraper.existing_codes = set()
    scraper.existing_posts_map = {}
    scraper.consecutive_existing_count = 3
    scraper.stopped_early = False

    monkeypatch.setattr(linkedin_scrap, "CRAWL_MODE", "update only")
    monkeypatch.setattr(
        linkedin_scrap,
        "parse_linkedin_post",
        lambda *_args, **_kwargs: {
            "platform_id": activity_id,
            "date": "2026-05-07",
            "username": "tester",
            "full_text": "new saved post",
        },
    )

    scraper.extract_post_from_view_model({"entityUrn": f"urn:li:activity:{activity_id}"})

    assert scraper.consecutive_existing_count == 0
    assert len(scraper.posts) == 1
