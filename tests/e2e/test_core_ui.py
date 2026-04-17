import socket
import threading
import time
from contextlib import closing

import pytest
import requests
from playwright.sync_api import Page, expect
from werkzeug.serving import make_server

from server import app as flask_app


def _find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self._server = make_server(host, port, app)

    def run(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()


@pytest.fixture(scope="session")
def server_url():
    port = _find_free_port()
    flask_app.config["TESTING"] = True
    thread = _ServerThread(flask_app, "127.0.0.1", port)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    for _ in range(20):
        try:
            response = requests.get(f"{url}/api/status", timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            time.sleep(0.2)
    else:
        thread.shutdown()
        thread.join(timeout=5)
        pytest.fail(f"Flask test server failed to start on {url}")

    yield url

    thread.shutdown()
    thread.join(timeout=5)


@pytest.mark.e2e
def test_web_viewer_loading(page: Page, server_url):
    page.goto(f"{server_url}/")

    expect(page.locator("#masonryGrid")).to_be_visible(timeout=10000)

    page.wait_for_timeout(3000)

    cards = page.locator("#masonryGrid > div")
    count = cards.count()
    print(f"Loaded posts count: {count}")
    assert count > 0, "No posts loaded in the viewer."


@pytest.mark.e2e
def test_sns_filtering(page: Page, server_url):
    page.goto(f"{server_url}/")
    page.wait_for_timeout(3000)

    threads_btn = page.locator("#filterContainer button:has-text('Threads')")
    if threads_btn.count() > 0:
        threads_btn.click()
        page.wait_for_timeout(1000)

        visible_posts = page.locator("#masonryGrid > div:visible")
        assert visible_posts.count() > 0, "Filtered posts should be visible."
    else:
        pytest.skip("Threads filter button not found.")


@pytest.mark.e2e
def test_api_status_check(server_url):
    response = requests.get(f"{server_url}/api/status")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


@pytest.mark.e2e
def test_management_modal_open(page: Page, server_url):
    page.goto(f"{server_url}/")
    page.wait_for_timeout(3000)

    settings_btn = page.locator("#settingsBtn")
    expect(settings_btn).to_be_visible()
    settings_btn.click()

    expect(page.locator("#managementModal")).to_be_visible()

    close_btn = page.locator("#closeManagementModal")
    close_btn.click()
    expect(page.locator("#managementModal")).not_to_be_visible()
