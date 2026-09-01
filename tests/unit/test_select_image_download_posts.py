"""`select_image_download_posts()` 대상 선정 규칙 테스트.

신규 글만 받으면 첫 수집에서 놓친 이미지가 영영 복구되지 않는다는 결함을 막는다.
계획: _docs/20260901_01_링크드인-이미지-복구와-외부요약-자동화-아이콘-개선-계획.md

`total_scrap` 은 import 시점에 `sys.stdout` 을 교체해 pytest 캡처와 충돌한다.
그래서 같은 폴더의 다른 total_scrap 테스트와 마찬가지로 subprocess 로 돌린다.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FUTURE = int(time.time()) + 30 * 86_400
PAST = int(time.time()) - 30 * 86_400

LIVE_URL = f"https://media.licdn.com/dms/image/v2/LIVE/feedshare-image/0/1/?e={FUTURE}&v=beta"
DEAD_URL = f"https://media.licdn.com/dms/image/v2/DEAD/feedshare-image/0/1/?e={PAST}&v=beta"
NO_EXPIRY_URL = "https://scontent.cdninstagram.com/v/t51.jpg?oh=abc&oe=DEADBEEF"


def _post(post_id, media=None, local_images=None, platform="linkedin"):
    return {
        "sns_platform": platform,
        "url": f"https://www.linkedin.com/feed/update/{post_id}",
        "platform_id": post_id,
        "media": media or [],
        "local_images": local_images or [],
    }


def _select(posts, mode, existing_ids):
    """subprocess 로 select_image_download_posts 를 돌리고 선택된 platform_id 목록을 돌려준다."""
    script = """
import json
import sys
import total_scrap
from utils.post_meta import build_post_key

payload = json.loads(sys.argv[1])
posts = payload["posts"]
existing_ids = set(payload["existing_ids"])
existing_keys = {build_post_key(p) for p in posts if p["platform_id"] in existing_ids}

selected = total_scrap.select_image_download_posts(posts, payload["mode"], existing_keys)
sys.stderr.write("RESULT" + json.dumps([p["platform_id"] for p in selected]))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    payload = json.dumps({"posts": posts, "mode": mode, "existing_ids": existing_ids})

    completed = subprocess.run(
        [sys.executable, "-c", script, payload],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    marker = completed.stderr.rsplit("RESULT", 1)[-1].strip()
    return json.loads(marker)


def test_all_mode_returns_every_post():
    posts = [_post("P1", [LIVE_URL])]
    assert _select(posts, "all", ["P1"]) == ["P1"]


def test_no_existing_keys_returns_every_post():
    posts = [_post("P1", [LIVE_URL])]
    assert _select(posts, "update", []) == ["P1"]


def test_new_post_is_included():
    posts = [
        _post("OLD", [LIVE_URL], ["web_viewer/images/a.jpg"]),
        _post("NEW", [LIVE_URL]),
    ]
    assert _select(posts, "update", ["OLD"]) == ["NEW"]


def test_existing_post_with_local_images_is_skipped():
    posts = [_post("P1", [LIVE_URL], ["web_viewer/images/a.jpg"])]
    assert _select(posts, "update", ["P1"]) == []


def test_existing_post_with_only_expired_urls_is_skipped():
    """죽은 URL 에 매 실행 403 요청을 반복하지 않는다."""
    posts = [_post("P1", [DEAD_URL])]
    assert _select(posts, "update", ["P1"]) == []


def test_existing_post_with_live_url_and_no_local_image_is_retried():
    """이번 변경의 핵심 - 놓친 글을 다음 실행에서 다시 줍는다."""
    posts = [_post("P1", [LIVE_URL])]
    assert _select(posts, "update", ["P1"]) == ["P1"]


def test_existing_post_with_mixed_urls_is_retried():
    posts = [_post("P1", [DEAD_URL, LIVE_URL])]
    assert _select(posts, "update", ["P1"]) == ["P1"]


def test_existing_post_without_media_is_skipped():
    posts = [_post("P1", [])]
    assert _select(posts, "update", ["P1"]) == []


def test_url_without_expiry_param_is_retried():
    """Threads(fbcdn) 처럼 `e=` 를 안 쓰는 CDN 은 만료로 단정하지 않는다."""
    posts = [_post("P1", [NO_EXPIRY_URL], platform="threads")]
    assert _select(posts, "update", ["P1"]) == ["P1"]


def test_video_only_post_is_skipped():
    """mp4 는 이미지 다운로드 대상이 아니다."""
    posts = [_post("P1", ["https://cdn.example.com/clip.mp4"])]
    assert _select(posts, "update", ["P1"]) == []
