"""Tests for the current Threads detail response shape (``data.media``).

The old shape put a whole thread under ``thread_items``; those tests live in
``test_threads_parser.py`` and must keep passing. This file covers the shape
Threads switched to, where the post body and its follow-up chain sit in
separate ``"result":{"data" ...}`` blocks on the same page.
"""
import json
import os

import pytest

from utils.threads_parser import (
    extract_items_from_media_html,
    extract_json_from_html,
    iter_result_data_blocks,
    select_detail_media,
)

GOLDEN_DIR = os.path.join("tests", "fixtures", "golden", "threads")


def load(name):
    with open(os.path.join(GOLDEN_DIR, f"{name}.html"), encoding="utf-8") as file:
        return file.read()


@pytest.mark.parametrize(
    "fixture,requested_code,expected_root,expected_user,expected_count",
    [
        ("media_single", "DcH-n9mEyK5", "DcH-n9mEyK5", "yangyang123001", 1),
        ("media_self_thread", "DcLDB4gGwew", "DcLDB4gGwew", "careerhackeralex", 11),
        ("media_redirect", "DbkBrexCRqX", "DbkBQE2CXD8", "tofukyung", 8),
        ("media_block_offset", "DcKZzrkmK_F", "DcKZzrkmK_F", "yoonyongnyong", 4),
    ],
)
def test_extract_items_from_media_html(
    fixture, requested_code, expected_root, expected_user, expected_count
):
    items = extract_items_from_media_html(load(fixture), requested_code, None)

    assert len(items) == expected_count
    assert items[0]["code"] == expected_root
    assert items[0]["username"] == expected_user
    assert items[0]["full_text"]


@pytest.mark.parametrize(
    "fixture",
    ["media_single", "media_self_thread", "media_redirect", "media_block_offset"],
)
def test_old_thread_items_path_does_not_claim_the_new_shape(fixture):
    """The new shape has no ``thread_items``, so the old entry point bows out."""
    assert extract_json_from_html(load(fixture)) is None


@pytest.mark.parametrize(
    "fixture",
    ["media_single", "media_self_thread", "media_redirect", "media_block_offset"],
)
def test_single_author_per_thread(fixture):
    """A collected thread never mixes authors - that was the X contamination."""
    items = extract_items_from_media_html(load(fixture), fixture, None)
    assert len({item["username"] for item in items}) == 1


def test_direct_replies_are_not_collected():
    """Other people's replies sit next to the chain and must stay out."""
    html = load("media_self_thread")
    reply_codes = set()
    for block in iter_result_data_blocks(html):
        media = block.get("media")
        if not isinstance(media, dict):
            continue
        replies = (media.get("text_post_app_info") or {}).get("direct_replies") or {}
        for edge in replies.get("edges") or []:
            node = (edge or {}).get("node") or {}
            for sub in ((node.get("posts") or {}).get("edges") or []):
                code = ((sub or {}).get("node") or {}).get("code")
                if code:
                    reply_codes.add(code)

    assert reply_codes, "fixture should carry replies for this test to mean anything"
    collected = {item["code"] for item in extract_items_from_media_html(html, "DcLDB4gGwew", None)}
    assert collected & reply_codes == set()


def test_block_position_is_not_used():
    """The body block is not always first, so index must not decide."""
    blocks = list(iter_result_data_blocks(load("media_block_offset")))
    first_media = blocks[0].get("media") if isinstance(blocks[0], dict) else None
    assert not (isinstance(first_media, dict) and "caption" in first_media), (
        "fixture no longer exercises the offset case"
    )
    selected = select_detail_media(blocks, "DcKZzrkmK_F", None)
    assert selected is not None
    assert selected["code"] == "DcKZzrkmK_F"


def test_ambiguous_candidates_return_none():
    """Two equally plausible bodies mean we fail rather than guess."""
    body = {
        "media": {
            "code": "AAA",
            "caption": {"text": "one"},
            "user": {"pk": "1", "username": "alpha"},
        }
    }
    other = {
        "media": {
            "code": "BBB",
            "caption": {"text": "two"},
            "user": {"pk": "2", "username": "beta"},
        }
    }
    assert select_detail_media([body, other], "CCC", "gamma") is None


def test_requested_code_breaks_a_tie():
    body = {
        "media": {
            "code": "AAA",
            "caption": {"text": "one"},
            "user": {"pk": "1", "username": "alpha"},
        }
    }
    other = {
        "media": {
            "code": "BBB",
            "caption": {"text": "two"},
            "user": {"pk": "2", "username": "beta"},
        }
    }
    selected = select_detail_media([body, other], "BBB", None)
    assert selected is not None
    assert selected["code"] == "BBB"


def test_iter_result_data_blocks_skips_unparsable_blocks():
    html = (
        '<script>{"result":{"data":{"media":{"code":"AAA","caption":{"text":"x"},'
        '"user":{"pk":"1","username":"alpha"}}}}}</script>'
        '<script>{"result":{"data":{"media": broken</script>'
    )
    blocks = list(iter_result_data_blocks(html))
    assert len(blocks) == 1
    assert blocks[0]["media"]["code"] == "AAA"


def test_no_result_blocks_yields_nothing():
    assert extract_items_from_media_html("<html><body>nothing</body></html>", "AAA", None) == []


def test_golden_fixtures_stay_small():
    """Fixtures are committed, so guard against re-adding a full 1MB snapshot."""
    for name in ("media_single", "media_self_thread", "media_redirect", "media_block_offset"):
        size = os.path.getsize(os.path.join(GOLDEN_DIR, f"{name}.html"))
        assert size < 300 * 1024, f"{name}.html grew to {size} bytes"


def test_self_thread_chain_keeps_author_order():
    """Root first, then the author's own follow-ups - merge relies on this."""
    items = extract_items_from_media_html(load("media_self_thread"), "DcLDB4gGwew", None)
    assert items[0]["code"] == "DcLDB4gGwew"
    assert all(item["root_code"] == "DcLDB4gGwew" for item in items)


def test_extracted_items_are_json_serializable():
    items = extract_items_from_media_html(load("media_redirect"), "DbkBrexCRqX", None)
    json.dumps(items, ensure_ascii=False)
