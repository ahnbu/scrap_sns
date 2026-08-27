"""`linkedin_metric_single.py --only` 처리 범위 옵션 단위 테스트.

내 글 파일(`linkedin_own_full_*.json`)을 `my_posts_scrap.py` 와 이 consumer 가
같은 웨이브에서 동시에 read-modify-write 해 경합이 났다. 두 실행을 갈라
직렬화하려면 처리 범위를 나눌 수 있어야 한다.

기존 호출(인자 없음)은 `all` 로 지금과 똑같이 동작해야 한다 - 하위호환이
깨지면 예약작업과 수동 실행이 조용히 반쪽만 돈다.

계획: _docs/20260827_04 (3.5 T5-a / V16, V17)
"""

from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import linkedin_metric_single  # noqa: E402


@pytest.fixture
def captured_scopes(monkeypatch):
    """실제 브라우저를 띄우지 않고 `sources` 에 어떤 라벨이 담겼는지만 본다."""
    monkeypatch.setattr(linkedin_metric_single, "load_failures", lambda: {})
    monkeypatch.setattr(linkedin_metric_single, "save_failures", lambda failures: None)
    monkeypatch.setattr(linkedin_metric_single, "failure_counts", lambda failures: {})
    monkeypatch.setattr(
        linkedin_metric_single, "latest_full_file", lambda: "saved.json"
    )
    monkeypatch.setattr(
        linkedin_metric_single, "latest_own_full_file", lambda: "own.json"
    )
    monkeypatch.setattr(
        linkedin_metric_single, "load_full", lambda path: ({}, [{"url": path}])
    )

    seen = []

    def fake_selector(posts, limit=None, failure_counts=None):
        seen.append(posts[0]["url"])
        # 대상이 없으면 sources 에 안 담기므로 1건씩 돌려준다.
        return list(posts)

    monkeypatch.setattr(linkedin_metric_single, "select_targets", fake_selector)
    monkeypatch.setattr(linkedin_metric_single, "select_own_targets", fake_selector)

    # sources 구성이 끝난 직후 멈춘다. 그 뒤는 Playwright 영역이다.
    class _Stop(RuntimeError):
        pass

    def boom():
        raise _Stop()

    monkeypatch.setattr(linkedin_metric_single, "sync_playwright", boom)
    return seen, _Stop


def _run(argv, captured):
    seen, stop = captured
    with pytest.raises(stop):
        linkedin_metric_single.main(argv)
    return seen


# V16 - 인자 없이 부르면 저장글·내 글 둘 다 처리한다 (기존 동작 불변)
def test_default_processes_both_sources(captured_scopes):
    assert _run([], captured_scopes) == ["saved.json", "own.json"]


def test_explicit_all_matches_default(captured_scopes):
    assert _run(["--only", "all"], captured_scopes) == ["saved.json", "own.json"]


# V17 - 한쪽만 처리한다
def test_only_saved_skips_own_file(captured_scopes):
    assert _run(["--only", "saved"], captured_scopes) == ["saved.json"]


def test_only_own_skips_saved_file(captured_scopes):
    assert _run(["--only", "own"], captured_scopes) == ["own.json"]


def test_unknown_scope_is_rejected(captured_scopes):
    """오타가 조용히 all 로 떨어지면 직렬화가 무너진다."""
    with pytest.raises(SystemExit):
        linkedin_metric_single.main(["--only", "everything"])
