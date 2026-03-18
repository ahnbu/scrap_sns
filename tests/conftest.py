import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# === Flask test client (보안 테스트용) ===
@pytest.fixture(scope="session")
def app():
    from server import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app, tmp_path):
    """Flask test client — WEB_VIEWER_DIR을 tmp_path로 교체하여 부작용 방지"""
    import server
    original_dir = server.WEB_VIEWER_DIR
    server.WEB_VIEWER_DIR = str(tmp_path)
    yield app.test_client()
    server.WEB_VIEWER_DIR = original_dir


# === Playwright 콘솔 수집 (U1, U4용) ===
@pytest.fixture
def console_messages(page):
    messages = []
    page.on("console", lambda msg: messages.append(msg))
    return messages
