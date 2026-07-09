from pathlib import Path


def test_linkedin_opencli_collector_declares_browser_close_cleanup():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "linkedin_opencli_shadow_collect.mjs"
    source = script_path.read_text(encoding="utf-8")

    assert 'browser(session, ["open", url, "--window", "background"]' in source
    assert 'browser(session, ["unbind"]' in source
    assert 'browser(session, ["close"]' in source
    assert '["tab", "new"' not in source
    assert '["tab", "close"' not in source
